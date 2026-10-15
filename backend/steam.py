"""
Steam store integration for PC games: search, store page details and library
artwork, from Valve's own public endpoints. No account needed.
"""

import html
import logging
import re
import time
from typing import Any, Dict, List, Optional

import requests

from backend.name_style import style_name
from backend.scraper import text_date_to_es

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r'<[^>]+>')
# Store category ids: 2 = Single-player, 1 = Multi-player, 9 = Co-op
_SINGLE, _MULTI = {2}, {1, 9, 24, 27, 36, 37, 38, 39, 47, 48, 49}


class SteamError(Exception):
    """A Steam request failed; the message is safe to show in the UI."""


def _plain(text: str) -> str:
    return html.unescape(_TAG_RE.sub('', text or '')).strip()


class SteamAPI:
    STORE_URL = "https://store.steampowered.com/api"
    ITEMS_URL = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
    ASSET_URL = "https://shared.steamstatic.com/store_item_assets"

    def __init__(self):
        self.session = requests.Session()

    def _get(self, url: str, params: Dict[str, Any]) -> Any:
        response = None
        for attempt in range(2):
            try:
                response = self.session.get(url, params=params, timeout=(10, 30))
            except requests.RequestException as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise SteamError(f"Couldn't reach Steam: {e}")
            if response.status_code >= 500 and attempt == 0:
                time.sleep(1)
                continue
            break
        if response.status_code == 429:
            raise SteamError("Steam rate limit hit (about 200 requests per 5 minutes). Wait a few minutes and retry.")
        if response.status_code != 200:
            logger.warning(f"Steam {url}: HTTP {response.status_code}: {response.text[:200]}")
            raise SteamError(f"Steam returned HTTP {response.status_code}.")
        try:
            return response.json()
        except ValueError:
            raise SteamError("Steam returned a response that isn't JSON.")

    def search_game(self, game_name: str) -> List[Dict]:
        """Store search. Returns raw items (possibly empty). Raises SteamError."""
        data = self._get(f"{self.STORE_URL}/storesearch/", {'term': game_name, 'l': 'english', 'cc': 'US'})
        return [item for item in (data or {}).get('items') or [] if item.get('type') == 'app' and item.get('id')]

    def get_game_info(self, app_id: Any) -> Dict:
        """One app's store details, with its artwork paths under 'assets'. Raises SteamError."""
        if not str(app_id).isdigit():
            raise SteamError("That isn't a Steam app ID.")
        data = self._get(f"{self.STORE_URL}/appdetails", {'appids': app_id, 'l': 'english'})
        entry = (data or {}).get(str(app_id)) or {}
        if not entry.get('success') or not entry.get('data'):
            raise SteamError("Steam has no store page for that app (it may be delisted or region-locked).")
        details = entry['data']
        details['assets'] = self._assets(app_id)
        return details

    def _assets(self, app_id: Any) -> Dict[str, str]:
        """{asset name: url} for the app's library artwork. Newer apps keep these
        under changing paths, which only this endpoint lists."""
        request = ('{"ids":[{"appid":%d}],"context":{"language":"english","country_code":"US"},'
                   '"data_request":{"include_assets":true}}') % int(app_id)
        try:
            data = self._get(self.ITEMS_URL, {'input_json': request})
            item = ((data.get('response') or {}).get('store_items') or [{}])[0]
            assets = item.get('assets') or {}
        except (SteamError, AttributeError, IndexError) as e:
            logger.warning(f"Steam artwork list for {app_id} failed: {e}")
            assets = {}
        url_format = assets.get('asset_url_format') or f"steam/apps/{app_id}/${{FILENAME}}"
        urls = {}
        for name in ('library_capsule_2x', 'library_capsule', 'library_hero_2x', 'library_hero', 'header'):
            if assets.get(name):
                urls[name] = f"{self.ASSET_URL}/{url_format.replace('${FILENAME}', assets[name])}"
        # The logo isn't listed, but sits at a fixed name for most apps
        logo = f"{self.ASSET_URL}/steam/apps/{app_id}/logo.png"
        try:
            if self.session.head(logo, timeout=(5, 15)).status_code == 200:
                urls['logo'] = logo
        except requests.RequestException:
            pass
        return urls

    def summarize_search_result(self, item: Dict) -> Dict[str, Any]:
        """Short form of a search hit for the results list."""
        return {
            'id': item.get('id'),
            'name': item.get('name'),
            'cover_url': item.get('tiny_image'),
            'platform_names': 'Steam',
            'year': None,
            'regions': [],
            'is_hack': False,
        }

    def extract_media(self, details: Dict) -> Dict[str, str]:
        """{label: url}: library cover, hero and logo (named by the folder they
        suit), the store header and up to 3 screenshots."""
        assets = details.get('assets') or {}
        media = {}
        cover = assets.get('library_capsule_2x') or assets.get('library_capsule')
        if cover:
            media['box2d'] = cover
        if assets.get('logo'):
            media['wheel'] = assets['logo']
        hero = assets.get('library_hero_2x') or assets.get('library_hero')
        if hero:
            media['fanart'] = hero
        for i, shot in enumerate((details.get('screenshots') or [])[:3], start=1):
            if isinstance(shot, dict) and shot.get('path_full'):
                media[f'screenshot_{i}'] = shot['path_full']
        header = assets.get('header') or details.get('header_image')
        if header:
            media['header'] = header
        return media

    def extract_game_data(self, details: Dict) -> Dict[str, Any]:
        """Convert an app's store details to gamelist fields plus a `media` dict."""
        categories = {c.get('id') for c in details.get('categories') or [] if isinstance(c, dict)}
        players = ''
        if categories & _SINGLE and not categories & _MULTI:
            players = '1'

        rating = ''
        score = (details.get('metacritic') or {}).get('score')
        if isinstance(score, (int, float)):
            rating = round(score / 100.0, 2)  # Metacritic rates out of 100

        genres = [g.get('description') for g in details.get('genres') or [] if isinstance(g, dict) and g.get('description')]
        return {
            'name': style_name(details.get('name') or ''),
            'desc': _plain(details.get('short_description') or ''),
            'genre': ', '.join(genres),
            'developer': ', '.join(details.get('developers') or []),
            'publisher': ', '.join(details.get('publishers') or []),
            'releasedate': text_date_to_es((details.get('release_date') or {}).get('date') or ''),
            'players': players,
            'rating': rating,
            'media': self.extract_media(details),
        }
