"""
Map ROM/media folder names to scraper system IDs.

IDs were checked against ScreenScraper's systemesListe.php and IGDB's
/platforms endpoint. Keys are normalized with normalize_system_name(), so
"snes", "SNES", "Super Nintendo" and "super-nintendo" all resolve.
"""

from typing import Optional, Tuple

# (folder aliases, ScreenScraper systemeid, IGDB platform id)
_SYSTEMS = [
    (("nes", "famicom", "nintendoentertainmentsystem"), 3, 18),
    (("fds", "famicomdisksystem"), 106, 51),
    (("snes", "sfc", "supernintendo", "superfamicom", "supernintendoentertainmentsystem"), 4, 19),
    (("n64", "nintendo64"), 14, 4),
    (("gc", "ngc", "gamecube", "nintendogamecube"), 13, 21),
    (("wii", "nintendowii"), 16, 5),
    (("gb", "gameboy"), 9, 33),
    (("gbc", "gameboycolor"), 10, 22),
    (("gba", "gameboyadvance"), 12, 24),
    (("nds", "nintendods"), 15, 20),
    (("3ds", "nintendo3ds"), 17, 37),
    (("nsw", "switch", "nintendoswitch"), 225, 130),
    (("virtualboy", "nvb"), 11, 87),
    (("gameandwatch", "gw"), 52, 307),
    (("pokemini", "pokemonmini"), 211, 166),
    (("megadrive", "genesis", "segagenesis", "segamegadrive"), 1, 29),
    (("mastersystem", "sms", "segamastersystem"), 2, 64),
    (("gamegear", "segagamegear"), 21, 35),
    (("sega32x", "32x"), 19, 30),
    (("segacd", "megacd"), 20, 78),
    (("saturn", "segasaturn"), 22, 32),
    (("dreamcast", "segadreamcast"), 23, 23),
    (("sg1000",), 109, 84),
    (("naomi",), 56, 52),
    (("psx", "ps1", "playstation", "sonyplaystation"), 57, 7),
    (("ps2", "playstation2"), 58, 8),
    (("ps3", "playstation3"), 59, 9),
    (("psp", "playstationportable"), 61, 38),
    (("xbox",), 32, 11),
    (("xbox360",), 33, 12),
    (("atari2600",), 26, 59),
    (("atari5200",), 40, 66),
    (("atari7800",), 41, 60),
    (("atari800",), 43, 65),
    (("atarilynx", "lynx"), 28, 61),
    (("atarijaguar", "jaguar"), 27, 62),
    (("atarijaguarcd", "jaguarcd"), 171, 410),
    (("atarist",), 42, 63),
    (("pcengine", "tg16", "turbografx16"), 31, 86),
    (("pcenginecd", "tgcd", "turbografxcd"), 114, 150),
    (("supergrafx",), 105, 128),
    (("pcfx",), 72, 274),
    (("neogeo",), 142, 80),
    (("neogeocd",), 70, 136),
    (("ngp", "neogeopocket"), 25, 119),
    (("ngpc", "neogeopocketcolor"), 82, 120),
    (("wonderswan",), 45, 57),
    (("wonderswancolor",), 46, 123),
    (("3do",), 29, 50),
    (("colecovision",), 48, 68),
    (("intellivision",), 115, 67),
    (("vectrex",), 102, 70),
    (("odyssey2", "videopac", "ody2"), 104, 133),
    (("msx",), 113, 27),
    (("zxspectrum",), 76, 26),
    (("amstradcpc",), 65, 25),
    (("c64", "commodore64"), 66, 15),
    (("amiga",), 64, 16),
    (("apple2", "appleii"), 86, 75),
    (("dos", "pc", "msdos"), 135, 13),
    (("macintosh", "mac"), 146, 14),
    (("x68000",), 79, 121),
    (("pc88",), 221, 125),
    (("pc98",), 208, 149),
    (("cps1",), 6, 52),
    (("cps2",), 7, 52),
    (("cps3",), 8, 52),
    (("arcade", "mame", "mamelibretro", "fba", "fbneo"), 75, 52),
    (("daphne",), 49, None),
    (("scummvm",), 123, None),
]

_LOOKUP = {}
for _aliases, _ss_id, _igdb_id in _SYSTEMS:
    for _alias in _aliases:
        _LOOKUP[_alias] = (_ss_id, _igdb_id)


def normalize_system_name(name: str) -> str:
    """Lowercase and keep letters/digits only ("Game Boy Advance" -> "gameboyadvance")."""
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def _lookup(system_name: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    return _LOOKUP.get(normalize_system_name(system_name), (None, None))


def screenscraper_system_id(system_name: Optional[str]) -> Optional[int]:
    """ScreenScraper systemeid for a folder name, or None if unknown."""
    return _lookup(system_name)[0]


def igdb_platform_id(system_name: Optional[str]) -> Optional[int]:
    """IGDB platform id for a folder name, or None if unknown."""
    return _lookup(system_name)[1]
