"""
libretro thumbnails (thumbnails.libretro.com): box art, screenshots, title
screens and logos, filed by No-Intro/Redump game name. No account and no quota.
https://docs.libretro.com/guides/roms-playlists-thumbnails/#thumbnail-paths-and-filenames
"""

import logging
import re
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote

import requests

from backend.systems import libretro_thumbnail_folder

logger = logging.getLogger(__name__)

BASE_URL = "https://thumbnails.libretro.com"

# RetroManager media folder -> libretro thumbnail type
THUMBNAIL_TYPES = {
    'box2d': 'Named_Boxarts',
    'screenshot': 'Named_Snaps',
    'screenshottitle': 'Named_Titles',
    'wheel': 'Named_Logos',
}

# Tried, in order, for a name that has no (Region) tag of its own
_REGION_GUESSES = ['(USA)', '(USA, Europe)', '(World)', '(Europe)', '(Japan, USA)', '(Japan)']

# Characters libretro replaces with "_" in thumbnail file names
_ILLEGAL_RE = re.compile(r'[&*/:`<>?\\|"]')
MAX_NAMES = 12


def candidate_names(names: Iterable[Optional[str]]) -> List[str]:
    """Thumbnail names to try for a game, likeliest first: each name as given,
    then names without a (tag) with the usual region tags added."""
    exact, guessed = [], []
    for name in names:
        name = (name or '').strip()
        if not name:
            continue
        if name not in exact:
            exact.append(name)
        if '(' not in name:
            guessed.extend(f"{name} {region}" for region in _REGION_GUESSES if f"{name} {region}" not in guessed)
    return (exact + [g for g in guessed if g not in exact])[:MAX_NAMES]


class LibretroThumbnails:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.session = requests.Session()

    def url(self, system_name: str, folder: str, name: str) -> Optional[str]:
        system_folder = libretro_thumbnail_folder(system_name)
        thumb_type = THUMBNAIL_TYPES.get(folder)
        if not system_folder or not thumb_type:
            return None
        file_name = _ILLEGAL_RE.sub('_', name)
        return f"{BASE_URL}/{quote(system_folder)}/{thumb_type}/{quote(file_name)}.png"

    def _exists(self, url: str) -> bool:
        try:
            return self.session.head(url, timeout=(5, 15), allow_redirects=True).status_code == 200
        except requests.RequestException as e:
            logger.debug(f"libretro thumbnails: {url}: {e}")
            return False

    def matching_name(self, system_name: str, names: Iterable[Optional[str]]) -> Optional[str]:
        """The first candidate name libretro has any thumbnail for (box art is
        checked first, since nearly every listed game has it)."""
        if not self.enabled or not libretro_thumbnail_folder(system_name):
            return None
        candidates = candidate_names(names)
        for folder in ('box2d', 'screenshot'):
            for name in candidates:
                if self._exists(self.url(system_name, folder, name)):
                    return name
        return None

    def find(self, system_name: str, names: Iterable[Optional[str]],
             folders: Optional[Iterable[str]] = None) -> Dict[str, str]:
        """{media folder: url} for the thumbnails libretro has for this game."""
        name = self.matching_name(system_name, names)
        if not name:
            return {}
        media = {}
        for folder in folders or THUMBNAIL_TYPES:
            url = self.url(system_name, folder, name)
            if url and self._exists(url):
                media[folder] = url
        return media
