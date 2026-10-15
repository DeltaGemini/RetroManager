"""
RetroAchievements (retroachievements.org) integration for metadata scraping.
It lists the checksums of every ROM it supports, ROM hacks included, so a game
can be identified by its contents rather than its name.
https://api-docs.retroachievements.org/
"""

import hashlib
import json
import logging
import re
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from backend.media_index import title_key
from backend.name_style import style_name
from backend.rom_hashes import HashCache, open_rom
from backend.scraper import text_date_to_es
from backend.systems import is_arcade, normalize_system_name, retroachievements_console_id

logger = logging.getLogger(__name__)

# How long a console's game list is reused before it's fetched again
LIST_MAX_AGE = 7 * 86400
# How long a game's achievement list (and what's been earned) is reused
PROGRESS_MAX_AGE = 300
# How long a ROM that RetroAchievements didn't recognise is left before asking again
UNMATCHED_MAX_AGE = 7 * 86400
SEARCH_MIN_SCORE = 0.5
MAX_RESULTS = 20
# IDs from this source are prefixed, so they can't be mistaken for ScreenScraper's
ID_PREFIX = 'ra:'

# "~Hack~ Pokemon ...", "~Homebrew~ ...": what kind of release this is
_TAG_RE = re.compile(r'~([^~]+)~\s*')
_SUBSET_RE = re.compile(r'\[Subset\b', re.IGNORECASE)
_DIGITS_RE = re.compile(r'\d+')
# Pictures RetroAchievements shows when a game has none
_PLACEHOLDER_IMAGES = ('/Images/000001.png', '/Images/000002.png')

# Largest ROM read into memory to work out a console-specific checksum
_SPECIAL_HASH_LIMIT = 600 * 1024 * 1024


class RetroAchievementsError(Exception):
    """A RetroAchievements request failed; the message is safe to show in the UI."""


