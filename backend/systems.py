"""
Map ROM/media folder names to scraper system IDs.

IDs were checked against ScreenScraper's systemesListe.php and IGDB's
/platforms endpoint. RetroAchievements console IDs and libretro thumbnail
folders are looked up by each system's first alias. Keys are normalized with normalize_system_name(), so
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
    (("colecovision", "coleco"), 48, 68),
    (("intellivision",), 115, 67),
    (("vectrex",), 102, 70),
    (("channelf", "fairchildchannelf"), 80, 127),
    (("odyssey2", "videopac", "ody2"), 104, 133),
    (("msx",), 113, 27),
    (("zxspectrum",), 76, 26),
    (("amstradcpc",), 65, 25),
    (("c64", "commodore64"), 66, 15),
    (("amiga",), 64, 16),
    (("apple2", "appleii"), 86, 75),
    (("dos", "pc", "msdos"), 135, 13),
    (("steam", "pcsteam", "windows", "pcwindows", "winxp", "win"), 138, 6),
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

# First alias -> RetroAchievements console ID
_RA_CONSOLES = {
    "megadrive": 1, "n64": 2, "snes": 3, "gb": 4, "gba": 5, "gbc": 6, "nes": 7, "pcengine": 8,
    "segacd": 9, "sega32x": 10, "mastersystem": 11, "psx": 12, "atarilynx": 13, "ngp": 14,
    "ngpc": 14, "gamegear": 15, "gc": 16, "atarijaguar": 17, "nds": 18, "wii": 19, "ps2": 21,
    "odyssey2": 23, "pokemini": 24, "atari2600": 25, "arcade": 27, "virtualboy": 28, "msx": 29,
    "sg1000": 33, "amstradcpc": 37, "apple2": 38, "saturn": 39, "dreamcast": 40, "psp": 41,
    "3do": 43, "colecovision": 44, "intellivision": 45, "vectrex": 46, "pc88": 47, "pcfx": 49,
    "atari7800": 51, "wonderswan": 53, "wonderswancolor": 53, "neogeocd": 56,
    "channelf": 57, "pcenginecd": 76, "atarijaguarcd": 77,
}

# First alias -> folder on thumbnails.libretro.com (arcade sets are left out:
# their thumbnails are named by game title, not by ROM set)
_LIBRETRO_FOLDERS = {
    "nes": "Nintendo - Nintendo Entertainment System",
    "fds": "Nintendo - Family Computer Disk System",
    "snes": "Nintendo - Super Nintendo Entertainment System",
    "n64": "Nintendo - Nintendo 64",
    "gc": "Nintendo - GameCube",
    "wii": "Nintendo - Wii",
    "gb": "Nintendo - Game Boy",
    "gbc": "Nintendo - Game Boy Color",
    "gba": "Nintendo - Game Boy Advance",
    "nds": "Nintendo - Nintendo DS",
    "3ds": "Nintendo - Nintendo 3DS",
    "virtualboy": "Nintendo - Virtual Boy",
    "pokemini": "Nintendo - Pokemon Mini",
    "megadrive": "Sega - Mega Drive - Genesis",
    "mastersystem": "Sega - Master System - Mark III",
    "gamegear": "Sega - Game Gear",
    "sega32x": "Sega - 32X",
    "segacd": "Sega - Mega-CD - Sega CD",
    "saturn": "Sega - Saturn",
    "dreamcast": "Sega - Dreamcast",
    "sg1000": "Sega - SG-1000",
    "psx": "Sony - PlayStation",
    "ps2": "Sony - PlayStation 2",
    "ps3": "Sony - PlayStation 3",
    "psp": "Sony - PlayStation Portable",
    "xbox": "Microsoft - Xbox",
    "xbox360": "Microsoft - Xbox 360",
    "atari2600": "Atari - 2600",
    "atari5200": "Atari - 5200",
    "atari7800": "Atari - 7800",
    "atari800": "Atari - 8-bit",
    "atarilynx": "Atari - Lynx",
    "atarijaguar": "Atari - Jaguar",
    "atarist": "Atari - ST",
    "pcengine": "NEC - PC Engine - TurboGrafx 16",
    "pcenginecd": "NEC - PC Engine CD - TurboGrafx-CD",
    "supergrafx": "NEC - PC Engine SuperGrafx",
    "pcfx": "NEC - PC-FX",
    "neogeocd": "SNK - Neo Geo CD",
    "ngp": "SNK - Neo Geo Pocket",
    "ngpc": "SNK - Neo Geo Pocket Color",
    "wonderswan": "Bandai - WonderSwan",
    "wonderswancolor": "Bandai - WonderSwan Color",
    "3do": "The 3DO Company - 3DO",
    "colecovision": "Coleco - ColecoVision",
    "intellivision": "Mattel - Intellivision",
    "vectrex": "GCE - Vectrex",
    "odyssey2": "Magnavox - Odyssey2",
    "msx": "Microsoft - MSX",
    "zxspectrum": "Sinclair - ZX Spectrum",
    "amstradcpc": "Amstrad - CPC",
    "c64": "Commodore - 64",
    "amiga": "Commodore - Amiga",
    "dos": "DOS",
    "x68000": "Sharp - X68000",
    "pc88": "NEC - PC-8001 - PC-8801",
    "pc98": "NEC - PC-98",
}

# First alias -> TheGamesDB platform id (thegamesdb.net/list_platforms.php), to
# keep its name searches to the system. One that isn't here is searched on every platform.
_TGDB_PLATFORMS = {
    "nes": 7, "fds": 4936, "snes": 6, "n64": 3, "gc": 2, "wii": 9, "gb": 4, "gbc": 41, "gba": 5, "nds": 8, "3ds": 4912,
    "nsw": 4971, "virtualboy": 4918, "gameandwatch": 4950, "pokemini": 4957,
    "megadrive": 36, "mastersystem": 35, "gamegear": 20, "sega32x": 33, "segacd": 21, "saturn": 17, "dreamcast": 16, "sg1000": 4949,
    "psx": 10, "ps2": 11, "ps3": 12, "psp": 13, "xbox": 14, "xbox360": 15,
    "atari2600": 22, "atari5200": 26, "atari7800": 27, "atari800": 4943, "atarilynx": 4924, "atarijaguar": 28, "atarijaguarcd": 29, "atarist": 4937,
    "pcengine": 34, "pcenginecd": 4955, "pcfx": 4930, "neogeo": 24, "neogeocd": 4956, "ngp": 4922, "ngpc": 4923,
    "wonderswan": 4925, "wonderswancolor": 4926, "3do": 25, "colecovision": 31, "intellivision": 32, "vectrex": 4939,
    "channelf": 4928, "odyssey2": 4927, "msx": 4929, "zxspectrum": 4913, "amstradcpc": 4914, "c64": 40, "amiga": 4911,
    "apple2": 4942, "dos": 1, "steam": 1, "macintosh": 37, "x68000": 4931, "pc88": 4933, "pc98": 4934,
    "arcade": 23, "cps1": 23, "cps2": 23, "cps3": 23, "naomi": 23,
}

# First alias -> GameTDB's platform folder (art.gametdb.com/<platform>/...): GameCube discs are with the Wii's
_GAMETDB_PLATFORMS = {"gc": "wii", "wii": "wii", "nds": "ds", "3ds": "3ds", "ps3": "ps3"}

# First alias -> the platform's name in the LaunchBox Games Database
_LAUNCHBOX_PLATFORMS = {
    "nes": "Nintendo Entertainment System", "fds": "Nintendo Famicom Disk System", "snes": "Super Nintendo Entertainment System",
    "n64": "Nintendo 64", "gc": "Nintendo GameCube", "wii": "Nintendo Wii", "wiiu": "Nintendo Wii U", "nsw": "Nintendo Switch",
    "gb": "Nintendo Game Boy", "gbc": "Nintendo Game Boy Color", "gba": "Nintendo Game Boy Advance", "nds": "Nintendo DS",
    "3ds": "Nintendo 3DS", "virtualboy": "Nintendo Virtual Boy", "gameandwatch": "Nintendo Game & Watch", "pokemini": "Nintendo Pokemon Mini",
    "megadrive": "Sega Genesis", "mastersystem": "Sega Master System", "gamegear": "Sega Game Gear", "sega32x": "Sega 32X",
    "segacd": "Sega CD", "saturn": "Sega Saturn", "dreamcast": "Sega Dreamcast", "sg1000": "Sega SG-1000",
    "psx": "Sony Playstation", "ps2": "Sony Playstation 2", "ps3": "Sony Playstation 3", "psp": "Sony PSP", "psvita": "Sony Playstation Vita",
    "xbox": "Microsoft Xbox", "xbox360": "Microsoft Xbox 360",
    "atari2600": "Atari 2600", "atari5200": "Atari 5200", "atari7800": "Atari 7800", "atari800": "Atari 800", "atarilynx": "Atari Lynx",
    "atarijaguar": "Atari Jaguar", "atarijaguarcd": "Atari Jaguar CD", "atarist": "Atari ST",
    "pcengine": "NEC TurboGrafx-16", "pcenginecd": "NEC TurboGrafx-CD", "pcfx": "NEC PC-FX",
    "neogeo": "SNK Neo Geo AES", "neogeocd": "SNK Neo Geo CD", "ngp": "SNK Neo Geo Pocket Color", "ngpc": "SNK Neo Geo Pocket Color",
    "wonderswan": "WonderSwan", "wonderswancolor": "WonderSwan Color", "3do": "3DO Interactive Multiplayer",
    "colecovision": "ColecoVision", "intellivision": "Mattel Intellivision", "vectrex": "GCE Vectrex", "channelf": "Fairchild Channel F",
    "odyssey2": "Magnavox Odyssey 2", "msx": "Microsoft MSX", "zxspectrum": "Sinclair ZX Spectrum", "amstradcpc": "Amstrad CPC",
    "c64": "Commodore 64", "amiga": "Commodore Amiga", "apple2": "Apple II", "dos": "MS-DOS", "steam": "Windows",
    "macintosh": "Apple Mac OS", "x68000": "Sharp X68000", "pc88": "NEC PC-8801", "pc98": "NEC PC-9801",
    "arcade": "Arcade", "cps1": "Arcade", "cps2": "Arcade", "cps3": "Arcade", "naomi": "Sega Naomi",
}

# First alias -> EmulatorJS system (EJS_core), for playing in the browser
_EMULATORJS_SYSTEMS = {
    "nes": "nes", "fds": "nes", "snes": "snes", "n64": "n64", "gb": "gb", "gbc": "gb", "gba": "gba",
    "nds": "nds", "virtualboy": "vb", "megadrive": "segaMD", "mastersystem": "segaMS", "gamegear": "segaGG",
    "sega32x": "sega32x", "segacd": "segaCD", "saturn": "segaSaturn", "sg1000": "segaMS", "psx": "psx",
    "atari2600": "atari2600", "atari5200": "atari5200", "atari7800": "atari7800", "atarilynx": "lynx",
    "atarijaguar": "jaguar", "colecovision": "coleco", "pcengine": "pce", "pcenginecd": "pce",
    "ngp": "ngp", "ngpc": "ngp", "wonderswan": "ws", "wonderswancolor": "ws", "3do": "3do",
    "arcade": "arcade", "neogeo": "arcade", "c64": "c64",
}

# First alias -> RetroArch cores that play it on a phone (the Android app in
# android/), likeliest first: the name is the core's file without
# "_libretro_android.so". The app starts the first unless another is chosen there.
_RETROARCH_CORES = {
    "nes": ("nestopia", "mesen", "fceumm"), "fds": ("nestopia", "mesen", "fceumm"),
    "snes": ("snes9x", "bsnes", "snes9x2010"),
    "n64": ("mupen64plus_next_gles3", "mupen64plus_next_gles2", "parallel_n64"),
    "gc": ("dolphin",), "wii": ("dolphin",),
    "gb": ("gambatte", "mgba", "sameboy"), "gbc": ("gambatte", "mgba", "sameboy"),
    "gba": ("mgba", "vba_next", "gpsp"), "nds": ("melondsds", "melonds", "desmume"), "3ds": ("citra",),
    "virtualboy": ("mednafen_vb",), "gameandwatch": ("gw",), "pokemini": ("pokemini",),
    "megadrive": ("genesis_plus_gx", "picodrive"), "mastersystem": ("genesis_plus_gx", "picodrive", "smsplus"),
    "gamegear": ("genesis_plus_gx", "smsplus"), "sega32x": ("picodrive",), "segacd": ("genesis_plus_gx", "picodrive"),
    "saturn": ("yabasanshiro", "mednafen_saturn", "yabause"), "dreamcast": ("flycast",), "naomi": ("flycast",),
    "sg1000": ("genesis_plus_gx", "gearsystem"),
    "psx": ("pcsx_rearmed", "swanstation", "mednafen_psx_hw", "mednafen_psx"), "ps2": ("play",), "psp": ("ppsspp",),
    "atari2600": ("stella", "stella2014"), "atari5200": ("a5200", "atari800"), "atari7800": ("prosystem",),
    "atari800": ("atari800",), "atarilynx": ("handy", "mednafen_lynx"), "atarijaguar": ("virtualjaguar",),
    "atarist": ("hatari",),
    "pcengine": ("mednafen_pce_fast", "mednafen_pce", "mednafen_supergrafx"),
    "pcenginecd": ("mednafen_pce_fast", "mednafen_pce", "mednafen_supergrafx"),
    "supergrafx": ("mednafen_supergrafx",), "pcfx": ("mednafen_pcfx",),
    "neogeo": ("fbneo", "fbalpha2012_neogeo"), "neogeocd": ("neocd", "fbneo"),
    "ngp": ("mednafen_ngp", "race"), "ngpc": ("mednafen_ngp", "race"),
    "wonderswan": ("mednafen_wswan",), "wonderswancolor": ("mednafen_wswan",),
    "3do": ("opera",), "colecovision": ("bluemsx", "gearcoleco"), "intellivision": ("freeintv",),
    "vectrex": ("vecx",), "channelf": ("freechaf",), "odyssey2": ("o2em",),
    "msx": ("bluemsx", "fmsx"), "zxspectrum": ("fuse",), "amstradcpc": ("cap32", "crocods"),
    "c64": ("vice_x64", "vice_x64sc"), "amiga": ("puae",), "dos": ("dosbox_pure", "dosbox_core"),
    "scummvm": ("scummvm",), "x68000": ("px68k",), "pc88": ("quasi88",), "pc98": ("np2kai",),
    "cps1": ("fbneo", "fbalpha2012_cps1"), "cps2": ("fbneo", "fbalpha2012_cps2"), "cps3": ("fbneo", "fbalpha2012_cps3"),
    "arcade": ("fbneo", "mame2003_plus", "mame2010", "mame"),
}

# First alias -> BIOS files, any one of which the system needs before it will
# play in the browser (looked for in BIOS_PATH and its sub-folders)
_REQUIRED_BIOS = {
    "segacd": ("bios_CD_U.bin", "bios_CD_E.bin", "bios_CD_J.bin"),
    "3do": ("panafz10.bin", "panafz1.bin", "goldstar.bin"),
    "pcenginecd": ("syscard3.pce",),
    "fds": ("disksys.rom",),
    "neogeo": ("neogeo.zip",),
}
# ...and BIOS files a system plays better with, but can do without
_OPTIONAL_BIOS = {
    "psx": ("scph5501.bin", "scph1001.bin", "scph7001.bin", "scph5500.bin", "scph5502.bin"),
    "saturn": ("sega_101.bin", "mpr-17933.bin", "saturn_bios.bin"),
    "atarilynx": ("lynxboot.img",),
}

_LOOKUP = {}
_PRIMARY = {}
for _aliases, _ss_id, _igdb_id in _SYSTEMS:
    for _alias in _aliases:
        _LOOKUP[_alias] = (_ss_id, _igdb_id)
        _PRIMARY[_alias] = _aliases[0]


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


def thegamesdb_platform_id(system_name: Optional[str]) -> Optional[int]:
    """TheGamesDB platform id for a folder name, or None if unknown."""
    return _TGDB_PLATFORMS.get(_PRIMARY.get(normalize_system_name(system_name)))


def gametdb_platform(system_name: Optional[str]) -> Optional[str]:
    """GameTDB's platform folder for a folder name, or None if it has none."""
    return _GAMETDB_PLATFORMS.get(_PRIMARY.get(normalize_system_name(system_name)))


