"""
TheGamesDB (thegamesdb.net) integration: descriptions, release dates, players,
developer, publisher and genres, with box art, fan art, screenshots, title
screens and clear logos, for most systems.
https://api.thegamesdb.net/ (API v1; a key is asked for on its forums)

Each request counts against the key's monthly allowance, so the lists that turn
its genre, developer and publisher numbers into names are fetched once and kept
in the data folder for a month.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from backend.name_style import style_name
from backend.systems import thegamesdb_platform_id

logger = logging.getLogger(__name__)

# How many extra pictures of a kind are offered beside the first
MAX_EXTRA = 2
NAMES_MAX_AGE = 30 * 86400
GAME_FIELDS = 'players,publishers,genres,overview,rating,platform'


class TheGamesDBError(Exception):
    """A TheGamesDB request failed; the message is safe to show in the UI."""


def _to_es_date(date: Any) -> str:
    """"1991-11-21" -> "19911121T000000"."""
    parts = str(date or '').split('-')
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return ''
    return f"{parts[0]:0>4}{parts[1]:0>2}{parts[2]:0>2}T000000"


class TheGamesDBAPI:
    BASE_URL = "https://api.thegamesdb.net/v1"

    def __init__(self, api_key: str, data_dir=None):
        self.api_key = (api_key or '').strip()
        self.session = requests.Session()
        self.names_file = Path(data_dir) / 'thegamesdb-names.json' if data_dir else None
        self._names = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _make_request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict:
        """GET a path and return the whole answer, or raise TheGamesDBError."""
        if not self.configured:
            raise TheGamesDBError("Add your TheGamesDB API key in Tools > Settings.")
        response = None
        for attempt in range(2):
            try:
                response = self.session.get(f"{self.BASE_URL}/{path}", params={'apikey': self.api_key, **(params or {})}, timeout=(10, 30))
            except requests.RequestException as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise TheGamesDBError(f"Couldn't reach TheGamesDB: {e}")
            if response.status_code in (500, 502, 503, 504) and attempt == 0:
                time.sleep(2)
                continue
            break
        if response.status_code in (401, 403):
            # (it answers 403 both for a key it doesn't know and for one that's used up)
            raise TheGamesDBError("TheGamesDB turned the API key down: it's wrong, or this month's allowance is used up. Check it in Tools > Settings.")
        if response.status_code == 429:
            raise TheGamesDBError("TheGamesDB rate limit hit. Wait a moment and retry.")
        if response.status_code != 200:
            logger.warning(f"TheGamesDB {path}: HTTP {response.status_code}: {response.text[:200]}")
            raise TheGamesDBError(f"TheGamesDB returned HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError:
            raise TheGamesDBError("TheGamesDB returned a response that isn't JSON.")
        if not isinstance(body, dict) or not isinstance(body.get('data'), dict):
            raise TheGamesDBError("TheGamesDB returned a response without any data.")
        return body

    # --- Names for its genre, developer and publisher numbers ---

    def _name_lists(self) -> Dict[str, Dict[str, str]]:
        """{"genres": {id: name}, "developers": {...}, "publishers": {...}}, from the
        kept copy while that's under a month old. A list that can't be fetched is
        left empty: the names are missed, not the scrape."""
        if self._names is None and self.names_file:
            try:
                kept = json.loads(self.names_file.read_text())
                if time.time() - kept.get('fetched', 0) < NAMES_MAX_AGE:
                    self._names = kept
            except (OSError, ValueError):
                pass
        if self._names is None:
            names = {'fetched': time.time()}
            for kind, path in (('genres', 'Genres'), ('developers', 'Developers'), ('publishers', 'Publishers')):
                try:
                    listed = self._make_request(path)['data'].get(kind) or {}
                    names[kind] = {str(key): entry.get('name') for key, entry in listed.items() if isinstance(entry, dict) and entry.get('name')}
                except (TheGamesDBError, AttributeError) as e:
                    logger.warning(f"TheGamesDB: couldn't fetch its {kind}: {e}")
                    names[kind] = {}
            self._names = names
            if self.names_file and all(names.get(kind) for kind in ('genres', 'developers', 'publishers')):
                try:
                    self.names_file.write_text(json.dumps(names))
                except OSError as e:
                    logger.warning(f"TheGamesDB: couldn't keep its names: {e}")
        return self._names

    def _named(self, kind: str, ids: Any) -> str:
        names = self._name_lists().get(kind) or {}
        return ', '.join(names[str(i)] for i in (ids or []) if str(i) in names)

    # --- Games ---

    @staticmethod
    def _games(body: Dict) -> List[Dict]:
        games = body['data'].get('games') or []
        return [g for g in (games.values() if isinstance(games, dict) else games) if isinstance(g, dict)]

    @staticmethod
    def _included(body: Dict, kind: str) -> Dict:
        included = (body.get('include') or {}).get(kind) or {}
        return included if isinstance(included, dict) else {}

    def search_game(self, game_name: str, system_name: Optional[str] = None) -> List[Dict]:
        """Search by name, on the system's platform when RetroManager knows it.
        Returns games with `_cover` (a small front box, or None) and `_platform`
        (its name). Raises TheGamesDBError."""
        params = {'name': game_name, 'fields': 'platform', 'include': 'boxart,platform'}
        platform = thegamesdb_platform_id(system_name)
        if platform:
            params['filter[platform]'] = platform
        body = self._make_request('Games/ByGameName', params)
        boxart, platforms = self._included(body, 'boxart'), self._included(body, 'platform')
        base = (boxart.get('base_url') or {}).get('small') or (boxart.get('base_url') or {}).get('original') or ''
        covers = boxart.get('data') or {}
        platform_names = platforms.get('data') or platforms
        games = self._games(body)
        for game in games:
            front = next((p for p in covers.get(str(game.get('id'))) or [] if isinstance(p, dict) and p.get('side') == 'front' and p.get('filename')), None)
            game['_cover'] = base + front['filename'] if front and base else None
            game['_platform'] = ((platform_names.get(str(game.get('platform'))) or {}).get('name') if isinstance(platform_names, dict) else None) or 'TheGamesDB'
        return games

    def get_game_info(self, game_id: Any) -> Dict:
        """One game with its pictures (`_images`: {kind: [urls]}, the front box as
        "boxart" and the back as "boxback"). Raises TheGamesDBError."""
        if not str(game_id).isdigit():
            raise TheGamesDBError("That isn't a TheGamesDB game.")
        games = self._games(self._make_request('Games/ByGameID', {'id': game_id, 'fields': GAME_FIELDS}))
        if not games:
            raise TheGamesDBError("TheGamesDB returned no data for that game.")
        return {**games[0], '_images': self.get_images(game_id)}

    def get_images(self, game_id: Any) -> Dict[str, List[str]]:
        """A game's pictures, {kind: [urls]} (the front box as "boxart", the back
        as "boxback"); {} if they can't be had. Never raises."""
        images = {}
        try:
            data = self._make_request('Games/Images', {'games_id': game_id})['data']
            base = (data.get('base_url') or {}).get('original') or ''
            for picture in (data.get('images') or {}).get(str(game_id)) or []:
                if not isinstance(picture, dict) or not picture.get('filename') or not base:
                    continue
                kind = picture.get('type') or ''
                if kind == 'boxart' and picture.get('side') == 'back':
                    kind = 'boxback'
                images.setdefault(kind, []).append(base + picture['filename'])
        except TheGamesDBError as e:
            # The details are still worth having without the pictures
            logger.warning(f"TheGamesDB: no pictures for game {game_id}: {e}")
        return images

    def summarize_search_result(self, game: Dict) -> Dict[str, Any]:
        """Short form of a search hit for the results list."""
        return {
            'id': game.get('id'),
            'name': style_name(game.get('game_title') or ''),
            'cover_url': game.get('_cover'),
            'platform_names': game.get('_platform') or 'TheGamesDB',
            'year': str(game.get('release_date') or '')[:4] or None,
            'regions': [],
            'is_hack': False,
            'hash_match': False,
        }

    def extract_game_data(self, game: Dict) -> Dict[str, Any]:
        """Convert get_game_info's answer to gamelist fields plus a `media` dict.
        The first picture of each kind is named for the media folder it suits
        (so the Scrape popup assigns it there); further ones are numbered."""
        media = {}
        folders = (('boxart', 'box2d'), ('fanart', 'fanart'), ('screenshot', 'screenshot'), ('titlescreen', 'screenshottitle'),
                   ('clearlogo', 'wheel'), ('boxback', 'boxback'), ('banner', 'banner'))
        for kind, folder in folders:
            for i, url in enumerate((game.get('_images') or {}).get(kind) or []):
                if i == 0:
                    media[folder] = url
                elif i <= MAX_EXTRA:
                    media[f'{folder}_{i + 1}'] = url
        players = game.get('players')
        return {
            'name': style_name(game.get('game_title') or ''),
            'desc': (game.get('overview') or '').strip(),
            'releasedate': _to_es_date(game.get('release_date')),
            'developer': self._named('developers', game.get('developers')),
            'publisher': self._named('publishers', game.get('publishers')),
            'genre': self._named('genres', game.get('genres')),
            'players': str(players) if players else '',
            'media': media,
        }
