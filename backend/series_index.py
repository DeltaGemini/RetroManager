"""
Which series each game belongs to, and what else is in that series: the games
you have, and the ones you don't.

The lists come from IGDB. Each library game is matched to an IGDB game (by name
and system), which names its "collection" (the series proper) or, failing that,
its "franchise" (broader: anything the characters turn up in). The series'
games are then fetched once and kept. Everything is stored in one file,
DATA_PATH/series.json:

    games    "<system>/<rom path>" -> the IGDB game it was matched to
    series   "c<id>" (collection) or "f<id>" (franchise) -> its name and games
    marks    IGDB game id -> "want" or "skip" (not interested)
    skipped_platforms   series -> platforms hidden within it
"""

import json
import logging
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# IGDB's game types (game_type)
MAIN, STANDALONE_EXPANSION, MOD, REMAKE, REMASTER, EXPANDED, PORT, FORK = 0, 4, 5, 8, 9, 10, 11, 12
# What counts as a game of its own in a series: originals, remakes and
# remasters. Ports, bundles, DLC, packs and updates don't.
LISTED_TYPES = {MAIN, STANDALONE_EXPANSION, REMAKE, REMASTER, EXPANDED}
TYPE_LABELS = {REMAKE: 'Remake', REMASTER: 'Remaster', EXPANDED: 'Expanded edition', STANDALONE_EXPANSION: 'Standalone expansion'}
HACK_TYPES = {MOD, FORK}

MATCH_FIELDS = ('name,alternative_names.name,collections.name,franchises.name,game_type,'
                'platforms,first_release_date,version_parent,parent_game')
SERIES_FIELDS = 'name,game_type,first_release_date,platforms.abbreviation,platforms.name,version_parent,cover.image_id'
SERIES_MAX_AGE = 30 * 86400   # a series' list is fetched again after this long
REQUEST_GAP = 0.27            # IGDB allows 4 requests a second
MARKS = ('want', 'skip')


def plain(text: str) -> str:
    """A name reduced to what should match: no tags, accents, articles or punctuation."""
    text = unicodedata.normalize('NFD', text or '').encode('ascii', 'ignore').decode().lower()
    text = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', text).replace('&', ' and ')
    text = re.sub(r'\b(the|a|an)\b', ' ', text)
    return re.sub(r'[^a-z0-9]+', '', text)