def _md5_from(handle, offset: int) -> str:
    handle.seek(offset)
    digest = hashlib.md5()
    for chunk in iter(lambda: handle.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def _nds_hash(handle, size: int) -> Optional[str]:
    """Nintendo DS: the header, both program sections and the icon/title block."""
    offset = 0
    handle.seek(0)
    header = handle.read(512)
    if len(header) < 512:
        return None
    if header[:4] == b'\x2e\x00\x00\xea' and header[0xB0:0xB4] == b'\x44\x46\x96\x00':
        # SuperCard header in front of the real one
        offset = 512
        handle.seek(offset)
        header = handle.read(512)
        if len(header) < 512:
            return None

    def word(at):
        return int.from_bytes(header[at:at + 4], 'little')

    arm9_addr, arm9_size = word(0x20), word(0x2C)
    arm7_addr, arm7_size = word(0x30), word(0x3C)
    icon_addr = word(0x68)
    if arm9_size + arm7_size > 16 * 1024 * 1024:
        return None
    digest = hashlib.md5()
    digest.update(header[:0x160])
    for addr, length in ((arm9_addr, arm9_size), (arm7_addr, arm7_size)):
        handle.seek(addr + offset)
        digest.update(handle.read(length))
    handle.seek(icon_addr + offset)
    digest.update(handle.read(0xA00).ljust(0xA00, b'\x00'))
    return digest.hexdigest()


def _n64_hash(handle, size: int) -> Optional[str]:
    """Nintendo 64: the ROM in big-endian (.z64) byte order, whichever order the file uses."""
    handle.seek(0)
    first = handle.read(1)
    if first == b'\x80' or size > 128 * 1024 * 1024:
        return None  # already big-endian: the plain checksum is the one
    handle.seek(0)
    data = bytearray(handle.read())
    if first == b'\x37':      # .v64: each pair of bytes swapped
        data[0::2], data[1::2] = data[1::2], data[0::2]
    elif first == b'\x40':    # .n64: each 4-byte word reversed
        data[0::4], data[1::4], data[2::4], data[3::4] = data[3::4], data[2::4], data[1::4], data[0::4]
    else:
        return None
    return hashlib.md5(data).hexdigest()


def _header_skip(system: str, handle, size: int) -> int:
    """Bytes of copier/emulator header that RetroAchievements leaves out of the checksum."""
    handle.seek(0)
    head = handle.read(16)
    if system in ('nes', 'famicom') and head[:4] == b'NES\x1a':
        return 16
    if system in ('fds', 'famicomdisksystem') and head[:4] == b'FDS\x1a':
        return 16
    if system in ('snes', 'sfc', 'supernintendo', 'superfamicom') and size % 0x2000 == 512:
        return 512
    if system in ('pcengine', 'tg16', 'turbografx16', 'supergrafx') and size % 0x20000 == 512:
        return 512
    if system in ('atarilynx', 'lynx') and head[:5] == b'LYNX\x00':
        return 64
    if system == 'atari7800' and head[1:10] == b'ATARI7800':
        return 128
    return 0


def rom_hashes(system_name: str, path: Path, hash_cache: HashCache) -> List[str]:
    """The checksums RetroAchievements may know this ROM by: the plain MD5, and
    the console's own variant where it has one (header skipped, byte order
    fixed, DS sections). Disc images use a scheme that isn't worked out here."""
    path = Path(path)
    if is_arcade(system_name):
        # Arcade sets are identified by their file name
        return [hashlib.md5(path.stem.encode('utf-8')).hexdigest()]

    found = []
    plain = hash_cache.hashes(path)
    if plain:
        found.append(plain['md5'])
    system = normalize_system_name(system_name)
    try:
        if not path.is_file() or path.stat().st_size > _SPECIAL_HASH_LIMIT:
            return found
        handle = open_rom(path)
        if handle is None:
            return found
        with handle:
            size = handle.seek(0, 2)
            special = None
            if system in ('nds', 'nintendods'):
                special = _nds_hash(handle, size)
            elif system in ('n64', 'nintendo64'):
                special = _n64_hash(handle, size)
            else:
                skip = _header_skip(system, handle, size)
                if skip:
                    special = _md5_from(handle, skip)
    except OSError as e:
        logger.warning(f"Couldn't read {path} for RetroAchievements hashing: {e}")
        return found
    if special and special not in found:
        found.insert(0, special)
    return found


def split_title(title: str) -> Dict[str, Any]:
    """"~Hack~ Pokemon - Ash Gray" -> {'name': 'Pokemon - Ash Gray', 'tags': ['Hack']}."""
    tags = _TAG_RE.findall(title or '')
    name = _TAG_RE.sub('', title or '').strip()
    return {'name': name, 'tags': tags}


def _name_score(wanted_key: str, title: str) -> float:
    """0-1 similarity; a title can list several names ("A | B") and the best one counts."""
    best = 0.0
    for part in title.split('|'):
        key = title_key(part)
        if not key:
            continue
        score = SequenceMatcher(None, wanted_key, key).ratio()
        if _DIGITS_RE.findall(wanted_key) != _DIGITS_RE.findall(key):
            score *= 0.7
        best = max(best, score)
    return best


class GameIdCache:
    """Which RetroAchievements game each ROM is, remembered in DATA_PATH so a
    game's page doesn't hash and look up its ROM every time it's opened."""

    def __init__(self, cache_dir: Path):
        self.state_file = Path(cache_dir) / 'retroachievements' / 'rom-games.json'
        self._lock = threading.Lock()
        try:
            self._items: Dict[str, Dict] = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self._items = {}

    @staticmethod
    def _stamp(rom_file: Path) -> Optional[List[int]]:
        try:
            stat = rom_file.stat()
        except OSError:
            return None
        return [stat.st_size, stat.st_mtime_ns]

    def get(self, key: str, rom_file: Path):
        """(known, game id or None). `known` is False when the ROM hasn't been
        looked up, has changed since, or went unrecognised long enough ago to retry."""
        with self._lock:
            item = self._items.get(key)
        if not item or item.get('stamp') != self._stamp(rom_file):
            return False, None
        if item.get('id') is None and time.time() - item.get('time', 0) > UNMATCHED_MAX_AGE:
            return False, None
        return True, item.get('id')

    def move(self, old_key: str, new_key: Optional[str], new_file: Optional[Path] = None):
        """A ROM was renamed (what's known about it follows) or removed."""
        with self._lock:
            item = self._items.pop(old_key, None)
            if item and new_key:
                if new_file is not None:
                    item['stamp'] = self._stamp(new_file)
                self._items[new_key] = item
            if item:
                try:
                    tmp = self.state_file.with_suffix('.tmp')
                    tmp.write_text(json.dumps(self._items))
                    tmp.replace(self.state_file)
                except OSError as e:
                    logger.warning(f"Couldn't save RetroAchievements game IDs: {e}")

    def roms_for(self, game_id: Any) -> List[str]:
        """The "system/rom path" keys already known to be this game."""
        with self._lock:
            return [key for key, item in self._items.items() if str(item.get('id')) == str(game_id)]

    def put(self, key: str, rom_file: Path, game_id: Optional[int]):
        with self._lock:
            self._items[key] = {'stamp': self._stamp(rom_file), 'id': game_id, 'time': time.time()}
            try:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.state_file.with_suffix('.tmp')
                tmp.write_text(json.dumps(self._items))
                tmp.replace(self.state_file)
            except OSError as e:
                logger.warning(f"Couldn't save RetroAchievements game IDs: {e}")


class RetroAchievementsAPI:
    BASE_URL = "https://retroachievements.org/API"
    MEDIA_URL = "https://media.retroachievements.org"
    SITE_URL = "https://retroachievements.org"

    def __init__(self, api_key: str, cache_dir: Path, user: str = ''):
        self.api_key = (api_key or '').strip()
        # Whose earned achievements are shown; without one, only the list is
        self.user = (user or '').strip()
        self.cache_dir = Path(cache_dir) / 'retroachievements'
        self.session = requests.Session()
        self._progress: Dict[Any, Dict] = {}  # (game id, 'overview' or 'unlocks'; user) -> {'time', 'data'}
        self._lists: Dict[int, Dict] = {}  # console id -> {'expires', 'games', 'by_hash'}

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Any:
        if not self.configured:
            raise RetroAchievementsError("Add your RetroAchievements API key in Tools > Settings.")
        response = None
        for attempt in range(2):
            try:
                response = self.session.get(f"{self.BASE_URL}/{endpoint}", params={**params, 'y': self.api_key},
                                            timeout=(10, 60))
            except requests.RequestException as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                # The key is in the URL, so the exception text isn't passed on
                logger.warning(f"RetroAchievements {endpoint} failed: {type(e).__name__}")
                raise RetroAchievementsError("Couldn't reach RetroAchievements.")
            if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                time.sleep(2)
                continue
            break

        if response.status_code in (401, 403):
            raise RetroAchievementsError("RetroAchievements rejected the API key. Check it in Tools > Settings.")
        if response.status_code == 429:
            raise RetroAchievementsError("RetroAchievements rate limit hit. Wait a moment and retry.")
        if response.status_code != 200:
            logger.warning(f"RetroAchievements {endpoint}: HTTP {response.status_code}: {response.text[:200]}")
            raise RetroAchievementsError(f"RetroAchievements returned HTTP {response.status_code}.")
        try:
            return response.json()
        except ValueError:
            raise RetroAchievementsError("RetroAchievements returned a response that isn't JSON.")

    def forget_progress(self):
        """Drop what's remembered about achievements earned (the user or key changed)."""
        self._progress.clear()

    # --- Console game lists (cached on disk: they're large and change slowly) ---

    def _console_list(self, console_id: int) -> Dict:
        cached = self._lists.get(console_id)
        if cached and time.time() < cached['expires']:
            return cached

        cache_file = self.cache_dir / f"console-{console_id}.json"
        saved, saved_time = None, 0.0
        try:
            saved_time = cache_file.stat().st_mtime
            saved = json.loads(cache_file.read_text())
        except (OSError, ValueError):
            saved = None

        # Lists saved before achievement counts were kept are fetched again
        if saved and 'achievements' not in saved[0]:
            saved_time = 0.0
        if saved is not None and time.time() - saved_time < LIST_MAX_AGE:
            games, expires = saved, saved_time + LIST_MAX_AGE
        else:
            try:
                data = self._make_request('API_GetGameList.php', {'i': console_id, 'h': 1})
            except RetroAchievementsError:
                if saved is None:
                    raise
                # An old list is better than none when the site can't be reached
                logger.warning(f"RetroAchievements: using the saved list for console {console_id}")
                games, expires = saved, time.time() + 3600
            else:
                games = [{'id': g.get('ID'), 'title': g.get('Title') or '', 'console': g.get('ConsoleName') or '',
                          'icon': g.get('ImageIcon') or '', 'achievements': int(g.get('NumAchievements') or 0),
                          'hashes': [str(h).lower() for h in g.get('Hashes') or []]}
                         for g in data or [] if isinstance(g, dict) and g.get('ID')]
                expires = time.time() + LIST_MAX_AGE
                try:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    tmp = cache_file.with_suffix('.tmp')
                    tmp.write_text(json.dumps(games))
                    tmp.replace(cache_file)
                except OSError as e:
                    logger.warning(f"Couldn't save the RetroAchievements list: {e}")

        entry = {'expires': expires, 'games': games,
                 'by_hash': {h: g for g in games for h in g.get('hashes') or []}}
        self._lists[console_id] = entry
        return entry

    def identify(self, system_name: str, hashes: List[str]) -> Optional[Dict]:
        """The game RetroAchievements lists any of these checksums for, or None."""
        console_id = retroachievements_console_id(system_name)
        if not console_id or not hashes:
            return None
        by_hash = self._console_list(console_id)['by_hash']
        for rom_hash in hashes:
            game = by_hash.get(rom_hash.lower())
            if game:
                return game
        return None

    def console_games(self, system_name: str) -> Dict[int, Dict]:
        """{game id: game-list entry} for a system's console ({} if it has none)."""
        console_id = retroachievements_console_id(system_name)
        if not console_id or not self.configured:
            return {}
        return {g['id']: g for g in self._console_list(console_id)['games']}

    def search_game(self, game_name: str, system_name: Optional[str]) -> List[Dict]:
        """Games on the system whose title is close to `game_name`, best first, each
        with a 'score'. RetroAchievements has no search of its own, so the system's
        list is searched here."""
        console_id = retroachievements_console_id(system_name)
        if not console_id:
            raise RetroAchievementsError("RetroAchievements doesn't cover this system (or RetroManager doesn't know its folder name).")
        wanted = title_key(game_name)
        if not wanted:
            return []
        scored = []
        for game in self._console_list(console_id)['games']:
            if _SUBSET_RE.search(game['title']):
                continue
            name = split_title(game['title'])['name']
            score = _name_score(wanted, name)
            if wanted in title_key(name):
                score = max(score, 0.75)  # a title that contains the search text
            if score >= SEARCH_MIN_SCORE:
                scored.append({**game, 'score': score})
        scored.sort(key=lambda g: g['score'], reverse=True)
        return scored[:MAX_RESULTS]

    def get_game_info(self, game_id: Any) -> Dict:
        """Fetch one game's details. Raises RetroAchievementsError."""
        numeric = str(game_id)[len(ID_PREFIX):] if str(game_id).startswith(ID_PREFIX) else str(game_id)
        if not numeric.isdigit():
            raise RetroAchievementsError("That isn't a RetroAchievements game.")
        data = self._make_request('API_GetGame.php', {'i': int(numeric)})
        if not isinstance(data, dict) or not (data.get('Title') or data.get('GameTitle')):
            raise RetroAchievementsError("RetroAchievements returned no data for that game.")
        return data

    def _media_url(self, image_path: Any) -> Optional[str]:
        if not image_path or not isinstance(image_path, str) or image_path in _PLACEHOLDER_IMAGES:
            return None
        return image_path if image_path.startswith('http') else f"{self.MEDIA_URL}{image_path}"

    def summarize_search_result(self, game: Dict) -> Dict[str, Any]:
        """Short form of a game-list entry, shaped like a ScreenScraper result so
        the bulk scrape review can list both."""
        title = split_title(game.get('title') or '')
        summary = {
            'id': f"{ID_PREFIX}{game.get('id')}",
            'nom': title['name'],
            'name': title['name'],
            'systemenom': f"{game.get('console') or 'RetroAchievements'} (RetroAchievements)",
            'image': self._media_url(game.get('icon')),
            'year': None,
            'regions': [],
            'is_hack': 'Hack' in title['tags'],
            'source': 'retroachievements',
        }
        if 'score' in game:
            summary['score'] = round(game['score'], 2)
        return summary

    def extract_game_data(self, game: Dict) -> Dict[str, Any]:
        """Convert API_GetGame's answer to gamelist fields plus a `media` dict.
        RetroAchievements has no descriptions, player counts or ratings."""
        title = split_title(game.get('Title') or game.get('GameTitle') or '')
        media = {}
        for field, folder in (('ImageBoxArt', 'box2d'), ('ImageTitle', 'screenshottitle'),
                              ('ImageIngame', 'screenshot'), ('ImageIcon', 'icon')):
            url = self._media_url(game.get(field))
            if url:
                media[folder] = url
        return {
            'name': style_name(title['name'].split('|')[0].strip()),
            'genre': game.get('Genre') or '',
            'developer': game.get('Developer') or '',
            'publisher': game.get('Publisher') or '',
            'releasedate': text_date_to_es(game.get('Released') or ''),
            'media': media,
        }

    def get_achievements(self, game_id: Any, refresh: bool = False, user: Optional[str] = None) -> Dict:
        """A game's achievements, in RetroAchievements' order, with which ones
        `user` (the configured user if none is given) has earned. Raises RetroAchievementsError.

        {'game_id', 'title', 'console', 'url', 'user', 'total', 'earned',
         'earned_hardcore', 'points', 'points_earned', 'completion' (0-100),
         'achievements': [{'id', 'title', 'description', 'points', 'type',
                           'badge', 'badge_locked', 'earned', 'hardcore'}]}
        `earned` is the date it was unlocked ("2024-03-09 18:22:10") or None."""
        numeric = str(game_id)[len(ID_PREFIX):] if str(game_id).startswith(ID_PREFIX) else str(game_id)
        if not numeric.isdigit():
            raise RetroAchievementsError("That isn't a RetroAchievements game.")
        numeric = int(numeric)
        user = (user or self.user or '').strip()
        cached = self._progress.get((numeric, user))
        if cached and not refresh and time.time() - cached['time'] < PROGRESS_MAX_AGE:
            return cached['data']

        if user:
            data = self._make_request('API_GetGameInfoAndUserProgress.php', {'g': numeric, 'u': user})
        else:
            data = self._make_request('API_GetGameExtended.php', {'i': numeric})
        if not isinstance(data, dict) or not data.get('Title'):
            raise RetroAchievementsError("RetroAchievements returned no data for that game.")

        raw = data.get('Achievements') or {}
        # A game with no achievements comes back as an empty list rather than a dict
        entries = list(raw.values()) if isinstance(raw, dict) else list(raw)
        entries = [a for a in entries if isinstance(a, dict)]
        entries.sort(key=lambda a: (int(a.get('DisplayOrder') or 0), int(a.get('ID') or 0)))
        achievements = []
        for entry in entries:
            badge = entry.get('BadgeName')
            earned = entry.get('DateEarned') or entry.get('DateEarnedHardcore') or None
            achievements.append({
                'id': entry.get('ID'),
                'title': entry.get('Title') or '',
                'description': entry.get('Description') or '',
                'points': int(entry.get('Points') or 0),
                # "progression", "win_condition", "missable" or None
                'type': entry.get('type') or entry.get('Type') or None,
                'badge': f"{self.MEDIA_URL}/Badge/{badge}.png" if badge else None,
                'badge_locked': f"{self.MEDIA_URL}/Badge/{badge}_lock.png" if badge else None,
                'earned': earned,
                'hardcore': bool(entry.get('DateEarnedHardcore')),
            })

        earned = [a for a in achievements if a['earned']]
        result = {
            'game_id': numeric,
            'title': split_title(data.get('Title') or '')['name'],
            'console': data.get('ConsoleName') or '',
            'url': f"{self.SITE_URL}/game/{numeric}",
            'user': user or None,
            'total': len(achievements),
            'earned': len(earned),
            'earned_hardcore': sum(1 for a in earned if a['hardcore']),
            'points': sum(a['points'] for a in achievements),
            'points_earned': sum(a['points'] for a in earned),
            'completion': round(100.0 * len(earned) / len(achievements), 1) if achievements else 0.0,
            'achievements': achievements,
        }
        self._progress[(numeric, user)] = {'time': time.time(), 'data': result}
        return result

    def get_user_progress(self, refresh: bool = False, user: Optional[str] = None) -> List[Dict]:
        """Every game `user` (the configured user if none is given) has earned an achievement in:
        [{'game_id', 'title', 'is_hack', 'console_id', 'console', 'icon', 'url',
          'total', 'earned', 'earned_hardcore', 'completion' (0-100),
          'last_earned', 'award'}], most complete first. `award` is
        "mastered", "completed", "beaten-hardcore", "beaten-softcore" or None.
        Raises RetroAchievementsError."""
        user = (user or self.user or '').strip()
        if not user:
            raise RetroAchievementsError("Add your RetroAchievements user name in Tools > Settings to see achievement progress.")
        cached = self._progress.get(('overview', user))
        if cached and not refresh and time.time() - cached['time'] < PROGRESS_MAX_AGE:
            return cached['data']

        rows, offset = [], 0
        while True:
            data = self._make_request('API_GetUserCompletionProgress.php', {'u': user, 'c': 500, 'o': offset})
            page = (data or {}).get('Results') or []
            rows.extend(r for r in page if isinstance(r, dict))
            offset += len(page)
            if not page or offset >= int((data or {}).get('Total') or 0):
                break

        games = []
        for row in rows:
            total, earned = int(row.get('MaxPossible') or 0), int(row.get('NumAwarded') or 0)
            title = split_title(row.get('Title') or '')
            games.append({
                'game_id': row.get('GameID'),
                'title': title['name'],
                'is_hack': 'Hack' in title['tags'],
                'console_id': row.get('ConsoleID'),
                'console': row.get('ConsoleName') or '',
                'icon': self._media_url(row.get('ImageIcon')),
                'url': f"{self.SITE_URL}/game/{row.get('GameID')}",
                'total': total,
                'earned': earned,
                'earned_hardcore': int(row.get('NumAwardedHardcore') or 0),
                'completion': round(100.0 * earned / total, 1) if total else 0.0,
                'last_earned': row.get('MostRecentAwardedDate') or None,
                'award': row.get('HighestAwardKind') or None,
            })
        games.sort(key=lambda g: (-g['completion'], -g['earned'], g['title'].lower()))
        self._progress[('overview', user)] = {'time': time.time(), 'data': games}
        return games

    def get_unlocks(self, refresh: bool = False, user: Optional[str] = None) -> List[Dict]:
        """Every achievement `user` (the configured user if none is given) has
        earned, newest first: [{'date' ("2024-03-09 18:22:10", UTC), 'title',
        'description', 'points', 'badge', 'hardcore', 'game_id', 'game_title',
        'console'}]. An achievement earned in both modes is listed once.
        Raises RetroAchievementsError."""
        user = (user or self.user or '').strip()
        if not user:
            raise RetroAchievementsError("Add your RetroAchievements user name in Tools > Settings to see achievement progress.")
        cached = self._progress.get(('unlocks', user))
        if cached and not refresh and time.time() - cached['time'] < PROGRESS_MAX_AGE:
            return cached['data']
        data = self._make_request('API_GetAchievementsEarnedBetween.php', {'u': user, 'f': 0, 't': int(time.time())})
        by_id: Dict[Any, Dict] = {}
        for row in data if isinstance(data, list) else []:
            if not isinstance(row, dict) or not row.get('Date'):
                continue
            hardcore = str(row.get('HardcoreMode')) in ('1', 'True', 'true')
            known = by_id.get(row.get('AchievementID'))
            if known:
                # Earned in both modes: keep the first time, and note the hardcore one
                known['hardcore'] = known['hardcore'] or hardcore
                known['date'] = min(known['date'], row['Date'])
                continue
            badge = row.get('BadgeName')
            by_id[row.get('AchievementID')] = {
                'date': row['Date'], 'title': row.get('Title') or '', 'description': row.get('Description') or '',
                'points': int(row.get('Points') or 0), 'hardcore': hardcore,
                'badge': f"{self.MEDIA_URL}/Badge/{badge}.png" if badge else self._media_url(row.get('BadgeURL')),
                'game_id': row.get('GameID'), 'game_title': split_title(row.get('GameTitle') or '')['name'],
                'console': row.get('ConsoleName') or '',
            }
        unlocks = sorted(by_id.values(), key=lambda u: u['date'], reverse=True)
        self._progress[('unlocks', user)] = {'time': time.time(), 'data': unlocks}
        return unlocks
