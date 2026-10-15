"""
Makes a demo library of made-up games, for screenshots of RetroManager that
show no one else's games: every name, description and picture here is
invented, and the pictures (box, spine, screenshot, logo) are drawn by this
script from shapes and Pillow's own font. The "ROM" files are a few bytes of
nothing: they don't run.

    python tools/make_demo_library.py <folder>

makes <folder>/roms, <folder>/media and the rest, the layout RetroManager
expects; point it there (as tools/take_screenshots.py does) to look at it.
"""

import os
import random
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# system folder -> (file extension, years the games are from, box shape (w, h), spine width)
SYSTEMS = {
    'atari2600': ('.a26', (1978, 1984), (300, 400), 50),
    'nes': ('.nes', (1985, 1993), (290, 400), 44),
    'mastersystem': ('.sms', (1986, 1993), (290, 400), 44),
    'snes': ('.sfc', (1991, 1998), (400, 290), 50),
    'megadrive': ('.md', (1990, 1997), (290, 410), 56),
    'gb': ('.gb', (1990, 1999), (300, 300), 34),
    'n64': ('.z64', (1996, 2002), (400, 290), 56),
    'psx': ('.cue', (1995, 2003), (400, 400), 40),
    'gba': ('.gba', (2001, 2008), (300, 300), 34),
    'nds': ('.nds', (2005, 2012), (300, 270), 30),
}
WORDS_A = ['Star', 'Moon', 'Pixel', 'Crystal', 'Thunder', 'Neon', 'Shadow', 'Rocket', 'Copper', 'Velvet', 'Comet', 'Ember',
           'Frost', 'Turbo', 'Echo', 'Lumen', 'Nova', 'Cobalt', 'Willow', 'Quartz', 'Orbit', 'Maple', 'Tidal', 'Solar']
WORDS_B = ['Knights', 'Racer', 'Quest', 'Garden', 'Legends', 'Patrol', 'Odyssey', 'Kingdom', 'Rally', 'Harbour', 'Drift',
           'Academy', 'Frontier', 'Circus', 'Voyage', 'Workshop', 'Arena', 'Tales', 'Express', 'Island', 'Mansion', 'Derby']
GENRES = ['Platform', 'Racing', 'Puzzle', 'Role Playing Game', 'Shooter', 'Adventure', 'Sports', 'Fighting', 'Strategy']
STUDIOS = ['Bright Hill Games', 'Paper Lantern', 'Studio Kestrel', 'Northwind Soft', 'Little Orbit Works', 'Mosaic Bay',
           'Tin Robot', 'Harbourlight', 'Quiet Fox Studio', 'Sunday Arcade']
PALETTES = [((32, 40, 110), (236, 92, 140)), ((18, 80, 92), (250, 196, 70)), ((70, 26, 92), (90, 220, 230)),
            ((140, 30, 40), (255, 210, 120)), ((20, 60, 40), (170, 240, 120)), ((40, 40, 48), (255, 130, 60)),
            ((10, 30, 70), (120, 170, 255)), ((96, 52, 20), (255, 236, 180))]


def font(size):
    return ImageFont.load_default(size=size)


def gradient(size, top, bottom):
    w, h = size
    im = Image.new('RGB', size, top)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return im


def scene(im, rng, accent):
    """Hills, a sun or moon, and a scatter of stars or shapes."""
    w, h = im.size
    d = ImageDraw.Draw(im)
    for _ in range(40):
        x, y, r = rng.uniform(0, w), rng.uniform(0, h * 0.6), rng.uniform(0.6, 2.2)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    cx, cy, r = rng.uniform(w * 0.2, w * 0.8), rng.uniform(h * 0.15, h * 0.4), rng.uniform(w * 0.08, w * 0.16)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
    for layer in range(3):
        base = h * (0.62 + layer * 0.1)
        shade = tuple(max(0, int(c * (0.35 + layer * 0.15))) for c in accent)
        points = [(0, h)]
        for i in range(9):
            points.append((w * i / 8, base - rng.uniform(0, h * 0.12)))
        points.append((w, h))
        d.polygon(points, fill=shade)


def title_lines(name, width, size):
    words, lines, line = name.split(), [], ''
    f = font(size)
    for word in words:
        trial = (line + ' ' + word).strip()
        if f.getlength(trial) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    return lines