def launchbox_platform(system_name: Optional[str]) -> Optional[str]:
    """The LaunchBox Games Database's name for a folder name's platform, or None if unknown."""
    return _LAUNCHBOX_PLATFORMS.get(_PRIMARY.get(normalize_system_name(system_name)))


def launchbox_platforms() -> set:
    return set(_LAUNCHBOX_PLATFORMS.values())


def retroachievements_console_id(system_name: Optional[str]) -> Optional[int]:
    """RetroAchievements console ID for a folder name, or None if unknown."""
    return _RA_CONSOLES.get(_PRIMARY.get(normalize_system_name(system_name)))


def libretro_thumbnail_folder(system_name: Optional[str]) -> Optional[str]:
    """The system's folder on thumbnails.libretro.com, or None if it has none."""
    return _LIBRETRO_FOLDERS.get(_PRIMARY.get(normalize_system_name(system_name)))


def is_arcade(system_name: Optional[str]) -> bool:
    """Arcade systems identify games by ROM set name rather than file contents."""
    return _PRIMARY.get(normalize_system_name(system_name)) in ("arcade", "naomi", "cps1", "cps2", "cps3", "neogeo")


def emulatorjs_system(system_name: Optional[str]) -> Optional[str]:
    """The EmulatorJS system that plays this folder's games in the browser, or None."""
    return _EMULATORJS_SYSTEMS.get(_PRIMARY.get(normalize_system_name(system_name)))


