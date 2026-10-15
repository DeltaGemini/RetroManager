"""
Draws RetroManager's icon (frontend/icons/icon.svg) and makes the files that
use it: the app and home-screen icons (icon-192.png, icon-512.png) and the
browser tab's (frontend/favicon.ico).

It's a game cartridge in the logo's orange-to-purple, with "RM" on its label in
the logo's own block letters: shapes alone, no font and nobody's artwork. The
picture fills its square (a phone crops an icon to its own shape) and the
cartridge keeps to the middle, where no crop reaches.

    python tools/make_icon.py        (needs rsvg-convert and ImageMagick for the .png and .ico)
"""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'frontend'
SVG = ROOT / 'icons' / 'icon.svg'

R = ['11110', '10001', '10001', '11110', '10100', '10010', '10001']
M = ['10001', '11011', '10101', '10101', '10001', '10001', '10001']


def letters(left, top, cell):
    """"RM" in blocks: each filled square a little wide, so the strokes are heavy."""
    out = []
    for i, letter in enumerate((R, M)):
        for row, line in enumerate(letter):
            for col, on in enumerate(line):
                if on == '1':
                    out.append(f'<rect x="{left + (i * 6.4 + col) * cell:.1f}" y="{top + row * cell:.1f}" width="{cell * 1.45:.1f}" height="{cell + 0.4:.1f}"/>')
    return ''.join(out)


def icon(tab=False):
    """The icon. `tab`: for a browser tab, where it's tiny: the cartridge alone, filling the square, on nothing."""
    # The cartridge: a body with cut top corners, and the narrower edge that goes in the slot
    body = 'M150 92 H362 L398 128 V352 Q398 372 378 372 H134 Q114 372 114 352 V128 Z'
    view = '90 70 332 372' if tab else '0 0 512 512'
    behind = '' if tab else '''<rect width="512" height="512" fill="url(#night)"/>
  <rect width="512" height="512" fill="url(#glow)"/>
  <!-- Stars, as squares -->
  <g fill="#fff"><rect x="66" y="88" width="10" height="10" opacity="0.7"/><rect x="430" y="150" width="8" height="8" opacity="0.5"/><rect x="88" y="396" width="8" height="8" opacity="0.45"/><rect x="420" y="372" width="10" height="10" opacity="0.6"/><rect x="250" y="44" width="7" height="7" opacity="0.4"/></g>
  <!-- Its shadow -->
  <path d="''' + body + '''" transform="translate(0 14)" fill="#000" opacity="0.35"/>'''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="512" height="512" role="img" aria-label="RetroManager">
  <!-- RetroManager's icon (tools/make_icon.py): a cartridge, with RM in the logo's block letters -->
  <defs>
    <linearGradient id="night" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1b2150"/><stop offset="1" stop-color="#070a1c"/></linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.47" r="0.5"><stop offset="0" stop-color="#ff6a9a" stop-opacity="0.55"/><stop offset="0.6" stop-color="#a63fd0" stop-opacity="0.16"/><stop offset="1" stop-color="#a63fd0" stop-opacity="0"/></radialGradient>
    <linearGradient id="shell" gradientUnits="userSpaceOnUse" x1="114" y1="92" x2="398" y2="420"><stop offset="0" stop-color="#ff7a1f"/><stop offset="0.5" stop-color="#ea4f7e"/><stop offset="1" stop-color="#9a3bd6"/></linearGradient>
    <linearGradient id="ink" gradientUnits="userSpaceOnUse" x1="160" y1="150" x2="352" y2="270"><stop offset="0" stop-color="#ffd9a8"/><stop offset="0.5" stop-color="#ffffff"/><stop offset="1" stop-color="#e9c8ff"/></linearGradient>
    <clipPath id="in"><path d="{body}"/></clipPath>
  </defs>
  {behind}
  <!-- The edge that goes in the slot, with its contacts -->
  <rect x="158" y="360" width="196" height="64" rx="10" fill="#5b2a8c"/>
  <g fill="#ffd27a">{''.join(f'<rect x="{176 + i * 24}" y="390" width="12" height="34" rx="2"/>' for i in range(7))}</g>
  <path d="{body}" fill="url(#shell)"/>
  <g clip-path="url(#in)">
    <!-- Light across it, and shade along the bottom -->
    <path d="M114 92 H250 L150 372 H114 Z" fill="#fff" opacity="0.13"/>
    <rect x="114" y="336" width="284" height="36" fill="#000" opacity="0.16"/>
  </g>
  <!-- The label, and the grip under it -->
  <rect x="144" y="124" width="224" height="170" rx="14" fill="#0b0f2a"/>
  <rect x="144" y="124" width="224" height="170" rx="14" fill="none" stroke="#fff" stroke-opacity="0.22" stroke-width="3"/>
  <g fill="url(#ink)">{letters(163, 153, 16)}</g>
  <g fill="#000" opacity="0.28"><rect x="176" y="312" width="160" height="9" rx="4.5"/><rect x="176" y="330" width="160" height="9" rx="4.5"/></g>
</svg>
'''


def main():
    SVG.parent.mkdir(parents=True, exist_ok=True)
    SVG.write_text(icon(), encoding='utf-8')
    print(f"Wrote {SVG}")
    if not shutil.which('rsvg-convert') or not shutil.which('magick'):
        print("rsvg-convert or ImageMagick isn't here: the .png and .ico files weren't made")
        return
    for size in (192, 512):
        subprocess.run(['rsvg-convert', '-w', str(size), '-h', str(size), str(SVG), '-o', str(ROOT / 'icons' / f'icon-{size}.png')], check=True)
    tab = SVG.with_name('.tab.svg')
    tab.write_text(icon(tab=True), encoding='utf-8')
    subprocess.run(['rsvg-convert', '-w', '256', '-h', '256', '-a', str(tab), '-o', str(SVG.with_name('.tab.png'))], check=True)
    subprocess.run(['magick', str(SVG.with_name('.tab.png')), '-background', 'none', '-gravity', 'center', '-extent', '256x256',
                    '-define', 'icon:auto-resize=64,48,32,16', str(ROOT / 'favicon.ico')], check=True)
    tab.unlink()
    SVG.with_name('.tab.png').unlink()
    print("Made icon-192.png, icon-512.png and favicon.ico")


if __name__ == '__main__':
    main()
