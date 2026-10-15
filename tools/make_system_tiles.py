"""
Draws a square picture for each system (frontend/tiles/<folder>.svg), for a
copy of RetroManager that's given to others: the pictures in frontend/imgs/
come from an EmulationStation theme that can't be passed on freely, and show
console logos and game art that aren't ours.

These are drawn from nothing but shapes and the system's name: a colour for
who made it, a plain drawing of the kind of machine it is (a pad, a handheld,
a computer, an arcade cabinet...), its name and when it came out. No logo, no
lettering of anyone's, no game. RetroManager uses one wherever a system has no
picture in frontend/imgs/ (backend/routes/pages.py), and for every system when
SYSTEM_TILES=1.

    python tools/make_system_tiles.py

Running it again overwrites them. To add a system, add a line to SYSTEMS.
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / 'frontend' / 'tiles'
SIZE = 720

# Who made it -> the tile's two colours (top left to bottom right) and the name shown
MAKERS = {
    'nintendo': ('#d7372f', '#7a1512', 'Nintendo'),
    'sega': ('#2374d8', '#0c2f66', 'Sega'),
    'sony': ('#4352b8', '#141a52', 'Sony'),
    'microsoft': ('#3d9a45', '#14471a', 'Microsoft'),
    'atari': ('#ea6a1c', '#7c2c05', 'Atari'),
    'nec': ('#17a2a8', '#064a52', 'NEC'),
    'snk': ('#c79a1e', '#5f4306', 'SNK'),
    'bandai': ('#c2417d', '#5a1438', 'Bandai'),
    'commodore': ('#3f8fb8', '#123f57', 'Commodore'),
    'computer': ('#1f9c85', '#07443a', None),
    'arcade': ('#8e3fc4', '#3a1259', None),
    'other': ('#5f7783', '#222f36', None),
    'list': ('#d1457f', '#5f1238', None),
}

# folder: (name, as lines; maker; kind of machine; when it came out, or what it is)
SYSTEMS = {
    # Nintendo
    'nes': (['NES'], 'nintendo', 'pad', '1983'),
    'famicom': (['Famicom'], 'nintendo', 'pad', '1983'),
    'fds': (['Famicom', 'Disk System'], 'nintendo', 'floppy', '1986'),
    'snes': (['Super NES'], 'nintendo', 'pad', '1990'),
    'sfc': (['Super', 'Famicom'], 'nintendo', 'pad', '1990'),
    'n64': (['Nintendo 64'], 'nintendo', 'pad', '1996'),
    'gc': (['GameCube'], 'nintendo', 'disc', '2001'),
    'wii': (['Wii'], 'nintendo', 'disc', '2006'),
    'wiiu': (['Wii U'], 'nintendo', 'disc', '2012'),
    'nsw': (['Switch'], 'nintendo', 'wide', '2017'),
    'gb': (['Game Boy'], 'nintendo', 'tall', '1989'),
    'gbc': (['Game Boy', 'Color'], 'nintendo', 'tall', '1998'),
    'gba': (['Game Boy', 'Advance'], 'nintendo', 'wide', '2001'),
    'nds': (['Nintendo DS'], 'nintendo', 'clam', '2004'),
    '3ds': (['Nintendo 3DS'], 'nintendo', 'clam', '2011'),
    'virtualboy': (['Virtual Boy'], 'nintendo', 'pad', '1995'),
    'gameandwatch': (['Game', '& Watch'], 'nintendo', 'wide', '1980'),
    'pokemini': (['Pokémon', 'Mini'], 'nintendo', 'tall', '2001'),
    # Sega
    'sg-1000': (['SG-1000'], 'sega', 'pad', '1983'),
    'mastersystem': (['Master', 'System'], 'sega', 'pad', '1985'),
    'megadrive': (['Mega Drive'], 'sega', 'pad', '1988'),
    'genesis': (['Genesis'], 'sega', 'pad', '1989'),
    'segacd': (['Sega CD'], 'sega', 'disc', '1991'),
    'sega32x': (['32X'], 'sega', 'pad', '1994'),
    'gamegear': (['Game Gear'], 'sega', 'wide', '1990'),
    'saturn': (['Saturn'], 'sega', 'disc', '1994'),
    'dreamcast': (['Dreamcast'], 'sega', 'disc', '1998'),
    'naomi': (['NAOMI'], 'sega', 'cabinet', '1998'),
    # Sony
    'psx': (['PlayStation'], 'sony', 'disc', '1994'),
    'ps2': (['PlayStation 2'], 'sony', 'disc', '2000'),
    'ps3': (['PlayStation 3'], 'sony', 'disc', '2006'),
    'psp': (['PlayStation', 'Portable'], 'sony', 'wide', '2004'),
    'psvita': (['PlayStation', 'Vita'], 'sony', 'wide', '2011'),
    # Microsoft
    'xbox': (['Xbox'], 'microsoft', 'disc', '2001'),
    'xbox360': (['Xbox 360'], 'microsoft', 'disc', '2005'),
    # Atari
    'atari2600': (['Atari 2600'], 'atari', 'stick', '1977'),
    'atari5200': (['Atari 5200'], 'atari', 'stick', '1982'),
    'atari7800': (['Atari 7800'], 'atari', 'stick', '1986'),
    'atari800': (['Atari 8-bit'], 'atari', 'computer', '1979'),
    'atarist': (['Atari ST'], 'atari', 'computer', '1985'),
    'atarilynx': (['Lynx'], 'atari', 'wide', '1989'),
    'atarijaguar': (['Jaguar'], 'atari', 'pad', '1993'),
    'atarijaguarcd': (['Jaguar CD'], 'atari', 'disc', '1995'),
    # NEC
    'pcengine': (['PC Engine'], 'nec', 'pad', '1987'),
    'tg16': (['TurboGrafx', '16'], 'nec', 'pad', '1989'),
    'tg-cd': (['TurboGrafx', 'CD'], 'nec', 'disc', '1989'),
    'pcenginecd': (['PC Engine', 'CD'], 'nec', 'disc', '1988'),
    'supergrafx': (['SuperGrafx'], 'nec', 'pad', '1989'),
    'pcfx': (['PC-FX'], 'nec', 'disc', '1994'),
    'pc88': (['PC-88'], 'nec', 'computer', '1981'),
    'pc98': (['PC-98'], 'nec', 'computer', '1982'),
    # SNK
    'neogeo': (['Neo Geo'], 'snk', 'cabinet', '1990'),
    'neogeocd': (['Neo Geo CD'], 'snk', 'disc', '1994'),
    'ngp': (['Neo Geo', 'Pocket'], 'snk', 'wide', '1998'),
    'ngpc': (['Neo Geo', 'Pocket Color'], 'snk', 'wide', '1999'),
    # Bandai
    'wonderswan': (['WonderSwan'], 'bandai', 'wide', '1999'),
    'wonderswancolor': (['WonderSwan', 'Color'], 'bandai', 'wide', '2000'),
    # Other consoles
    '3do': (['3DO'], 'other', 'disc', '1993'),
    'colecovision': (['ColecoVision'], 'other', 'stick', '1982'),
    'intellivision': (['Intellivision'], 'other', 'stick', '1979'),
    'vectrex': (['Vectrex'], 'other', 'stick', '1982'),
    'channelf': (['Channel F'], 'other', 'stick', '1976'),
    'ody2': (['Odyssey²'], 'other', 'stick', '1978'),
    'videopac': (['Videopac'], 'other', 'stick', '1978'),
    'cdi': (['CD-i'], 'other', 'disc', '1991'),
    # Computers
    'dos': (['DOS'], 'computer', 'computer', 'PC'),
    'pc': (['PC'], 'computer', 'computer', 'Windows'),
    'pc-cd': (['PC CD-ROM'], 'computer', 'disc', 'PC'),
    'steam': (['Steam'], 'computer', 'computer', 'PC'),
    'macintosh': (['Macintosh'], 'computer', 'computer', '1984'),
    'apple2': (['Apple II'], 'computer', 'computer', '1977'),
    'amiga': (['Amiga'], 'commodore', 'computer', '1985'),
    'c64': (['Commodore', '64'], 'commodore', 'computer', '1982'),
    'msx': (['MSX'], 'computer', 'computer', '1983'),
    'zxspectrum': (['ZX', 'Spectrum'], 'computer', 'computer', '1982'),
    'amstradcpc': (['Amstrad', 'CPC'], 'computer', 'computer', '1984'),
    'dragon32': (['Dragon 32'], 'computer', 'computer', '1982'),
    'x68000': (['X68000'], 'computer', 'computer', '1987'),
    'scummvm': (['ScummVM'], 'computer', 'cursor', 'Adventures'),
    'residualvm': (['ResidualVM'], 'computer', 'cursor', '3D adventures'),
    'ags': (['Adventure', 'Game Studio'], 'computer', 'cursor', 'Adventures'),
    'zmachine': (['Z-machine'], 'computer', 'cursor', 'Text adventures'),
    'love': (['LÖVE'], 'computer', 'cursor', 'Games made with it'),
    'ports': (['Ports'], 'computer', 'cursor', 'Games rebuilt to run here'),
    'kodi': (['Kodi'], 'other', 'screen', 'Films and music'),
    'retropie': (['Settings'], 'other', 'cog', 'This device'),
    # Arcade
    'arcade': (['Arcade'], 'arcade', 'cabinet', None),
    'mame': (['MAME'], 'arcade', 'cabinet', 'Arcade'),
    'mame-libretro': (['MAME'], 'arcade', 'cabinet', 'Arcade'),
    'fba': (['FinalBurn'], 'arcade', 'cabinet', 'Arcade'),
    'fbneo': (['FinalBurn', 'Neo'], 'arcade', 'cabinet', 'Arcade'),
    'cps1': (['CPS-1'], 'arcade', 'cabinet', '1988'),
    'cps2': (['CPS-2'], 'arcade', 'cabinet', '1993'),
    'cps3': (['CPS-3'], 'arcade', 'cabinet', '1996'),
    'daphne': (['Laserdisc'], 'arcade', 'disc', 'Arcade'),
    # EmulationStation's own lists
    'auto-allgames': (['All games'], 'list', 'grid', None),
    'auto-favorites': (['Favourites'], 'list', 'star', None),
    'auto-lastplayed': (['Last played'], 'list', 'clock', None),
    'custom-collections': (['Collections'], 'list', 'folder', None),
    # A system RetroManager has no line for here
    '_default': (['Games'], 'other', 'pad', None),
}

INK = 'fill="#fff"'
CUT = 'fill="#000" fill-opacity="0.38"'


def _rect(x, y, w, h, r, style=INK):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" {style}/>'


def _circle(x, y, r, style=INK):
    return f'<circle cx="{x}" cy="{y}" r="{r}" {style}/>'


def _plus(x, y, arm, thick, style=CUT):
    """A direction pad: a plus, centred on x, y."""
    return _rect(x - arm, y - thick / 2, arm * 2, thick, thick / 4, style) + _rect(x - thick / 2, y - arm, thick, arm * 2, thick / 4, style)


# The drawings, in a box 360 wide and 250 high whose middle is 0, 0
def _pad():
    return (_rect(-170, -78, 340, 156, 78) + _plus(-88, 0, 38, 24)
            + _circle(70, 22, 19, CUT) + _circle(112, -22, 19, CUT) + _rect(-22, 30, 44, 12, 6, CUT))


def _tall():
    return (_rect(-92, -125, 184, 250, 22) + _rect(-66, -99, 132, 104, 8, CUT) + _plus(-44, 62, 26, 17)
            + _circle(34, 76, 14, CUT) + _circle(66, 50, 14, CUT))


def _wide():
    return (_rect(-180, -80, 360, 160, 40) + _rect(-78, -56, 156, 112, 8, CUT) + _plus(-128, 0, 28, 18)
            + _circle(116, 20, 14, CUT) + _circle(144, -14, 14, CUT))


def _clam():
    return (_rect(-120, -125, 240, 118, 18) + _rect(-88, -103, 176, 76, 6, CUT)
            + _rect(-120, 7, 240, 118, 18) + _rect(-52, 27, 104, 78, 6, CUT) + _plus(-88, 66, 20, 13)
            + _circle(78, 76, 10, CUT) + _circle(98, 54, 10, CUT))


def _disc():
    return (_circle(0, 0, 122) + _circle(0, 0, 122, 'fill="none" stroke="#000" stroke-opacity="0.2" stroke-width="2"')
            + _circle(0, 0, 76, 'fill="none" stroke="#000" stroke-opacity="0.16" stroke-width="26"')
            + _circle(0, 0, 34, CUT) + _circle(0, 0, 13))


def _floppy():
    return (_rect(-112, -118, 224, 236, 12) + _rect(-66, -118, 132, 84, 4, CUT) + _rect(22, -106, 26, 60, 3)
            + _rect(-78, 14, 156, 104, 6, CUT))


def _stick():
    return (_rect(-120, 52, 240, 66, 16) + _rect(-13, -62, 26, 124, 10) + _circle(0, -78, 42) + _circle(74, 84, 15, CUT))


def _computer():
    return (_rect(-142, -122, 284, 182, 14) + _rect(-118, -100, 236, 138, 6, CUT) + _rect(-24, 60, 48, 28, 0)
            + _rect(-166, 90, 332, 34, 9)
            + ''.join(_rect(-146 + i * 30, 99, 20, 14, 3, CUT) for i in range(10)))


def _cabinet():
    return ('<path d="M-98 -125 H98 V-98 L80 -70 V30 L112 62 V125 H-112 V62 L-80 30 V-70 L-98 -98 Z" ' + INK + '/>'
            + _rect(-60, -62, 120, 82, 6, CUT) + _rect(-88, 42, 176, 20, 4, CUT)
            + _rect(-52, 22, 8, 26, 3) + _circle(-48, 18, 11) + _circle(22, 44, 8) + _circle(48, 44, 8))


def _cursor():
    return (_rect(-150, -112, 300, 196, 14) + _rect(-126, -90, 252, 152, 6, CUT)
            + '<path d="M-40 -58 V34 L-14 12 L4 54 L24 45 L6 4 L40 2 Z" ' + INK + '/>' + _rect(-60, 84, 120, 28, 6))


def _screen():
    return (_rect(-166, -110, 332, 200, 14) + _rect(-142, -88, 284, 156, 6, CUT)
            + '<path d="M-26 -50 V30 L44 -10 Z" ' + INK + '/>' + _rect(-70, 96, 140, 20, 8))


def _cog():
    teeth = ''.join(f'<rect x="-20" y="-126" width="40" height="252" rx="8" {INK} transform="rotate({a})"/>' for a in (0, 45, 90, 135))
    return teeth + _circle(0, 0, 92) + _circle(0, 0, 40, CUT)


def _grid():
    return ''.join(_rect(-116 + c * 82, -116 + r * 82, 68, 68, 10) for r in range(3) for c in range(3))


def _star():
    return '<path d="M0 -124 L36 -42 L124 -34 L57 24 L77 111 L0 65 L-77 111 L-57 24 L-124 -34 L-36 -42 Z" ' + INK + ' stroke="#fff" stroke-width="10" stroke-linejoin="round"/>'


def _clock():
    return _circle(0, 0, 120) + _circle(0, 0, 96, CUT) + _rect(-9, -72, 18, 82, 9) + _rect(-8, -9, 66, 18, 9) + _circle(0, 0, 14)


def _folder():
    return '<path d="M-150 -92 H-40 L-8 -58 H150 V104 H-150 Z" ' + INK + ' stroke="#fff" stroke-width="16" stroke-linejoin="round"/>' + _rect(-150, -30, 300, 12, 0, CUT)


DRAWINGS = {'pad': _pad, 'tall': _tall, 'wide': _wide, 'clam': _clam, 'disc': _disc, 'floppy': _floppy, 'stick': _stick,
            'computer': _computer, 'cabinet': _cabinet, 'cursor': _cursor, 'screen': _screen, 'cog': _cog,
            'grid': _grid, 'star': _star, 'clock': _clock, 'folder': _folder}
FONT = "font-family=\"'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif\""


def tile(lines, maker, kind, note):
    light, dark, maker_name = MAKERS[maker]
    # The name as big as it fits (a letter is about 0.58 of its height wide, bold)
    size = min(104 if len(lines) == 1 else 86, int(620 / (0.58 * max(len(line) for line in lines))))
    gap = int(size * 1.08)
    first = 478 + (0 if len(lines) == 1 else -gap * (len(lines) - 1) / 2) + size * 0.18
    title = ''.join(f'<text x="360" y="{first + i * gap:.0f}" font-size="{size}" font-weight="800" letter-spacing="-1" text-anchor="middle" fill="#fff" {FONT}>{escape(line)}</text>'
                    for i, line in enumerate(lines))
    under = ' · '.join(part for part in (maker_name, note) if part)
    sub = (f'<text x="360" y="644" font-size="34" font-weight="600" letter-spacing="3" text-anchor="middle" fill="#fff" fill-opacity="0.78" {FONT}>{escape(under.upper())}</text>'
           if under else '')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}" role="img" aria-label="{escape(' '.join(lines))}">
<defs>
<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{light}"/><stop offset="1" stop-color="{dark}"/></linearGradient>
<pattern id="p" width="36" height="36" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="18" height="36" fill="#fff" fill-opacity="0.035"/></pattern>
<radialGradient id="s" cx="0.5" cy="0.32" r="0.6"><stop offset="0" stop-color="#fff" stop-opacity="0.2"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
</defs>
<rect width="{SIZE}" height="{SIZE}" fill="url(#g)"/><rect width="{SIZE}" height="{SIZE}" fill="url(#p)"/><rect width="{SIZE}" height="{SIZE}" fill="url(#s)"/>
<g transform="{'translate(360 222)' if len(lines) == 1 else 'translate(360 204) scale(0.9)'}" fill-opacity="0.94">{DRAWINGS[kind]()}</g>
{title}
{sub}
</svg>
'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (lines, maker, kind, note) in SYSTEMS.items():
        (OUT / f'{name}.svg').write_text(tile(lines, maker, kind, note), encoding='utf-8')
    print(f"Wrote {len(SYSTEMS)} tiles to {OUT}")


if __name__ == '__main__':
    main()