# A core's file name -> the name RetroArch knows it by, which is what it calls
# the core's folder in its config folder (config/<name>/<name>.cfg is the
# core's override, <name>.opt its options). The phone app writes into that
# folder; a core that isn't here is left alone.
_RETROARCH_CORE_NAMES = {
    "fceumm": "FCEUmm", "nestopia": "Nestopia", "mesen": "Mesen", "snes9x": "Snes9x", "bsnes": "bsnes", "snes9x2010": "Snes9x 2010",
    "mupen64plus_next_gles3": "Mupen64Plus-Next", "mupen64plus_next_gles2": "Mupen64Plus-Next", "parallel_n64": "ParaLLEl N64",
    "dolphin": "dolphin-emu", "gambatte": "Gambatte", "mgba": "mGBA", "sameboy": "SameBoy", "vba_next": "VBA Next", "gpsp": "gpSP",
    "melondsds": "melonDS DS", "melonds": "melonDS", "desmume": "DeSmuME", "citra": "Citra", "mednafen_vb": "Beetle VB",
    "gw": "Game & Watch", "pokemini": "PokeMini", "genesis_plus_gx": "Genesis Plus GX", "picodrive": "PicoDrive", "smsplus": "SMS Plus GX",
    "gearsystem": "Gearsystem", "yabasanshiro": "YabaSanshiro", "mednafen_saturn": "Beetle Saturn", "yabause": "Yabause", "flycast": "Flycast",
    "pcsx_rearmed": "PCSX-ReARMed", "swanstation": "SwanStation", "mednafen_psx_hw": "Beetle PSX HW", "mednafen_psx": "Beetle PSX",
    "play": "Play!", "ppsspp": "PPSSPP", "stella": "Stella", "stella2014": "Stella 2014", "a5200": "a5200", "atari800": "Atari800",
    "prosystem": "ProSystem", "handy": "Handy", "mednafen_lynx": "Beetle Lynx", "virtualjaguar": "Virtual Jaguar", "hatari": "Hatari",
    "mednafen_pce_fast": "Beetle PCE Fast", "mednafen_pce": "Beetle PCE", "mednafen_supergrafx": "Beetle SuperGrafx", "mednafen_pcfx": "Beetle PC-FX",
    "fbneo": "FinalBurn Neo", "neocd": "NeoCD", "mednafen_ngp": "Beetle NeoPop", "race": "RACE", "mednafen_wswan": "Beetle WonderSwan",
    "opera": "Opera", "bluemsx": "blueMSX", "gearcoleco": "Gearcoleco", "freeintv": "FreeIntv", "vecx": "vecx", "freechaf": "FreeChaF",
    "o2em": "O2EM", "fmsx": "fMSX", "fuse": "Fuse", "cap32": "cap32", "crocods": "CrocoDS", "vice_x64": "VICE x64", "vice_x64sc": "VICE x64sc",
    "puae": "PUAE", "dosbox_pure": "DOSBox-pure", "dosbox_core": "DOSBox-core", "scummvm": "ScummVM", "px68k": "PX68k", "quasi88": "QUASI88",
    "np2kai": "Neko Project II Kai", "mame2003_plus": "MAME 2003-Plus", "mame2010": "MAME 2010", "mame": "MAME",
}

