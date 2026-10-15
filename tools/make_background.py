"""
Draws a night sky (frontend/open/background.svg) for the Switch colour themes
in a copy that's given to others: the picture those themes have here
(frontend/themes/switch/background.jpg) is a photograph of a nebula whose
source isn't recorded, so it can't be credited and isn't passed on.

This one is ours: a dark sky, a few soft clouds of colour and a scatter of
stars, the same every time it's drawn (the scatter is seeded). RetroManager
uses it wherever the other isn't there, and always when OPEN_ARTWORK=1
(backend/routes/pages.py).

    python tools/make_background.py
"""

import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'frontend' / 'open' / 'background.svg'
W, H = 1920, 1080
# (x, y, radius, colour, how strong) of each cloud
CLOUDS = [
    (420, 300, 620, '#6a3fb5', 0.55), (1450, 260, 560, '#b5483f', 0.42), (1080, 760, 700, '#2f6fa8', 0.40),
    (240, 900, 480, '#b5763f', 0.30), (1700, 880, 520, '#7a3fa8', 0.38), (900, 380, 380, '#e08a4a', 0.22),
]
STAR_COLOURS = ['#ffffff', '#ffffff', '#ffffff', '#ffe9c9', '#cfe0ff', '#ffd0d0']


def main():
    rng = random.Random(1983)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice">', '<defs>']
    for i, (_, _, _, colour, strength) in enumerate(CLOUDS):
        parts.append(f'<radialGradient id="c{i}"><stop offset="0" stop-color="{colour}" stop-opacity="{strength}"/>'
                     f'<stop offset="0.55" stop-color="{colour}" stop-opacity="{strength * 0.35:.3f}"/><stop offset="1" stop-color="{colour}" stop-opacity="0"/></radialGradient>')
    parts.append('<radialGradient id="glow"><stop offset="0" stop-color="#fff" stop-opacity="0.9"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>')
    parts.append('</defs>')
    parts.append(f'<rect width="{W}" height="{H}" fill="#0b0b16"/>')
    for i, (x, y, r, _, _) in enumerate(CLOUDS):
        parts.append(f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{int(r * 0.72)}" fill="url(#c{i})"/>')
    # Many faint stars, fewer bright ones, a handful with a glow
    for _ in range(620):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.choice([0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.3])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{rng.choice(STAR_COLOURS)}" opacity="{rng.uniform(0.25, 0.8):.2f}"/>')
    for _ in range(70):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.uniform(1.4, 2.1):.1f}" fill="{rng.choice(STAR_COLOURS)}" opacity="{rng.uniform(0.7, 1):.2f}"/>')
    for _ in range(14):
        x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(7, 13)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="url(#glow)" opacity="0.5"/><circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#fff"/>')
    parts.append('</svg>')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(parts) + '\n')
    print('Wrote', OUT, f'({OUT.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
