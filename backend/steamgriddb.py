"""
SteamGridDB (steamgriddb.com) integration: community-made covers, heroes and
logos for games on any system. Artwork only; it has no descriptions.
https://www.steamgriddb.com/api/v2
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from backend.name_style import style_name

logger = logging.getLogger(__name__)

# How many of each kind are offered (best-voted first)
MAX_GRIDS, MAX_HEROES, MAX_LOGOS = 3, 2, 2


class SteamGridDBError(Exception):
    """A SteamGridDB request failed; the message is safe to show in the UI."""


def _to_es_date(timestamp: Any) -> str:
    if not isinstance(timestamp, (int, float)) or timestamp <= 0:
        return ''
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime('%Y%m%dT000000')


class SteamGridDBAPI:
    BASE_URL = "https://www.steamgriddb.com/api/v2"

    def __init__(self, api_key: str):
        self.api_key = (api_key or '').strip()
        self.session = requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _make_request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET a path and return its `data`, or raise SteamGridDBError."""
        if not self.configured:
            raise SteamGridDBError("Add your SteamGridDB API key in Tools > Settings.")
        headers = {'Authorization': f'Bearer {self.api_key}'}
        response = None
        for attempt in range(2):
            try:
                response = self.session.get(f"{self.BASE_URL}/{path}", params=params, headers=headers, timeout=(10, 30))
            except requests.RequestException as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise SteamGridDBError(f"Couldn't reach SteamGridDB: {e}")
            if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                time.sleep(2)
                continue
            break

        if response.status_code in (401, 403):
            raise SteamGridDBError("SteamGridDB rejected the API key. Check it in Tools > Settings.")
        if response.status_code == 404:
            return []
        if response.status_code == 429:
            raise SteamGridDBError("SteamGridDB rate limit hit. Wait a moment and retry.")
        if response.status_code != 200:
            logger.warning(f"SteamGridDB {path}: HTTP {response.status_code}: {response.text[:200]}")
            raise SteamGridDBError(f"SteamGridDB returned HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError:
            raise SteamGridDBError("SteamGridDB returned a response that isn't JSON.")
        if not body.get('success'):
            raise SteamGridDBError(f"SteamGridDB error: {'; '.join(body.get('errors') or ['unknown'])}")
        return body.get('data')

    def search_game(self, game_name: str) -> List[Dict]:
        """Search by name. Returns raw games (possibly empty). Raises SteamGridDBError."""
        return self._make_request(f"search/autocomplete/{quote(game_name, safe='')}") or []

    def get_game(self, game_id: Any) -> Optional[Dict]:
        """One game by its SteamGridDB id, or None if it doesn't exist."""
        if not str(game_id).isdigit():
            raise SteamGridDBError("That isn't a SteamGridDB game.")
        return self._make_request(f"games/id/{game_id}") or None

    def _images(self, kind: str, game_id: Any, params: Dict[str, Any], limit: int) -> List[str]:
        items = self._make_request(f"{kind}/game/{game_id}", params) or []
        return [item['url'] for item in items if isinstance(item, dict) and item.get('url')][:limit]

    def get_game_info(self, game_id: Any) -> Dict:
        """The game plus its best covers, heroes and logos. Raises SteamGridDBError."""
        game = self.get_game(game_id)
        if not game:
            raise SteamGridDBError("SteamGridDB returned no data for that game.")
        static = {'types': 'static', 'nsfw': 'false'}
        return {
            **game,
            # Portrait covers, the shape of a game box
            'grids': self._images('grids', game_id, {**static, 'dimensions': '600x900,342x482,660x930'}, MAX_GRIDS),
            'heroes': self._images('heroes', game_id, static, MAX_HEROES),
            'logos': self._images('logos', game_id, static, MAX_LOGOS),
        }

    def summarize_search_result(self, game: Dict, hash_match: bool = False) -> Dict[str, Any]:
        """Short form of a search hit for the results list."""
        releasedate = _to_es_date(game.get('release_date'))
        return {
            'id': game.get('id'),
            'name': game.get('name'),
            'cover_url': None,
            'platform_names': 'SteamGridDB artwork',
            'year': releasedate[:4] or None,
            'regions': [],
            'is_hack': False,
            'hash_match': hash_match,
        }

    def extract_game_data(self, game: Dict) -> Dict[str, Any]:
        """Convert get_game_info's answer to gamelist fields plus a `media` dict."""
        media = {}
        for label, urls in (('grid', game.get('grids')), ('hero', game.get('heroes')), ('logo', game.get('logos'))):
            for i, url in enumerate(urls or [], start=1):
                media[f'{label}_{i}'] = url
        return {
            'name': style_name(game.get('name') or ''),
            'releasedate': _to_es_date(game.get('release_date')),
            'media': media,
        }