# Android emulators of their own that the phone app can start a game in, where
# RetroArch has no core for a system or a poor one. How each is started:
# `package` and `activity` name it, `action` is what it's asked to do, and
# "data": "document" hands it the game as a document it's allowed to read (the
# way current emulators want it, rather than a path); `extras` are named values
# it's given, where "{document}" stands for the game as such a document and
# "{path}" for its path on the phone. `get` is where it comes from.
# `titles`: games in these formats have to be installed in the emulator first
# (a 3DS .cia), so it's started on the installed copy, looked for in the
# emulator's own folder (one of `folders`, inside the RetroArch folder).
_PHONE_EMULATORS = {
    "azahar": {
        "name": "Azahar", "package": "org.azahar_emu.azahar", "activity": "org.citra.citra_emu.activities.EmulationActivity",
        "action": "android.intent.action.VIEW", "data": "document", "type": "application/octet-stream",
        "get": "https://azahar-emu.org/",
        "titles": {"extensions": [".cia"], "folders": ["azahar", "Azahar", "citra-emu"]},
    },
    "dolphin": {
        "name": "Dolphin", "package": "org.dolphinemu.dolphinemu", "activity": "org.dolphinemu.dolphinemu.ui.main.MainActivity",
        "action": "android.intent.action.MAIN", "extras": {"AutoStartFile": "{document}"},
        "get": "https://dolphin-emu.org/download/",
    },
}
# First alias -> the emulators above that play it, likeliest first
_PHONE_EMULATOR_SYSTEMS = {
    "3ds": ("azahar",), "gc": ("dolphin",), "wii": ("dolphin",),
}


