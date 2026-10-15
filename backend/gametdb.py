"""
GameTDB (gametdb.com): disc and cartridge pictures for GameCube, Wii, DS, 3DS
and PS3 games, filed by the game's own ID. The ID is read from the ROM file
itself, so the picture is that game's and no other's. No account and no quota.
"""

import logging
import re
import struct
from pathlib import Path
from typing import Dict, List, Optional

import requests

from backend.systems import gametdb_platform

logger = logging.getLogger(__name__)

BASE_URL = "https://art.gametdb.com"
# GameTDB's folder for a platform's disc or cartridge picture
_KINDS = {'wii': 'disc', 'ps3': 'disc', 'ds': 'cart', '3ds': 'cart'}
# The letter of an ID that says where the game was sold -> GameTDB's region folder
# For choosing by hand: media folder -> the files to try for it, the best first
_PICTURES = {
    'wii': {'support': ['disc.png'], 'box2d': ['cover.png'], 'box3d': ['cover3D.png']},
    'ds': {'support': ['cart.png'], 'box2d': ['coverHQ.jpg', 'cover.jpg'], 'box3d': ['box.png']},
    '3ds': {'support': ['cart.png'], 'box2d': ['coverHQ.jpg', 'coverM.jpg'], 'box3d': ['box.png']},
    'ps3': {'support': ['disc.png'], 'box2d': ['coverHQ.jpg', 'cover.jpg']},
}
_REGIONS = {'E': 'US', 'U': 'US', 'P': 'EN', 'J': 'JA', 'K': 'KO', 'D': 'DE', 'F': 'FR', 'S': 'ES', 'I': 'IT'}
_FALLBACK_REGIONS = ['US', 'EN', 'JA']

_DISC_ID = re.compile(rb'^[A-Z0-9]{6}$')
_CART_ID = re.compile(rb'^[A-Z0-9]{4}$')
_PS3_ID = re.compile(rb'([A-Z]{4})-?(\d{5})')
_3DS_CODE = re.compile(rb'^(?:CTR|KTR)-[A-Z]-([A-Z0-9]{4})')
# ...which is often in a 3DS file's name too: "Game (CTR-P-AC3P) (E).cia"
_3DS_NAMED = re.compile(r'\((?:CTR|KTR)-[A-Z]-([A-Z0-9]{4})\)')
# Where a GameCube or Wii disc's ID is in each kind of file
_DISC_OFFSETS = {'.iso': 0, '.gcm': 0, '.ciso': 0x8000, '.wbfs': 0x200, '.rvz': 0x58, '.wia': 0x58}


def _read(path: Path, offset: int, length: int) -> bytes:
    with open(path, 'rb') as f:
        f.seek(offset)
        return f.read(length)


def _align(n: int) -> int:
    return (n + 63) & ~63


def _3ds_id(path: Path) -> Optional[str]:
    """The four-letter code of a 3DS game, from its .3ds/.cci card image or its
    .cia (when that isn't encrypted)."""
    if path.suffix.lower() == '.cia':
        header, _type, _version, cert, ticket, tmd = struct.unpack('<IHHIII', _read(path, 0, 20))
        if header != 0x2020:
            return None
        start = _align(header) + _align(cert) + _align(ticket) + _align(tmd)
    else:
        if _read(path, 0x100, 4) != b'NCSD':
            return None
        start = struct.unpack('<I', _read(path, 0x120, 4))[0] * 0x200
    if _read(path, start + 0x100, 4) != b'NCCH':
        return None
    code = _3DS_CODE.match(_read(path, start + 0x150, 16))
    return code.group(1).decode() if code else None


