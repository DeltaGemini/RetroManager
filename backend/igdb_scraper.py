"""
IGDB (Internet Game Database) API integration for metadata scraping
https://api-docs.igdb.com/
"""

import time
import requests
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone

from backend.name_style import style_name
from backend.systems import igdb_platform_id

logger = logging.getLogger(__name__)


class IGDBError(Exception):
    """An IGDB request failed; the message is safe to show in the UI."""


class IGDBAuth:
    """Handle OAuth2 authentication for IGDB"""

    TOKEN_URL = "https://id.twitch.tv/oauth2/token"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = None

    def invalidate(self):
        self.access_token = None
        self.token_expiry = None

    def get_token(self) -> str:
        """Get a valid access token, refreshing if needed. Raises IGDBError."""
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token
        if not (self.client_id and self.client_secret):
            raise IGDBError("IGDB isn't set up: add IGDB_CLIENT_ID and IGDB_CLIENT_SECRET to .env (see .env.example).")

        try:
            response = requests.post(self.TOKEN_URL, params={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials',
            }, timeout=10)
        except requests.RequestException as e:
            raise IGDBError(f"Couldn't reach Twitch to log in to IGDB: {e}")

        if response.status_code != 200:
            logger.error(f"IGDB token request failed: HTTP {response.status_code}: {response.text[:200]}")
            raise IGDBError("Twitch rejected the IGDB credentials (IGDB_CLIENT_ID / IGDB_CLIENT_SECRET).")

        data = response.json()
        self.access_token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)
        # Refresh 5 minutes early
        self.token_expiry = datetime.now() + timedelta(seconds=max(expires_in - 300, 60))
        logger.info("IGDB token acquired")
        return self.access_token


def _image_url(image: Any, size: str) -> Optional[str]:
    """Build a full-size image URL from an expanded IGDB image object."""
    if not isinstance(image, dict) or not image.get('image_id'):
        return None
    return f"https://images.igdb.com/igdb/image/upload/{size}/{image['image_id']}.jpg"


def _to_es_date(timestamp: Any) -> str:
    """Unix timestamp -> EmulationStation's "YYYYMMDDT000000"."""
    if not isinstance(timestamp, (int, float)):
        return ''
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime('%Y%m%dT000000')


def _escape(text: str) -> str:
    """Escape a string for an Apicalypse "..." literal."""
    return text.replace('\\', '\\\\').replace('"', '\\"')


# IGDB game_type ids for fan-made variants: 5 = Mod, 12 = Fork
HACK_GAME_TYPES = {5, 12}