def phone_players(system_name: Optional[str]) -> list:
    """Everything that can play this folder's games on a phone, for the app to
    choose from: emulators of their own ({id: "app:…", kind: "app", name,
    package, activity, action, data, type, get}), then RetroArch's cores
    ({id: "retroarch:…", kind: "core", core, name, folder: the core's folder
    in RetroArch's config folder, if known})."""
    primary = _PRIMARY.get(normalize_system_name(system_name))
    players = [{'id': f'app:{key}', 'kind': 'app', **_PHONE_EMULATORS[key]} for key in _PHONE_EMULATOR_SYSTEMS.get(primary, ())]
    players += [{'id': f'retroarch:{core}', 'kind': 'core', 'core': core, 'name': f'RetroArch: {core}', 'folder': _RETROARCH_CORE_NAMES.get(core)}
                for core in _RETROARCH_CORES.get(primary, ())]
    return players


def retroarch_cores(system_name: Optional[str]) -> Tuple[str, ...]:
    """The RetroArch cores that play this folder's games on a phone, likeliest
    first (none: RetroArch has nothing for it)."""
    return _RETROARCH_CORES.get(_PRIMARY.get(normalize_system_name(system_name)), ())


# Where BIOS files are kept (set once at start-up, from BIOS_PATH)
_bios_dir = None


