"""
Screenscraper.fr API integration for metadata scraping
https://www.screenscraper.fr/webapi2.php
"""

import time
import requests
import logging
from typing import Optional, List, Dict, Any

from backend.name_style import style_name

logger = logging.getLogger(__name__)


class ScreenscraperError(Exception):
    """A ScreenScraper request failed; the message is safe to show in the UI."""


class ScreenscraperNotFound(ScreenscraperError):
    """ScreenScraper answered, but has no game for the request."""


# HTTP status codes ScreenScraper uses to report problems
_HTTP_ERRORS = {
    400: "ScreenScraper rejected the request as malformed.",
    401: "ScreenScraper has closed the API to non-members because it's overloaded. Set SCREENSCRAPER_USER to scrape with your account, or try later.",
    403: "ScreenScraper rejected the developer credentials (SCREENSCRAPER_LOGIN / SCREENSCRAPER_PASSWORD).",
    404: "ScreenScraper found no matching game.",
    423: "ScreenScraper's API is fully closed right now. Try later.",
    426: "ScreenScraper has blocked this software name or version.",
    429: "ScreenScraper's thread limit was reached. Wait a moment and retry.",
    430: "ScreenScraper's daily quota is used up. Set SCREENSCRAPER_USER for a larger quota, or try tomorrow.",
    431: "ScreenScraper has blocked this account for too many failed requests today.",
}

# Statuses worth one retry (busy servers rather than bad input)
_RETRY_STATUSES = {429, 500, 502, 503, 504}

# ScreenScraper media type -> RetroManager media folder, in priority order
# (the first ScreenScraper type found wins for each folder)
MEDIA_TYPE_MAP = [
    ("box-2D", "box2d"),
    ("box-3D", "box3d"),
    ("box-2D-side", "boxside"),
    ("ss", "screenshot"),
    ("sstitle", "screenshottitle"),
    ("wheel-hd", "wheel"),
    ("wheel", "wheel"),
    ("fanart", "fanart"),
    ("mixrbv2", "mix"),
    ("mixrbv1", "mix"),
    ("video-normalized", "videos"),
    ("video", "videos"),
    ("manuel", "manuals"),
]

# Preferred regions for names, dates and media
REGION_ORDER = ["us", "wor", "eu", "ss", "uk", "jp"]


def _region_rank(region: Optional[str]) -> int:
    try:
        return REGION_ORDER.index(region)
    except ValueError:
        return len(REGION_ORDER)


def _pick_by_region(entries: Any) -> Optional[Dict]:
    """Pick the best entry from a list of {"region": ..., "text"/"url": ...} dicts."""
    if not isinstance(entries, list):
        return None
    candidates = [e for e in entries if isinstance(e, dict)]
    if not candidates:
        return None
    return min(candidates, key=lambda e: _region_rank(e.get("region")))


def _pick_by_language(entries: Any, language: str = "en") -> str:
    """Pick the text in `language` from a list of {"langue": ..., "text": ...} dicts."""
    if not isinstance(entries, list):
        return ""
    texts = [e for e in entries if isinstance(e, dict) and e.get("text")]
    for entry in texts:
        if entry.get("langue") == language:
            return entry["text"]
    return texts[0]["text"] if texts else ""


def _text(value: Any) -> str:
    """ScreenScraper wraps most scalars as {"id": ..., "text": ...}."""
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return str(value or "")


def to_es_date(date_text: str) -> str:
    """Convert "1991-08-13", "1991-08" or "1991" to EmulationStation's "19910813T000000"."""
    digits = "".join(ch for ch in (date_text or "") if ch.isdigit())
    if len(digits) < 4:
        return ""
    digits = (digits + "0101")[:8] if len(digits) == 4 else (digits + "01")[:8]
    return f"{digits}T000000"