def clean_name(name: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', name or '')).strip()


def _type_of(game: Dict) -> Optional[int]:
    value = game.get('game_type')
    return value.get('id') if isinstance(value, dict) else value


def choose_match(results: List[Dict], name: str, platform_id: Optional[int]):
    """(game, how) for the search result that is this game, or (None, None).
    how: 'exact' (same name, alternative names included) or 'loose' (one name
    inside the other). The system's platform and original releases are
    preferred; fan hacks are only taken when nothing else has the name."""
    wanted = plain(name)
    if not wanted:
        return None, None
    best, best_score, best_how = None, 0, None
    for position, game in enumerate(results):
        names = [game.get('name') or ''] + [a.get('name') or '' for a in game.get('alternative_names') or [] if isinstance(a, dict)]
        plains = [plain(n) for n in names if n]
        if wanted in plains:
            how, score = 'exact', 100
        elif len(wanted) >= 6 and any(p and (wanted in p or (len(p) >= 6 and p in wanted)) for p in plains[:1]):
            how, score = 'loose', 40
        else:
            continue
        # Being on this system counts for more than the name being exactly the
        # same: "Aladdin" on the Master System is IGDB's "Disney's Aladdin" for
        # that system, not the LCD handheld that also goes by plain "Aladdin"
        if platform_id and platform_id in (game.get('platforms') or []):
            score += 70
        kind = _type_of(game)
        if kind in HACK_TYPES:
            score -= 60
        elif kind == MAIN:
            score += 5
        score -= position   # IGDB's own order breaks ties
        if score > best_score:
            best, best_score, best_how = game, score, how
    return best, best_how


class SeriesIndex:
    def __init__(self, path: Path, igdb, platform_id_of: Callable[[str], Optional[int]]):
        self.path = Path(path)
        self.igdb = igdb
        self.platform_id_of = platform_id_of
        self._lock = threading.RLock()
        self._request_lock = threading.Lock()
        self._last_request = 0.0
        # 'people' holds each person's own marks and skipped platforms once login is on
        self._data = {'games': {}, 'series': {}, 'marks': {}, 'skipped_platforms': {}, 'people': {}}
        self.progress = {'running': False, 'done': 0, 'total': 0, 'step': '', 'error': None, 'finished': None}
        # Present while a library match is under way, so one a restart cut short starts again
        self.marker = self.path.with_name('series-running.json')
        try:
            if self.path.is_file():
                loaded = json.loads(self.path.read_text())
                for key in self._data:
                    if isinstance(loaded.get(key), dict):
                        self._data[key] = loaded[key]
        except (OSError, ValueError) as e:
            logger.warning(f"Couldn't read {self.path}: {e}")

    # ------------------------------------------------------------------
    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(f".{self.path.name}.part")
            tmp.write_text(json.dumps(self._data))
            tmp.replace(self.path)
        except OSError as e:
            logger.warning(f"Couldn't write {self.path}: {e}")

    def _request(self, query: str) -> List[Dict]:
        """One IGDB games query, keeping under its rate limit."""
        with self._request_lock:
            wait = REQUEST_GAP - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                return self.igdb._make_request('games', query)
            finally:
                self._last_request = time.time()

    @property
    def configured(self) -> bool:
        return self.igdb.configured

    # ------------------------------------------------------------------
    # Matching a library game to IGDB
    # ------------------------------------------------------------------
    def _record_for(self, game: Dict, how: str) -> Dict:
        group, kind = None, None
        for field, prefix in (('collections', 'c'), ('franchises', 'f')):
            groups = [g for g in game.get(field) or [] if isinstance(g, dict) and g.get('id')]
            if groups:
                # A game can be in several ("Disney" and "Disney's Aladdin"): the
                # one named in the game's own title is the closer fit
                title = plain(game.get('name') or '')
                named = [g for g in groups if plain(g.get('name') or '') and plain(g.get('name') or '') in title]
                group, kind = (max(named, key=lambda g: len(plain(g['name']))) if named else groups[0]), prefix
                break
        series_key = f"{kind}{group['id']}" if group else None
        if series_key:
            with self._lock:
                entry = self._data['series'].setdefault(series_key, {})
                entry.setdefault('name', group.get('name') or 'Series')
                entry.setdefault('kind', 'series' if kind == 'c' else 'franchise')
        # A port or a special edition counts as having the game it's a version of
        owns = [game['id']] + [game[f] for f in ('parent_game', 'version_parent') if isinstance(game.get(f), int)]
        return {'id': game['id'], 'name': game.get('name'), 'how': how, 'series': series_key, 'owns': owns}

    def search(self, name: str, system: Optional[str]) -> List[Dict]:
        """IGDB's candidates for a name: on the system's platform first, then anywhere."""
        text = clean_name(name).replace('"', '').replace('\\', '')
        if not text:
            return []
        platform_id = self.platform_id_of(system) if system else None
        results, seen = [], set()
        for where in ([f' where platforms = ({platform_id});'] if platform_id else []) + ['']:
            for game in self._request(f'search "{text}"; fields {MATCH_FIELDS};{where} limit 15;'):
                if game.get('id') not in seen:
                    seen.add(game.get('id'))
                    results.append(game)
            # A match on the system's own platform is the one: no need to look wider
            if results and where and choose_match(results, name, platform_id)[0]:
                break
        return results

    def match(self, key: str, system: str, name: str, force: bool = False) -> Dict:
        """The game's record, looked up on IGDB if it hasn't been (or its name
        has changed since). A manual match is kept until it's cleared."""
        with self._lock:
            record = self._data['games'].get(key)
        if record and not force and (record.get('how') == 'manual' or record.get('looked') == plain(name)):
            return record
        results = self.search(name, system)
        game, how = choose_match(results, name, self.platform_id_of(system))
        record = self._record_for(game, how) if game else {'id': None, 'how': 'none', 'series': None, 'owns': []}
        record['looked'] = plain(name)
        record['at'] = time.time()
        with self._lock:
            self._data['games'][key] = record
            self._save()
        return record

    def set_match(self, key: str, igdb_id: Optional[int]) -> Dict:
        """Match a game by hand (or, with no id, forget its match so it's looked up again)."""
        if not igdb_id:
            with self._lock:
                self._data['games'].pop(key, None)
                self._save()
            return {}
        found = self._request(f'fields {MATCH_FIELDS}; where id = {int(igdb_id)};')
        if not found:
            raise ValueError("IGDB has no game with that number")
        record = self._record_for(found[0], 'manual')
        with self._lock:
            self._data['games'][key] = record
            self._save()
        return record

    def game_moved(self, old_key: str, new_key: Optional[str]):
        with self._lock:
            record = self._data['games'].pop(old_key, None)
            if record and new_key:
                self._data['games'][new_key] = record
            if record:
                self._save()

    # ------------------------------------------------------------------
    # A series' games
    # ------------------------------------------------------------------
    def series_games(self, series_key: str, refresh: bool = False) -> Optional[Dict]:
        """{name, kind, games: [...]} for a series, fetched from IGDB when it
        hasn't been lately. None for a series nothing here refers to."""
        with self._lock:
            entry = self._data['series'].get(series_key)
        if entry is None:
            return None
        if not refresh and 'games' in entry and time.time() - entry.get('fetched', 0) < SERIES_MAX_AGE:
            return entry
        field = 'collections' if series_key[0] == 'c' else 'franchises'
        rows, offset = [], 0
        while True:
            page = self._request(f"fields {SERIES_FIELDS}; where {field} = ({int(series_key[1:])}); limit 500; offset {offset};")
            rows += page
            if len(page) < 500 or offset >= 1500:
                break
            offset += 500
        games = []
        for row in rows:
            kind = _type_of(row)
            if kind not in LISTED_TYPES or row.get('version_parent'):
                continue
            platforms = [p.get('abbreviation') or p.get('name') for p in row.get('platforms') or [] if isinstance(p, dict)]
            cover = row.get('cover') if isinstance(row.get('cover'), dict) else {}
            games.append({
                'id': row['id'], 'name': row.get('name') or '?', 'date': row.get('first_release_date'),
                'platforms': [p for p in platforms if p], 'type': TYPE_LABELS.get(kind), 'cover': cover.get('image_id'),
            })
        games.sort(key=lambda g: (g['date'] is None, g['date'] or 0, g['name']))
        with self._lock:
            entry = self._data['series'].setdefault(series_key, {})
            entry.update({'games': games, 'fetched': time.time()})
            self._save()
            return entry

    def _owned(self) -> Dict[int, List[str]]:
        """IGDB game id -> the library games that are it."""
        owned = {}
        with self._lock:
            for key, record in self._data['games'].items():
                for igdb_id in record.get('owns') or []:
                    owned.setdefault(igdb_id, []).append(key)
        return owned

    def _own(self, person: Optional[str]) -> Dict:
        """Where a person's marks and skipped platforms are kept; with no person
        (login off), the shared ones."""
        if person is None:
            return self._data
        own = self._data['people'].setdefault(person, {})
        own.setdefault('marks', {})
        own.setdefault('skipped_platforms', {})
        return own

    def adopt(self, person: str):
        """Give the shared want list to a person who has none of their own."""
        with self._lock:
            if (self._data['marks'] or self._data['skipped_platforms']) and person not in self._data['people']:
                self._data['people'][person] = {'marks': dict(self._data['marks']),
                                                'skipped_platforms': {k: list(v) for k, v in self._data['skipped_platforms'].items()}}
                self._save()

    def view(self, series_key: str, refresh: bool = False, person: Optional[str] = None) -> Optional[Dict]:
        """A series as the pages show it: every game with the library games
        that are it ("have"), and your mark on the ones that aren't."""
        entry = self.series_games(series_key, refresh)
        if entry is None:
            return None
        owned = self._owned()
        with self._lock:
            marks = dict(self._own(person)['marks'])
            skipped = list(self._own(person)['skipped_platforms'].get(series_key, []))
        games = []
        for game in entry.get('games', []):
            have = owned.get(game['id'], [])
            hidden = bool(game['platforms']) and all(p in skipped for p in game['platforms'])
            games.append({**game, 'have': have, 'mark': None if have else marks.get(str(game['id'])), 'platform_skipped': hidden and not have})
        counted = [g for g in games if g['have'] or not (g['mark'] == 'skip' or g['platform_skipped'])]
        return {
            'key': series_key, 'name': entry.get('name'), 'kind': entry.get('kind'), 'games': games,
            'have': sum(1 for g in games if g['have']), 'total': len(counted),
            'skipped_platforms': skipped, 'fetched': entry.get('fetched'),
        }

    # ------------------------------------------------------------------
    # Your marks
    # ------------------------------------------------------------------
    def set_mark(self, igdb_id: int, mark: Optional[str], person: Optional[str] = None):
        with self._lock:
            marks = self._own(person)['marks']
            if mark in MARKS:
                marks[str(int(igdb_id))] = mark
            else:
                marks.pop(str(int(igdb_id)), None)
            self._save()

    def skip_platform(self, series_key: str, platform: str, skip: bool, person: Optional[str] = None):
        with self._lock:
            skipped = self._own(person)['skipped_platforms']
            current = [p for p in skipped.get(series_key, []) if p != platform]
            if skip:
                current.append(platform)
            if current:
                skipped[series_key] = current
            else:
                skipped.pop(series_key, None)
            self._save()

    # ------------------------------------------------------------------
    # The whole library
    # ------------------------------------------------------------------
    def overview(self, person: Optional[str] = None) -> Dict:
        """Every series the library has a game from (and whose list has been
        fetched), most complete first, and the games marked as wanted."""
        with self._lock:
            marks = dict(self._own(person)['marks'])
            keys = [k for k, s in self._data['series'].items() if 'games' in s]
            in_use = {r.get('series') for r in self._data['games'].values() if r.get('series')}
            matched = sum(1 for r in self._data['games'].values() if r.get('id'))
            unmatched = sum(1 for r in self._data['games'].values() if not r.get('id'))
        series, wanted = [], []
        for key in keys:
            if key not in in_use:
                continue
            view = self.view(key, person=person)
            if not view or not view['have']:
                continue
            series.append({k: view[k] for k in ('key', 'name', 'kind', 'have', 'total')})
            for game in view['games']:
                if game['mark'] == 'want':
                    wanted.append({**{k: game[k] for k in ('id', 'name', 'date', 'platforms', 'type', 'cover')}, 'series': view['name'], 'series_key': key})
        series.sort(key=lambda s: (-(s['have'] / s['total'] if s['total'] else 0), s['name'] or ''))
        wanted.sort(key=lambda g: (g['series'] or '', g['date'] or 0))
        with self._lock:
            not_found = sorted(k for k, r in self._data['games'].items() if not r.get('id'))
        return {'series': series, 'wanted': wanted, 'matched': matched, 'unmatched': unmatched, 'unmatched_games': not_found,
                'waiting': len([k for k in in_use if k not in keys]), 'marks': len(marks)}

    def interrupted(self) -> Optional[Dict]:
        """{redo, started} of a library match a restart cut short, or None."""
        try:
            return json.loads(self.marker.read_text()) if self.marker.is_file() else None
        except (OSError, ValueError):
            return {'redo': False, 'started': 0}

    def run(self, library: List[Dict], redo: bool = False, started: Optional[float] = None):
        """Match every library game ({key, system, name}) that hasn't been, then
        fetch the list of every series they belong to. Meant for a background
        thread. `redo` looks every game up again; `started` is when that began,
        so a run picked up after a restart doesn't redo the ones already done."""
        with self._lock:
            if self.progress['running']:
                return
            self.progress = {'running': True, 'done': 0, 'total': len(library), 'step': 'Matching games', 'error': None, 'finished': None}
        started = started or time.time()
        try:
            self.marker.write_text(json.dumps({'redo': redo, 'started': started}))
        except OSError:
            pass
        try:
            for game in library:
                with self._lock:
                    done_at = (self._data['games'].get(game['key']) or {}).get('at', 0)
                self.match(game['key'], game['system'], game['name'], force=redo and done_at < started)
                self.progress['done'] += 1
            # Drop records for games that are gone
            keys = {g['key'] for g in library}
            with self._lock:
                gone = [k for k in self._data['games'] if k not in keys]
                for key in gone:
                    del self._data['games'][key]
                in_use = sorted({r.get('series') for r in self._data['games'].values() if r.get('series')})
                if gone:
                    self._save()
            self.progress.update({'step': 'Fetching each series', 'done': 0, 'total': len(in_use)})
            for key in in_use:
                self.series_games(key)
                self.progress['done'] += 1
        except Exception as e:   # IGDB down, keys wrong...: say so and stop
            logger.exception("Series matching stopped")
            self.progress['error'] = str(e)
        finally:
            self.progress.update({'running': False, 'finished': time.time()})
            try:
                self.marker.unlink()
            except OSError:
                pass