def set_bios_dir(path) -> None:
    global _bios_dir
    _bios_dir = path


def bios_file(system_name: Optional[str]):
    """The BIOS file to give the browser emulator for a system (a Path), or None
    if it needs none or none is there."""
    primary = _PRIMARY.get(normalize_system_name(system_name))
    names = _REQUIRED_BIOS.get(primary, ()) + _OPTIONAL_BIOS.get(primary, ())
    if not names or _bios_dir is None:
        return None
    try:
        if not _bios_dir.is_dir():
            return None
        found = {f.name.lower(): f for f in _bios_dir.rglob('*') if f.is_file()}
    except OSError:
        return None
    return next((found[name.lower()] for name in names if name.lower() in found), None)


def bios_files(system_name: Optional[str]) -> list:
    """Every BIOS file there is for a system (Paths), for a phone's RetroArch,
    which keeps them in its system folder."""
    primary = _PRIMARY.get(normalize_system_name(system_name))
    names = {name.lower() for name in _REQUIRED_BIOS.get(primary, ()) + _OPTIONAL_BIOS.get(primary, ())}
    try:
        if not names or _bios_dir is None or not _bios_dir.is_dir():
            return []
        return sorted({f.name.lower(): f for f in _bios_dir.rglob('*') if f.is_file() and f.name.lower() in names}.values())
    except OSError:
        return []


# Games the browser emulator can't be given: playlists of discs and archives it can't open
_NOT_BROWSER_PLAYABLE = ('.m3u', '.7z', '.rar')


def browser_playable(system_name: Optional[str], rom_path: str) -> bool:
    """Whether a game can be played in the browser: its system is one
    EmulatorJS plays, the BIOS that system needs is there, and its file is one
    that can be handed over (a disc's .cue is, with its tracks)."""
    primary = _PRIMARY.get(normalize_system_name(system_name))
    if not emulatorjs_system(system_name) or (rom_path or '').lower().endswith(_NOT_BROWSER_PLAYABLE):
        return False
    return primary not in _REQUIRED_BIOS or bios_file(system_name) is not None
