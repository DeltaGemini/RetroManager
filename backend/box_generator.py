"""
Spines and 3D boxes made from a game's own pictures (Fill the gaps' "Generate one").

A spine is made when a game has none: for a disc game or a Mega Drive (and for a
cardboard box whose edge is busy), the look of the system's case, black with its
band; for a cardboard box, the cover's edge colour. Both carry the game's logo
(its wheel picture) along them, or its name.

A 3D box is the cover on the front of a box seen turned, with the spine (the
game's own, or a made one) on the left, or underneath for a landscape cover
(SNES, N64), as ScreenScraper's are. Plastic cases get their border: a keep case
(GameCube, PS2...) its rounded rim, a jewel case its clear frame, a Mega Drive
clamshell its edge.
"""

import math
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

from backend.systems import _PRIMARY, normalize_system_name

FONT = Path(__file__).resolve().parent.parent / 'frontend' / 'themes' / 'starship' / 'Antonio.ttf'
# The long side of a made 3D box
BOX_SIZE = 700
BLACK = (16, 16, 18)

# Case kinds: spine depth (of the cover's long edge), the case's colour, and its band
# at the top of the spine (colour, text colour, text)
_CARD = {'case': 'card', 'depth': 0.145}
_CASES = {
    'nes': {'case': 'card', 'depth': 0.145, 'badge': ((200, 20, 30), (255, 255, 255), 'NES')},
    'snes': {'case': 'card', 'depth': 0.15, 'label': 'SUPER NINTENDO'},
    'n64': {'case': 'card', 'depth': 0.16, 'badge': ((20, 20, 20), (240, 240, 240), 'NINTENDO 64')},
    'megadrive': {'case': 'clamshell', 'depth': 0.14, 'label': 'MEGA DRIVE'},
    'mastersystem': {'case': 'clamshell', 'depth': 0.14, 'label': 'MASTER SYSTEM'},
    'sega32x': {'case': 'clamshell', 'depth': 0.14, 'label': '32X'},
    'psx': {'case': 'jewel', 'depth': 0.05, 'label': 'PlayStation'},
    'saturn': {'case': 'jewel', 'depth': 0.05, 'label': 'SEGA SATURN'},
    'dreamcast': {'case': 'jewel', 'depth': 0.05, 'label': 'DREAMCAST'},
    'segacd': {'case': 'jewel', 'depth': 0.05, 'label': 'MEGA-CD'},
    'pcengine': {'case': 'jewel', 'depth': 0.05, 'label': 'PC ENGINE'},
    'pcenginecd': {'case': 'jewel', 'depth': 0.05, 'label': 'CD-ROM²'},
    'neogeocd': {'case': 'jewel', 'depth': 0.05, 'label': 'NEO GEO CD'},
    '3do': {'case': 'jewel', 'depth': 0.05, 'label': '3DO'},
    'atarijaguarcd': {'case': 'jewel', 'depth': 0.05, 'label': 'JAGUAR CD'},
    'pcfx': {'case': 'jewel', 'depth': 0.05, 'label': 'PC-FX'},
    'ps2': {'case': 'keepcase', 'depth': 0.08, 'band': ((235, 235, 240), (20, 40, 140), 'PlayStation 2')},
    'gc': {'case': 'keepcase', 'depth': 0.08, 'band': ((44, 44, 48), (230, 230, 230), 'GAMECUBE')},
    'wii': {'case': 'keepcase', 'depth': 0.08, 'colour': (232, 232, 234), 'band': ((200, 200, 204), (40, 40, 44), 'Wii')},
    'xbox': {'case': 'keepcase', 'depth': 0.08, 'band': ((40, 150, 40), (255, 255, 255), 'XBOX')},
    'xbox360': {'case': 'keepcase', 'depth': 0.08, 'band': ((235, 235, 235), (60, 150, 30), 'XBOX 360')},
    'ps3': {'case': 'keepcase', 'depth': 0.07, 'band': ((30, 30, 34), (230, 230, 230), 'PS3')},
    'psp': {'case': 'keepcase', 'depth': 0.08, 'band': ((30, 30, 34), (230, 230, 230), 'PSP')},
    'nds': {'case': 'keepcase', 'depth': 0.11, 'band': ((60, 60, 64), (240, 240, 240), 'NINTENDO DS')},
    '3ds': {'case': 'keepcase', 'depth': 0.11, 'colour': (232, 232, 234), 'band': ((210, 20, 30), (255, 255, 255), '3DS')},
    'nsw': {'case': 'keepcase', 'depth': 0.08, 'colour': (200, 20, 30), 'band': ((200, 20, 30), (255, 255, 255), 'NINTENDO SWITCH')},
}