def box(name, system, palette, rng, size):
    w, h = size
    im = gradient(size, palette[0], tuple(min(255, c // 3) for c in palette[0]))
    scene(im, rng, palette[1])
    d = ImageDraw.Draw(im)
    # A band along the top with the title
    d.rectangle([0, 0, w, int(h * 0.27)], fill=tuple(c // 2 for c in palette[0]))
    size_t = max(22, int(w * 0.1))
    for i, line in enumerate(title_lines(name, w * 0.86, size_t)[:2]):
        d.text((w * 0.07 + 2, h * 0.04 + i * size_t * 1.1 + 2), line, font=font(size_t), fill=(0, 0, 0))
        d.text((w * 0.07, h * 0.04 + i * size_t * 1.1), line, font=font(size_t), fill=(255, 255, 255))
    d.rectangle([0, h - 26, w, h], fill=(16, 16, 20))
    d.text((10, h - 22), 'DEMO · MADE-UP GAME', font=font(14), fill=palette[1])
    return im


def spine(name, palette, size):
    w, h = size   # (the spine stands up: drawn long and turned)
    strip = Image.new('RGB', (h, w), tuple(c // 2 for c in palette[0]))
    d = ImageDraw.Draw(strip)
    d.rectangle([0, 0, 18, w], fill=palette[1])
    d.text((30, w / 2 - 11), name, font=font(max(14, int(w * 0.42))), fill=(255, 255, 255))
    return strip.rotate(90, expand=True)


def screenshot(palette, rng):
    """A small picture of a made-up game, scaled up with its pixels square."""
    w, h = 160, 120
    im = gradient((w, h), palette[0], tuple(min(255, c + 40) for c in palette[0]))
    d = ImageDraw.Draw(im)
    for x in range(0, w, 16):
        top = h - 16 - rng.choice([0, 0, 16, 32])
        d.rectangle([x, top, x + 15, h], fill=tuple(c // 2 for c in palette[1]))
        d.rectangle([x, top, x + 15, top + 3], fill=palette[1])
    px = rng.randrange(20, w - 30)
    d.rectangle([px, h - 46, px + 9, h - 33], fill=(255, 255, 255))
    for _ in range(5):
        x, y = rng.randrange(8, w - 8), rng.randrange(10, h - 60)
        d.ellipse([x, y, x + 5, y + 5], fill=palette[1])
    d.text((4, 3), f'SCORE {rng.randrange(1, 99) * 100:06d}', font=font(9), fill=(255, 255, 255))
    return im.resize((640, 480), Image.NEAREST)


def logo(name, palette):
    f = font(64)
    width = int(f.getlength(name)) + 40
    im = Image.new('RGBA', (width, 110), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((20, 18), name, font=f, fill=palette[1] + (255,), stroke_width=6, stroke_fill=(20, 20, 30, 255))
    return im


def main(target: Path):
    rng = random.Random(2026)
    names, used = [], set()
    while len(names) < 90:
        name = f"{rng.choice(WORDS_A)} {rng.choice(WORDS_B)}"
        if name not in used:
            used.add(name)
            names.append(name)
    (target / 'retromanager').mkdir(parents=True, exist_ok=True)
    (target / 'retromanager' / 'setup.json').write_text('{"done": true}')
    for sub in ('saves', 'savestates', 'BIOS', 'inbox', 'save-backups'):
        (target / sub).mkdir(parents=True, exist_ok=True)
    # Point RetroManager at it to learn each system's media folder name
    os.environ.update(ROMS_PATH=str(target / 'roms'), MEDIA_PATH=str(target / 'media'), DATA_PATH=str(target / 'retromanager'),
                      RETROMANAGER_NO_BACKGROUND='1', LOG_LEVEL='WARNING')
    per_system = {system: [] for system in SYSTEMS}
    for i, name in enumerate(names):
        per_system[list(SYSTEMS)[i % len(SYSTEMS)]].append(name)
    for system, (ext, (start, end), shape, spine_w) in SYSTEMS.items():
        folder = target / 'roms' / system
        folder.mkdir(parents=True, exist_ok=True)
        for name in per_system[system]:
            (folder / f"{name}{ext}").write_bytes(b'RetroManager demo: not a game\n')
    # (a media folder named after each system, so each finds its own and not a neighbour's)
    for system in SYSTEMS:
        (target / 'media' / system).mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend.core import scanner
    for system, (ext, (start, end), shape, spine_w) in SYSTEMS.items():
        media_system = scanner.media_index(system).media_system
        media = target / 'media' / media_system
        entries = []
        for name in per_system[system]:
            palette = rng.choice(PALETTES)
            game_rng = random.Random(name)
            year = rng.randint(start, end)
            studio = rng.choice(STUDIOS)
            genre = rng.choice(GENRES)
            pictures = {
                'box2d': box(name, system, palette, game_rng, shape),
                'boxside': spine(name, palette, (spine_w, shape[1])),
                'screenshot': screenshot(palette, game_rng),
                'wheel': logo(name, palette),
            }
            for kind, picture in pictures.items():
                (media / kind).mkdir(parents=True, exist_ok=True)
                picture.save(media / kind / f"{name}.png")
            desc = (f"{name} is a made-up {genre.lower()} game, invented for RetroManager's demo library. "
                    f"Nothing about it is real: not the game, not {studio}, and not this picture of it.")
            entries.append(f"""  <game>
    <path>./{escape(name)}{ext}</path>
    <name>{escape(name)}</name>
    <desc>{escape(desc)}</desc>
    <image>../../media/{escape(media_system)}/box2d/{escape(name)}.png</image>
    <thumbnail>../../media/{escape(media_system)}/screenshot/{escape(name)}.png</thumbnail>
    <rating>{rng.choice([0.5, 0.6, 0.7, 0.8, 0.9])}</rating>
    <releasedate>{year}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}T000000</releasedate>
    <developer>{escape(studio)}</developer>
    <publisher>{escape(rng.choice(STUDIOS))}</publisher>
    <genre>{escape(genre)}</genre>
    <players>{rng.choice(['1', '1', '1-2', '1-4'])}</players>
  </game>""")
        (folder := target / 'roms' / system).mkdir(exist_ok=True)
        # A little for Library health to show: games with no entry yet, and a picture nothing uses
        if system in ('nes', 'psx', 'gba'):
            (folder / f"Untitled Prototype{ext}").write_bytes(b'RetroManager demo: not a game\n')
        if system == 'snes':
            screenshot(rng.choice(PALETTES), random.Random(system)).save(media / 'screenshot' / 'Old Picture.png')
        (folder / 'gamelist.xml').write_text('<?xml version="1.0"?>\n<gameList>\n' + '\n'.join(entries) + '\n</gameList>\n')
        print(f"{system}: {len(entries)} games, pictures in media/{media_system}")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).resolve())