class ScreenscraperAPI:
    """Client for Screenscraper.fr API"""

    BASE_URL = "https://www.screenscraper.fr/api2"
    SOFTNAME = "RetroManager"

    def __init__(self, dev_login: str, dev_password: str, dev_debug_password: Optional[str] = None,
                 user: Optional[str] = None, user_password: Optional[str] = None):
        self.dev_login = dev_login
        self.dev_password = dev_password
        self.dev_debug_password = dev_debug_password
        self.user = user
        self.user_password = user_password
        self.session = requests.Session()

    def _auth_params(self) -> Dict[str, str]:
        params = {
            'devid': self.dev_login,
            'devpassword': self.dev_password,
            'softname': self.SOFTNAME,
            'output': 'json',
        }
        if self.dev_debug_password:
            params['devdebugpassword'] = self.dev_debug_password
        if self.user and self.user_password:
            params['ssid'] = self.user
            params['sspassword'] = self.user_password
        return params

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict:
        """Call the API and return the parsed JSON, or raise ScreenscraperError."""
        if not (self.dev_login and self.dev_password):
            raise ScreenscraperError("ScreenScraper isn't set up: add SCREENSCRAPER_LOGIN and "
                                     "SCREENSCRAPER_PASSWORD to .env (see .env.example).")
        url = f"{self.BASE_URL}/{endpoint}"
        full_params = {**params, **self._auth_params()}
        logger.debug(f"ScreenScraper request: {endpoint} {params}")

        response = None
        for attempt in range(2):
            try:
                response = self.session.get(url, params=full_params, timeout=(10, 30))
            except requests.Timeout:
                if attempt == 0:
                    logger.warning(f"ScreenScraper {endpoint} timed out, retrying")
                    continue
                raise ScreenscraperError("ScreenScraper didn't respond within 30 seconds. It's often slow at busy times; try again.")
            except requests.RequestException as e:
                if attempt == 0:
                    logger.warning(f"ScreenScraper {endpoint} failed ({e}), retrying")
                    time.sleep(2)
                    continue
                raise ScreenscraperError(f"Couldn't reach ScreenScraper: {e}")

            if response.status_code in _RETRY_STATUSES and attempt == 0:
                logger.warning(f"ScreenScraper {endpoint} returned {response.status_code}, retrying")
                time.sleep(2)
                continue
            break

        if response.status_code != 200:
            message = _HTTP_ERRORS.get(response.status_code, f"ScreenScraper returned HTTP {response.status_code}.")
            logger.warning(f"ScreenScraper {endpoint}: HTTP {response.status_code}: {response.text[:200]}")
            if response.status_code == 404:
                raise ScreenscraperNotFound(message)
            raise ScreenscraperError(message)

        try:
            data = response.json()
        except ValueError:
            # Errors such as bad credentials come back as plain text with HTTP 200
            body = response.text.strip()[:200] or "empty response"
            logger.warning(f"ScreenScraper {endpoint} returned non-JSON: {body}")
            raise ScreenscraperError(f"ScreenScraper error: {body}")

        header_error = (data.get('header') or {}).get('error')
        if header_error:
            raise ScreenscraperError(f"ScreenScraper error: {header_error}")

        return data

    def search_game(self, game_name: str, system_id: Optional[int] = None) -> List[Dict]:
        """
        Search for a game. Returns a list of raw `jeu` objects (possibly empty).
        Raises ScreenscraperError on failure.
        """
        params = {'recherche': game_name}
        if system_id:
            params['systemeid'] = system_id

        data = self._make_request('jeuRecherche.php', params)
        jeux = (data.get('response') or {}).get('jeux') or []
        if isinstance(jeux, dict):
            jeux = [jeux]
        # A search with no matches returns [{}]
        return [j for j in jeux if isinstance(j, dict) and j.get('id')]

    def get_game_info(self, game_id: int, system_id: Optional[int] = None) -> Dict:
        """Fetch one game's raw `jeu` object. Raises ScreenscraperError on failure."""
        params = {'gameid': str(game_id)}
        if system_id:
            params['systemeid'] = str(system_id)
        data = self._make_request('jeuInfos.php', params)
        jeu = (data.get('response') or {}).get('jeu')
        if not jeu:
            raise ScreenscraperError("ScreenScraper returned no data for that game.")
        return jeu

    def identify_rom(self, rom_filename: str, system_id: Optional[int] = None, size: Optional[int] = None,
                     md5: Optional[str] = None) -> Dict:
        """Look a game up by its ROM file name (ScreenScraper matches it against its
        ROM database), and its MD5 checksum when given. Returns the raw `jeu`;
        raises ScreenscraperNotFound if unknown."""
        params = {'romtype': 'rom', 'romnom': rom_filename}
        if system_id:
            params['systemeid'] = str(system_id)
        if size:
            params['romtaille'] = str(size)
        if md5:
            params['md5'] = md5
        data = self._make_request('jeuInfos.php', params)
        jeu = (data.get('response') or {}).get('jeu')
        if not jeu or not jeu.get('id'):
            raise ScreenscraperNotFound("ScreenScraper doesn't know this ROM.")
        return jeu

    def summarize_search_result(self, jeu: Dict) -> Dict[str, Any]:
        """Short form of a search hit for the results list."""
        systeme = jeu.get('systeme') or {}
        name_entry = _pick_by_region(jeu.get('noms'))
        date_entry = _pick_by_region(jeu.get('dates'))
        media = self.extract_media(jeu)
        releasedate = date_entry.get('text') if date_entry else None
        regions = sorted({d.get('region') for d in jeu.get('dates') or [] if isinstance(d, dict) and d.get('region')},
                         key=_region_rank)
        name = name_entry.get('text') if name_entry else ''
        system_name = systeme.get('text') or ''
        return {
            'id': jeu.get('id'),
            'nom': name,
            'systemeid': systeme.get('id'),
            'systemenom': system_name,
            'image': media.get('box2d') or media.get('wheel') or media.get('screenshot'),
            'releasedate': releasedate,
            'year': releasedate[:4] if releasedate and releasedate[:4].isdigit() else None,
            'regions': regions,
            # ScreenScraper files ROM hacks under systems named "... Hacks"
            'is_hack': 'hack' in system_name.lower() or 'hack' in name.lower(),
            'jeu': jeu,  # full object, so game-info doesn't need another API call
        }

    def extract_media(self, jeu: Dict) -> Dict[str, str]:
        """Map a jeu's media list to {retromanager_folder: url}, best region first."""
        by_type: Dict[str, List[Dict]] = {}
        for item in jeu.get('medias') or []:
            if isinstance(item, dict) and item.get('url'):
                by_type.setdefault(item.get('type'), []).append(item)

        media: Dict[str, str] = {}
        for ss_type, folder in MEDIA_TYPE_MAP:
            if folder in media or ss_type not in by_type:
                continue
            best = _pick_by_region(by_type[ss_type])
            if best:
                media[folder] = best['url']
        return media

    def extract_game_data(self, jeu: Dict) -> Dict[str, Any]:
        """
        Convert a raw `jeu` object to gamelist fields plus a `media` dict.
        Dates use EmulationStation's format and ratings are 0-1.
        """
        if not jeu:
            return {}

        name_entry = _pick_by_region(jeu.get('noms'))
        date_entry = _pick_by_region(jeu.get('dates'))

        genre = ''
        for genre_entry in jeu.get('genres') or []:
            if isinstance(genre_entry, dict):
                genre = _pick_by_language(genre_entry.get('noms'))
                if genre:
                    break

        rating = ''
        note = _text(jeu.get('note'))
        if note:
            try:
                rating = round(float(note) / 20.0, 2)  # ScreenScraper rates out of 20
            except ValueError:
                pass

        data = {
            'name': style_name(name_entry.get('text')) if name_entry else '',
            'desc': _pick_by_language(jeu.get('synopsis')),
            'genre': genre,
            'developer': _text(jeu.get('developpeur')),
            'publisher': _text(jeu.get('editeur')),
            'releasedate': to_es_date(date_entry.get('text')) if date_entry else '',
            'players': _text(jeu.get('joueurs')),
            'rating': rating,
            'media': self.extract_media(jeu),
        }
        logger.debug(f"ScreenScraper extracted: name={data['name']}, media={list(data['media'])}")
        return data
