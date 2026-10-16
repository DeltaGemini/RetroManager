"""
Fetches the systems' logos for the "Logos" system pictures: monochrome SVGs from
HVR88's Monochrome Gaming Logos (https://github.com/HVR88/Monochrome-Gaming-Logos),
saved as frontend/logos/<folder>.svg. RetroManager draws each system's tile from
its logo in the colours of the theme in use (backend/logo_tiles.py).

The logos are their brand owners' marks, recreated by the collection's author
for identifying the systems; the collection asks only for credit and a link back
(frontend/logos/README.md). They aren't kept in git: run this to have them.

    python tools/fetch_system_logos.py           # the ones not fetched yet
    python tools/fetch_system_logos.py --again   # all of them again

A system with no logo here keeps its drawn tile. To add one, add a line to LOGOS.
"""

import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'frontend' / 'logos'
SOURCE = 'https://raw.githubusercontent.com/HVR88/Monochrome-Gaming-Logos/main/svg/{}.svg'

# System folder -> the collection's file name (without .svg)
LOGOS = {
    # Nintendo
    'nes': 'nintendo_nes', 'famicom': 'nintendo_famicom', 'fds': 'nintendo_famicom_disksystem',
    'snes': 'nintendo_snes', 'sfc': 'nintendo_super_famicom', 'n64': 'nintendo_64', 'gc': 'nintendo_gamecube',
    'wii': 'nintendo_wii', 'wiiu': 'nintendo_wiiu', 'nsw': 'nintendo_switch', 'switch': 'nintendo_switch',
    'gb': 'nintendo_gameboy', 'gbc': 'nintendo_gameboy_color', 'gba': 'nintendo_gameboy_advance',
    'nds': 'nintendo_ds', '3ds': 'nintendo_3ds', 'virtualboy': 'nintendo_virtualboy', 'gameandwatch': 'handheld_game_and_watch',
    # Sega
    'sg-1000': 'sega_sg1000', 'mastersystem': 'sega_master_system', 'megadrive': 'sega_megadrive', 'genesis': 'sega_genesis',
    'segacd': 'sega_cd', 'sega32x': 'sega_32x', 'gamegear': 'sega_gamegear', 'saturn': 'sega_saturn',
    'dreamcast': 'sega_dreamcast', 'naomi': 'sega_naomi',
    # Sony and Microsoft
    'psx': 'playstation_ps_compact', 'ps2': 'playstation_ps2', 'ps3': 'playstation_ps3_compact', 'psp': 'playstation_psp',
    'psvita': 'playstation_vita', 'xbox': 'xbox_original', 'xbox360': 'xbox_360',
    # Atari
    'atari2600': 'atari_2600', 'atari5200': 'atari_5200', 'atari7800': 'atari_7800', 'atari800': 'atari_800',
    'atarist': 'atari_st', 'atarilynx': 'atari_lynx', 'atarijaguar': 'atari_jaguar', 'atarijaguarcd': 'atari_jaguarcd',
    # NEC, SNK, Bandai and others
    'pcengine': 'nec_pcengine', 'tg16': 'nec_turbografx16', 'tg-cd': 'nec_turbografxcd', 'pcenginecd': 'nec_pcengine_cdrom',
    'supergrafx': 'nec_pcengine_supergrafx', 'pcfx': 'nec_pcfx', 'neogeo': 'snk_neogeo', 'neogeocd': 'snk_neogeo_cd',
    'ngp': 'snk_neogeo_pocket', 'ngpc': 'snk_neogeo_pocket_color', 'wonderswan': 'bandai_wonderswan',
    'wonderswancolor': 'bandai_wonderswan_color', '3do': '3do', 'colecovision': 'coleco_vision',
    'intellivision': 'mattel_intellivision', 'vectrex': 'vectrex', 'channelf': 'fairchild_channelf',
    'ody2': 'magnavox_odyssey2', 'videopac': 'philips_odyssey2', 'cdi': 'philips_cdi',
    # Computers
    'dos': 'ms-dos', 'pc': 'windows', 'winxp': 'windows', 'steam': 'publisher_steam', 'macintosh': 'apple_macintosh',
    'apple2': 'apple-ii', 'amiga': 'commodore_amiga', 'c64': 'commodore_64', 'msx': 'msx', 'zxspectrum': 'sinclair_zxspectrum',
    'dragon32': 'dragon32', 'x68000': 'sharp_x68000',
    # Engines, arcade and lists
    'scummvm': 'scummvm', 'residualvm': 'residualvm', 'zmachine': 'z-machine', 'love': 'love', 'kodi': 'kodi',
    'arcade': 'arcade', 'mame': 'mame', 'fba': 'final_burn', 'fbneo': 'final_burn', 'cps1': 'capcom_cp1',
    'cps2': 'capcom_cp2', 'cps3': 'capcom_cp3', 'daphne': 'laserdisc_daphne', 'ports': 'playlist_ports',
    'auto-favorites': 'playlist_favourites',
}


def main():
    again = '--again' in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    fetched = kept = failed = 0
    for folder, name in sorted(LOGOS.items()):
        target = OUT / f'{folder}.svg'
        if target.is_file() and not again:
            kept += 1
            continue
        try:
            with urllib.request.urlopen(SOURCE.format(name), timeout=30) as response:
                data = response.read()
            if b'<svg' not in data[:2000]:
                raise ValueError("not an SVG")
            target.write_bytes(data)
            fetched += 1
        except Exception as e:
            print(f"{folder} ({name}): {e}", file=sys.stderr)
            failed += 1
    print(f"Fetched {fetched}, already had {kept}, failed {failed}. In {OUT}")


if __name__ == '__main__':
    main()
