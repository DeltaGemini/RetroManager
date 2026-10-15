"""
Hasheous (hasheous.org) hash lookups: a ROM's checksums -> the same game's IDs
on IGDB, RetroAchievements, ScreenScraper and SteamGridDB. No account needed.
https://hasheous.org/swagger/index.html
"""

import logging
import time
from collections import OrderedDict
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class HasheousError(Exception):
    """A Hasheous request failed; the message is safe to show in the UI."""


# Hasheous source name -> key in the result's `ids`
_SOURCES = {
    'IGDB': 'igdb',
    'RetroAchievements': 'retroachievements',
    'ScreenScraper': 'screenscraper',
    'SteamGridDb': 'steamgriddb',
    'TheGamesDb': 'thegamesdb',
}


class HasheousAPI:
    BASE_URL = "https://hasheous.org/api/v1"

    def __init__(self, enabled: bool = True, cache_size: int = 2000):
        self.enabled = enabled
        self.session = requests.Session()
        self.cache_size = cache_size
        self._cache: "OrderedDict[str, Optional[Dict]]" = OrderedDict()

    def lookup(self, hashes: Optional[Dict[str, str]]) -> Optional[Dict]:
        """{'name', 'platform', 'ids': {'igdb': '1802', ...}, 'sources': the ROM
        databases that list this exact file (TOSEC, NoIntros, Redump,
        RetroAchievements...)} for a ROM's checksums
        (as HashCache.hashes returns them), or None when Hasheous doesn't know the
        file. Raises HasheousError when it can't be asked."""
        if not self.enabled or not hashes or not hashes.get('md5'):
            return None
        key = hashes['md5']
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        body = {'mD5': hashes['md5']}
        if hashes.get('sha1'):
            body['shA1'] = hashes['sha1']
        response = None
        for attempt in range(2):
            try:
                response = self.session.post(f"{self.BASE_URL}/Lookup/ByHash", params={'returnAllSources': 'true'},
                                             json=body, timeout=(10, 30))
            except requests.RequestException as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise HasheousError(f"Couldn't reach Hasheous: {e}")
            if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                time.sleep(2)
                continue
            break

        # 404: not in any database. 400: it won't look the checksums up at all
        # (those of an empty file, say), which comes to the same thing
        if response.status_code in (400, 404):
            result = None
        elif response.status_code != 200:
            logger.warning(f"Hasheous: HTTP {response.status_code}: {response.text[:200]}")
            raise HasheousError(f"Hasheous returned HTTP {response.status_code}.")
        else:
            try:
                data = response.json()
            except ValueError:
                raise HasheousError("Hasheous returned a response that isn't JSON.")
            ids = {}
            for entry in data.get('metadata') or []:
                source = _SOURCES.get((entry or {}).get('source'))
                game_id = str(entry.get('immutableId') or entry.get('id') or '')
                if source and game_id and entry.get('status') == 'Mapped':
                    ids[source] = game_id
            result = {
                'name': data.get('name') or '',
                'platform': (data.get('platform') or {}).get('name') or '',
                'ids': ids,
                'sources': sorted((data.get('signatures') or {}).keys()),
            }
            logger.debug(f"Hasheous: {key} is {result['name']} {ids}")

        self._cache[key] = result
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return result