def game_id(platform: str, path: Path) -> Optional[str]:
    """The game's ID as GameTDB files it, read from the ROM; None if this kind
    of file doesn't show it (a compressed or encrypted one, say). Never raises."""
    try:
        suffix = path.suffix.lower()
        if platform == 'wii':
            if suffix not in _DISC_OFFSETS or not path.is_file():
                return None
            found = _read(path, _DISC_OFFSETS[suffix], 6)
            return found.decode() if _DISC_ID.match(found) else None
        if platform == 'ds':
            found = _read(path, 0x0C, 4) if path.is_file() and suffix in ('.nds', '.dsi') else b''
            return found.decode() if _CART_ID.match(found) else None
        if platform == '3ds':
            named = _3DS_NAMED.search(path.name)
            if named:
                return named.group(1)
            return _3ds_id(path) if path.is_file() and suffix in ('.3ds', '.cci', '.cia') else None
        if platform == 'ps3':
            if path.is_dir():
                sfo = next((p for p in (path / 'PS3_GAME/PARAM.SFO', path / 'PARAM.SFO') if p.is_file()), None)
                found = _PS3_ID.search(sfo.read_bytes()[:65536]) if sfo else None
            else:
                found = _PS3_ID.search(_read(path, 0x800, 0x40)) if suffix == '.iso' else None
            return (found.group(1) + found.group(2)).decode() if found else None
    except (OSError, struct.error, ValueError) as e:
        logger.warning(f"GameTDB: couldn't read the game ID from {path.name}: {e}")
    return None


def _regions(platform: str, found_id: str) -> List[str]:
    letter = found_id[2] if platform == 'ps3' else found_id[3]
    return list(dict.fromkeys([_REGIONS.get(letter, 'EN')] + _FALLBACK_REGIONS))


class GameTDB:
    enabled = True

    def __init__(self):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'RetroManager'

    def _first(self, platform: str, found_id: str, files) -> Optional[str]:
        """The first of these files GameTDB has for the game, its own region's
        before another's. Raises requests.RequestException."""
        for name in files:
            kind, ext = name.split('.')
            for region in _regions(platform, found_id):
                url = f"{BASE_URL}/{platform}/{kind}/{region}/{found_id}.{ext}"
                if self.session.head(url, timeout=15, allow_redirects=True).status_code == 200:
                    return url
        return None

    def support_url(self, system_name: str, rom_file: Path) -> Optional[str]:
        """The address of the game's disc or cartridge picture, or None if
        GameTDB has none (or the system isn't one of its own). Never raises."""
        platform = gametdb_platform(system_name)
        if not self.enabled or not platform:
            return None
        found_id = game_id(platform, rom_file)
        if not found_id:
            return None
        try:
            return self._first(platform, found_id, [_KINDS[platform] + '.png'])
        except requests.RequestException as e:
            logger.warning(f"GameTDB couldn't be asked: {e}")
            return None

    def find(self, system_name: str, rom_file: Optional[Path]) -> Optional[str]:
        """The game's ID as "<platform>:<ID>", for `game`. Raises ValueError
        (with what to tell the person) when there's none to be had."""
        platform = gametdb_platform(system_name)
        if not platform:
            raise ValueError("GameTDB only has GameCube, Wii, DS, 3DS and PS3 games.")
        found_id = game_id(platform, rom_file) if rom_file else None
        if not found_id:
            raise ValueError("GameTDB files games by the ID inside the ROM, and this file doesn't show one (a compressed or encrypted file, or a download-only game).")
        return f"{platform}:{found_id}"

    def game(self, found: str) -> Dict[str, str]:
        """{media folder: url} for one of find's IDs: its disc or cartridge,
        cover and 3D box, whichever GameTDB has. Raises ValueError."""
        platform, _, found_id = str(found).partition(':')
        if platform not in _PICTURES or not re.match(r'^[A-Z0-9]{4,9}$', found_id):
            raise ValueError("That isn't a GameTDB game.")
        try:
            media = {folder: self._first(platform, found_id, files) for folder, files in _PICTURES[platform].items()}
        except requests.RequestException as e:
            raise ValueError(f"GameTDB couldn't be asked: {e}")
        return {folder: url for folder, url in media.items() if url}