class IGDBAPI:
    """Client for IGDB API"""

    BASE_URL = "https://api.igdb.com/v4"

    # Expanded so covers, screenshots and artworks come back as objects with
    # image ids rather than bare numeric ids that need another request each
    SEARCH_FIELDS = 'name, first_release_date, cover.image_id, platforms.name, genres.name, game_type'
    DETAIL_FIELDS = (
        'name, summary, first_release_date, total_rating, rating, '
        'cover.image_id, screenshots.image_id, artworks.image_id, '
        'genres.name, platforms.name, '
        'involved_companies.developer, involved_companies.publisher, involved_companies.company.name'
    )

    def __init__(self, client_id: str, client_secret: str):
        self.auth = IGDBAuth(client_id, client_secret)
        self.session = requests.Session()

    def _make_request(self, endpoint: str, query: str) -> List[Dict]:
        """POST an Apicalypse query and return the result list, or raise IGDBError."""
        url = f"{self.BASE_URL}/{endpoint}"
        logger.debug(f"IGDB request: {endpoint}: {query}")

        response = None
        for attempt in range(2):
            headers = {
                'Client-ID': self.auth.client_id,
                'Authorization': f'Bearer {self.auth.get_token()}',
            }
            try:
                response = self.session.post(url, data=query.encode('utf-8'), headers=headers, timeout=(10, 30))
            except requests.RequestException as e:
                if attempt == 0:
                    logger.warning(f"IGDB {endpoint} failed ({e}), retrying")
                    time.sleep(1)
                    continue
                raise IGDBError(f"Couldn't reach IGDB: {e}")

            if response.status_code == 401 and attempt == 0:
                # Token revoked or expired early
                self.auth.invalidate()
                continue
            if response.status_code == 429 and attempt == 0:
                # IGDB allows 4 requests per second
                time.sleep(1)
                continue
            if response.status_code >= 500 and attempt == 0:
                time.sleep(1)
                continue
            break

        if response.status_code != 200:
            logger.error(f"IGDB {endpoint}: HTTP {response.status_code}: {response.text[:300]}")
            if response.status_code == 429:
                raise IGDBError("IGDB rate limit hit. Wait a second and retry.")
            raise IGDBError(f"IGDB returned HTTP {response.status_code}.")

        try:
            data = response.json()
        except ValueError:
            raise IGDBError("IGDB returned a response that isn't JSON.")
        return data if isinstance(data, list) else [data]

    def search_game(self, game_name: str, system_name: Optional[str] = None) -> List[Dict]:
        """
        Search IGDB, filtered to the system's platform when it's known.
        Returns raw game objects (possibly empty). Raises IGDBError.
        """
        platform_id = igdb_platform_id(system_name)
        query = f'search "{_escape(game_name)}"; fields {self.SEARCH_FIELDS};'
        if platform_id:
            query += f' where platforms = ({platform_id});'
        query += ' limit 20;'
        results = self._make_request('games', query)

        if not results and platform_id:
            # Platform data on IGDB is incomplete for some older games
            logger.debug(f"No IGDB results on platform {platform_id}, retrying without the filter")
            results = self._make_request('games', f'search "{_escape(game_name)}"; fields {self.SEARCH_FIELDS}; limit 20;')
        return results

    def get_game_info(self, game_id: int) -> Optional[Dict]:
        """Fetch one game with everything needed for metadata and media. Raises IGDBError."""
        results = self._make_request('games', f'fields {self.DETAIL_FIELDS}; where id = {int(game_id)};')
        return results[0] if results else None

    def summarize_search_result(self, game: Dict) -> Dict[str, Any]:
        """Short form of a search hit for the results list."""
        platforms = [p.get('name') for p in game.get('platforms') or [] if isinstance(p, dict) and p.get('name')]
        releasedate = _to_es_date(game.get('first_release_date'))
        game_type = game.get('game_type')
        if isinstance(game_type, dict):
            game_type = game_type.get('id')
        return {
            'id': game.get('id'),
            'name': game.get('name'),
            'cover_url': _image_url(game.get('cover'), 't_cover_big'),
            'platform_names': ', '.join(platforms) if platforms else 'Unknown',
            'releasedate': releasedate,
            'year': releasedate[:4] or None,
            'regions': [],
            'is_hack': game_type in HACK_GAME_TYPES,
        }

    def extract_media(self, game: Dict) -> Dict[str, str]:
        """{label: url} for the cover, up to 3 screenshots and up to 2 artworks."""
        media = {}
        cover = _image_url(game.get('cover'), 't_cover_big')
        if cover:
            media['cover'] = cover
        for i, shot in enumerate((game.get('screenshots') or [])[:3], start=1):
            url = _image_url(shot, 't_screenshot_big')
            if url:
                media[f'screenshot_{i}'] = url
        for i, art in enumerate((game.get('artworks') or [])[:2], start=1):
            url = _image_url(art, 't_1080p')
            if url:
                media[f'artwork_{i}'] = url
        return media

    def extract_game_data(self, game: Dict) -> Dict[str, Any]:
        """Convert a detailed IGDB game to gamelist fields plus a `media` dict."""
        developers, publishers = [], []
        for involvement in game.get('involved_companies') or []:
            if not isinstance(involvement, dict):
                continue
            company = (involvement.get('company') or {}).get('name')
            if not company:
                continue
            if involvement.get('developer'):
                developers.append(company)
            if involvement.get('publisher'):
                publishers.append(company)

        genres = [g.get('name') for g in game.get('genres') or [] if isinstance(g, dict) and g.get('name')]

        rating = ''
        score = game.get('total_rating') or game.get('rating')
        if isinstance(score, (int, float)):
            rating = round(score / 100.0, 2)  # IGDB rates out of 100

        return {
            'name': style_name(game.get('name') or ''),
            'desc': game.get('summary') or '',
            'genre': ', '.join(genres),
            'developer': ', '.join(developers),
            'publisher': ', '.join(publishers),
            'releasedate': _to_es_date(game.get('first_release_date')),
            'rating': rating,
            'media': self.extract_media(game),
        }