class BoxError(Exception):
    pass


def case_for(system: str) -> dict:
    return _CASES.get(_PRIMARY.get(normalize_system_name(system), ''), _CARD)


def _shape(cover: Image.Image, system: str) -> str:
    """A cardboard box lies down when its cover is wider than tall (SNES, N64); a plastic case
    always stands (a PS1 cover is a little wider than tall, its spine still on the left)"""
    return 'landscape' if case_for(system)['case'] == 'card' and cover.width > cover.height * 1.05 else 'portrait'


# ---- Drawing helpers ----
def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT), max(6, size))
    except OSError:
        return ImageFont.load_default()


def _fit_text(text: str, width: float, height: float) -> ImageFont.FreeTypeFont:
    size = int(height)
    while size > 6:
        font = _font(size)
        if font.getlength(text) <= width:
            return font
        size -= 1
    return _font(6)


def _edge(cover: Image.Image, shape: str) -> Image.Image:
    """The strip of the cover along where the spine joins it."""
    rgb = cover.convert('RGB')
    w, h = rgb.size
    return rgb.crop((0, 0, max(2, w // 12), h)) if shape == 'portrait' else rgb.crop((0, h - max(2, h // 12), w, h))


def _edge_colour(cover: Image.Image, shape: str) -> Tuple[int, int, int]:
    return tuple(int(v) for v in ImageStat.Stat(_edge(cover, shape)).median)


def _busy(cover: Image.Image, shape: str) -> bool:
    """An edge with a picture on it rather than a colour: a made spine of that colour would look wrong."""
    return sum(ImageStat.Stat(_edge(cover, shape)).stddev) / 3 > 45


def _ink(rgb) -> Tuple[int, int, int]:
    return (20, 20, 20) if 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] > 150 else (245, 245, 245)


def _spine_size(cover: Image.Image, shape: str, depth: float) -> Tuple[int, int]:
    w, h = cover.size
    return (max(8, round(h * depth)), h) if shape == 'portrait' else (w, max(8, round(w * depth)))


# ---- Spines ----
def make_spine(cover: Image.Image, logo: Optional[Image.Image], title: str, system: str) -> Image.Image:
    """A spine for a game that has none, the size of the cover's edge: standing for a portrait cover, lying for a landscape one."""
    if cover is None:
        raise BoxError("It needs a cover (Box 2D) to make one from")
    cover = cover.convert('RGBA')
    shape = _shape(cover, system)
    case = case_for(system)
    size = _spine_size(cover, shape, case['depth'])
    long_, short = (size[1], size[0]) if shape == 'portrait' else size
    cased = case['case'] != 'card' or _busy(cover, shape)
    bg = case.get('colour', BLACK) if cased else _edge_colour(cover, shape)
    s = Image.new('RGBA', (long_, short), bg + (255,))
    d = ImageDraw.Draw(s)
    ink = _ink(bg)
    x = int(short * 0.25)
    band = case.get('band') or (case.get('badge') if cased else None)
    if band:
        width = int(long_ * 0.17)
        d.rectangle((0, 0, width, short), fill=band[0])
        d.text((width / 2, short / 2), band[2], font=_fit_text(band[2], width - short * 0.3, short * 0.42), fill=band[1], anchor='mm')
        x = width + int(short * 0.3)
    elif case.get('label'):
        font = _fit_text(case['label'], long_ * 0.22, short * 0.3)
        d.text((x, short / 2), case['label'], font=font, fill=(170, 170, 180) if cased else ink, anchor='lm')
        x += int(font.getlength(case['label'])) + int(short * 0.4)
    room = (x, int(short * 0.08), long_ - int(short * 0.25), int(short * 0.92))
    if logo is not None:
        mark = logo.convert('RGBA')
        bbox = mark.getbbox()
        if bbox:
            mark = mark.crop(bbox)
        mark.thumbnail((room[2] - room[0], room[3] - room[1]), Image.LANCZOS)
        s.alpha_composite(mark, (room[0] + (room[2] - room[0] - mark.width) // 2, room[1] + (room[3] - room[1] - mark.height) // 2))
    else:
        text = (title or '').upper()
        d.text(((room[0] + room[2]) / 2, short / 2), text, font=_fit_text(text, room[2] - room[0], short * 0.55), fill=ink, anchor='mm')
    if case['case'] == 'clamshell':  # the ridges at the ends of a clamshell
        step = max(3, short // 12)
        for at in list(range(0, int(long_ * 0.08), step)) + list(range(int(long_ * 0.92), long_, step)):
            d.line((at, 0, at, short), fill=(52, 52, 56), width=1)
    elif case['case'] == 'jewel':  # a jewel case's hinge
        edge = max(2, short // 7)
        d.rectangle((0, 0, long_, edge), fill=(62, 62, 66))
        d.rectangle((0, short - edge, long_, short), fill=(62, 62, 66))
    return s.rotate(-90, expand=True) if shape == 'portrait' else s


# ---- The front of a case ----
def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=radius, fill=255)
    img.putalpha(ImageChops.darker(img.getchannel('A'), mask))
    return img


def case_front(cover: Image.Image, system: str) -> Image.Image:
    """The cover as the front of its case: in a keep case's rim, a jewel case's frame or a clamshell's edge."""
    case = case_for(system)
    kind = case['case']
    cover = cover.convert('RGBA')
    if kind == 'card':
        return cover
    w, h = cover.size
    if kind == 'keepcase':
        side, top, radius, colour = int(w * 0.035), int(h * 0.022), int(w * 0.045), case.get('colour', BLACK)
    elif kind == 'jewel':
        side, top, radius, colour = int(w * 0.018), int(h * 0.018), 2, (178, 182, 188)
    else:
        side, top, radius, colour = int(w * 0.025), int(h * 0.02), int(w * 0.02), BLACK
    front = Image.new('RGBA', (w + 2 * side, h + 2 * top), colour + (255,))
    front.alpha_composite(cover, (side, top))
    d = ImageDraw.Draw(front)
    if kind == 'keepcase':  # the clear sleeve's edge over the cover
        d.rectangle((side - 2, top - 2, side + w + 1, top + h + 1), outline=(255, 255, 255, 50), width=2)
    elif kind == 'jewel':  # a clear frame catches the light
        d.rectangle((0, 0, front.width - 1, front.height - 1), outline=(235, 238, 242), width=max(1, side // 3))
        front.putalpha(Image.new('L', front.size, 255))
    return _rounded(front, radius)


# ---- 3D ----
def _turn(p, yaw, pitch):
    x, y, z = p
    x, z = x * math.cos(yaw) + z * math.sin(yaw), -x * math.sin(yaw) + z * math.cos(yaw)
    y, z = y * math.cos(pitch) - z * math.sin(pitch), y * math.sin(pitch) + z * math.cos(pitch)
    return x, y, z


def _solve(a, b):
    """Gaussian elimination (8 unknowns)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col and m[col][col]:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] for i in range(n)]


def _perspective(dst, src):
    """PIL PERSPECTIVE coefficients taking the output quad dst to the input corners src."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y]); rhs.append(v)
    return _solve(rows, rhs)


def _darken(img: Image.Image, factor: float) -> Image.Image:
    r, g, b, a = img.split()
    return Image.merge('RGBA', [c.point(lambda v: int(v * factor)) for c in (r, g, b)] + [a])


def make_box3d(cover: Image.Image, spine: Image.Image, system: str, size: int = BOX_SIZE) -> Image.Image:
    """The cover (in its case) on the front of a turned box, the spine on its left, or underneath for a landscape cover."""
    if cover is None:
        raise BoxError("It needs a cover (Box 2D) to make one from")
    cover = cover.convert('RGBA')
    shape = _shape(cover, system)
    front = case_front(cover, system)
    spine = spine.convert('RGBA')
    if shape == 'portrait' and spine.width > spine.height:
        spine = spine.rotate(-90, expand=True)
    elif shape == 'landscape' and spine.height > spine.width:
        spine = spine.rotate(90, expand=True)
    ss = 2
    W, H = front.size
    D = spine.width * H / spine.height if shape == 'portrait' else spine.height * W / spine.width
    yaw, pitch = (math.radians(-40), math.radians(3)) if shape == 'portrait' else (math.radians(-10), math.radians(-38))
    centre = (W / 2, H / 2, D / 2)
    distance = max(W, H) * 3.2

    def project(p):
        x, y, z = _turn((p[0] - centre[0], p[1] - centre[1], p[2] - centre[2]), yaw, pitch)
        f = distance / (z + distance)
        return x * f, y * f

    face = [(0, 0, 0), (W, 0, 0), (W, H, 0), (0, H, 0)]
    side = [(0, 0, D), (0, 0, 0), (0, H, 0), (0, H, D)] if shape == 'portrait' else [(0, H, 0), (W, H, 0), (W, H, D), (0, H, D)]
    pf, ps = [project(p) for p in face], [project(p) for p in side]
    xs, ys = [p[0] for p in pf + ps], [p[1] for p in pf + ps]
    pad = 2 * ss
    scale = (size * ss - 2 * pad - 1) / max(max(xs) - min(xs), max(ys) - min(ys))
    cw, ch = int((max(xs) - min(xs)) * scale) + 2 * pad, int((max(ys) - min(ys)) * scale) + 2 * pad
    place = lambda pts: [((x - min(xs)) * scale + pad, (y - min(ys)) * scale + pad) for x, y in pts]
    pf, ps = place(pf), place(ps)

    canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    for img, quad, light in ((spine, ps, 0.68), (front, pf, 1.0)):
        w, h = img.size
        warped = img.transform((cw, ch), Image.PERSPECTIVE, _perspective(quad, [(0, 0), (w, 0), (w, h), (0, h)]), Image.BICUBIC)
        mask = Image.new('L', (cw, ch), 0)
        ImageDraw.Draw(mask).polygon(quad, fill=255)
        warped.putalpha(ImageChops.darker(mask, warped.getchannel('A')))
        canvas.alpha_composite(_darken(warped, light) if light != 1.0 else warped)
    # A thin light edge where the faces meet, and a soft sheen across the front
    ImageDraw.Draw(canvas).line((pf[0], pf[3]) if shape == 'portrait' else (pf[3], pf[2]), fill=(255, 255, 255, 70), width=2 * ss)
    sheen = Image.new('L', (cw, ch), 0)
    ImageDraw.Draw(sheen).polygon(pf, fill=38)
    fade = Image.linear_gradient('L').rotate(35).resize((cw, ch)).point(lambda v: 255 - v)
    sheen = ImageChops.multiply(sheen, fade)
    white = Image.new('RGBA', (cw, ch), (255, 255, 255, 0))
    white.putalpha(ImageChops.darker(sheen, canvas.getchannel('A')))
    canvas.alpha_composite(white)
    return canvas.resize((max(1, cw // ss), max(1, ch // ss)), Image.LANCZOS)

