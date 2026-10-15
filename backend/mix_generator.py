"""
Make a Mix picture from the media a game already has: its screenshot, box,
cartridge or disc and logo, laid out like the Mix pictures scrapers make.

The layout is data. A template (a JSON file in backend/mix_templates/, or in
DATA_PATH/mix_templates/ to add or replace one without a rebuild) says where
each element goes, as fractions of the canvas, so the picture's size can change
without the layout changing:

    canvas      {"width", "height"} in pixels
    sources     for each role (screenshot, box, media, wheel), the media folders
                to take it from, first one the game has wins
    layers      the roles, back to front
    elements    for each role, either
                  "panel": [x, y, w, h]  the picture is fitted inside it
                                         ("fit": contain or cover), or
                  "anchor" + "max": [w, h]  the picture is scaled to fit max and
                                         its anchor point ("bottom-left",
                                         "top-center"...) is put at "pos", or
                                         "margin" in from that corner or edge
                "attach": {"to": role, "overlap"}  starts at that element's right
                                         edge instead (less the overlap)
                "variants": [{"when": {"missing": [...], "present": [...]},
                              "set": {...}}]  what changes when other elements
                                         are or aren't there
                "trim", "radius", "fill", "shadow": {"offset", "blur", "opacity"}
                "frame": {"width", "color", "radius", "edge"}  a bezel drawn
                                         around a panel

compute_layout() is the arithmetic alone (no pictures), so it can be tested.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter
from PIL.PngImagePlugin import PngInfo

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / 'mix_templates'
# In a template folder: which template each system gets ({"default", "systems"})
DEFAULTS_FILE = 'defaults.json'
ROLES = ('screenshot', 'box', 'media', 'wheel')
# Written into the PNG, so a generated Mix can be told from a scraped one
SOURCE_KEY = 'mix_source'
GENERATED = 'generated'

Size = Tuple[int, int]
Rect = Tuple[int, int, int, int]  # x, y, width, height


class MixError(Exception):
    """Why a game's Mix couldn't be made. `reason` is one of no_screenshot,
    screenshot_only, no_box_or_wheel, asset_unreadable, template."""

    def __init__(self, reason: str, detail: str = ''):
        super().__init__(detail or reason)
        self.reason = reason


# --- Templates ---

def _valid(template) -> bool:
    try:
        canvas = template['canvas']
        return (bool(template['name']) and int(canvas['width']) > 0 and int(canvas['height']) > 0
                and isinstance(template['elements'], dict) and isinstance(template['sources'], dict)
                and all('panel' in e or 'max' in e for e in template['elements'].values()))
    except (KeyError, TypeError, ValueError):
        return False


def load_templates(folders: Iterable[Path] = (TEMPLATE_DIR,)) -> Dict[str, Dict]:
    """{name: template} from every folder; a later folder's template replaces
    an earlier one with the same name. Files that aren't templates are skipped."""
    templates = {}
    for folder in folders:
        try:
            files = sorted(Path(folder).glob('*.json'))
        except OSError:
            continue
        for file in files:
            if file.name == DEFAULTS_FILE:
                continue
            try:
                template = json.loads(file.read_text(encoding='utf-8'))
            except (OSError, ValueError) as e:
                logger.warning(f"Mix template {file} can't be read: {e}")
                continue
            if not _valid(template):
                logger.warning(f"Mix template {file} is missing its name, canvas, sources or elements")
                continue
            templates[template['name']] = template
    return templates


def default_template(system: str, templates: Dict[str, Dict], folders: Iterable[Path] = (TEMPLATE_DIR,)) -> Optional[str]:
    """The template a system's games get unless another is asked for."""
    chosen = None
    for folder in folders:
        try:
            defaults = json.loads((Path(folder) / DEFAULTS_FILE).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        name = (defaults.get('systems') or {}).get(system) or defaults.get('default')
        if name in templates:
            chosen = name
    return chosen or ('classic' if 'classic' in templates else next(iter(templates), None))


# --- Which media a game's Mix is made from ---

def candidates(template: Dict, available: Dict[str, str], options: Optional[Dict] = None) -> Dict[str, List[Tuple[str, str]]]:
    """{role: [(media folder, path), ...]} in the order they'd be tried, from
    the media a game has ({folder: path}). Options: box, media, wheel (False
    leaves it out), box_type ('2d' or '3d' first), screenshot ('title' first)."""
    options = options or {}
    first = {'box': {'2d': 'box2d', '3d': 'box3d'}.get(options.get('box_type')),
             'screenshot': {'title': 'screenshottitle', 'screenshot': 'screenshot'}.get(options.get('screenshot'))}
    found = {}
    for role in ROLES:
        if role not in template['elements'] or options.get(role) is False:
            continue
        folders = list(template['sources'].get(role) or [])
        if first.get(role) in folders:
            folders.sort(key=lambda f: f != first[role])
        have = [(f, available[f]) for f in folders if available.get(f)]
        if have:
            found[role] = have
    return found


def classify(roles: Iterable[str]) -> Tuple[str, Optional[str]]:
    """('full' | 'partial' | 'ineligible', reason it's ineligible)."""
    roles = set(roles)
    if 'screenshot' not in roles:
        return 'ineligible', 'no_screenshot'
    if roles >= set(ROLES):
        return 'full', None
    if roles & {'box', 'wheel'}:
        return 'partial', None
    return 'ineligible', 'screenshot_only' if roles == {'screenshot'} else 'no_box_or_wheel'


# --- Layout: where everything goes, in pixels ---

def element_for(template: Dict, role: str, present: Iterable[str]) -> Dict:
    """A role's element, with the variants that apply to this set of roles."""
    present = set(present)
    element = dict(template['elements'][role])
    for variant in element.pop('variants', None) or []:
        when = variant.get('when') or {}
        if set(when.get('missing') or []) & present or not set(when.get('present') or []) <= present:
            continue
        element.update(variant.get('set') or {})
    return element


def _fit(size: Size, box: Size, cover: bool = False) -> Size:
    """size scaled to fit inside box (or, covering, to fill it), same shape."""
    scale = (max if cover else min)(box[0] / size[0], box[1] / size[1])
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def _anchor_point(element: Dict) -> Tuple[float, float]:
    """Where the element's anchor point goes, as fractions of the canvas."""
    if element.get('pos'):
        return tuple(element['pos'])
    vertical, _, horizontal = (element.get('anchor') or 'top-left').partition('-')
    mx, my = element.get('margin') or (0, 0)
    return ({'left': mx, 'right': 1 - mx}.get(horizontal, 0.5),
            {'top': my, 'bottom': 1 - my}.get(vertical, 0.5))


def compute_layout(template: Dict, sizes: Dict[str, Size], canvas: Optional[Size] = None) -> Dict[str, Dict]:
    """Where each picture goes: {role: {'rect': (x, y, w, h), 'clip': (x, y, w, h)
    or None, 'panel': (x, y, w, h) or None}} for the roles in sizes ({role: the
    picture's (width, height)}). A picture covering its panel is drawn at rect
    and cut off at clip."""
    width, height = canvas or (int(template['canvas']['width']), int(template['canvas']['height']))
    present = [r for r in template.get('layers') or ROLES if r in sizes and r in template['elements']]
    placed = {}
    for role in present:
        element = element_for(template, role, present)
        if 'panel' in element:
            px, py, pw, ph = element['panel']
            panel = (round(px * width), round(py * height), max(1, round(pw * width)), max(1, round(ph * height)))
            cover = (element.get('fit') or template.get('screenshot_fit') or 'contain') == 'cover'
            w, h = _fit(sizes[role], panel[2:], cover)
            rect = (panel[0] + (panel[2] - w) // 2, panel[1] + (panel[3] - h) // 2, w, h)
            placed[role] = {'rect': rect, 'clip': panel if cover else None, 'panel': panel}
            continue
        w, h = _fit(sizes[role], (max(1, round(element['max'][0] * width)), max(1, round(element['max'][1] * height))))
        ax, ay = _anchor_point(element)
        vertical, _, horizontal = (element.get('anchor') or 'top-left').partition('-')
        x = round(ax * width) - {'left': 0, 'right': w}.get(horizontal, w // 2)
        y = round(ay * height) - {'top': 0, 'bottom': h}.get(vertical, h // 2)
        attach = element.get('attach') or {}
        if attach.get('to') in placed:
            target = placed[attach['to']]['rect']
            x = target[0] + target[2] - round((attach.get('overlap') or 0) * width)
        placed[role] = {'rect': (x, y, w, h), 'clip': None, 'panel': None}
    return placed


# --- Drawing ---

def _open(path: Path, trim: bool) -> Image.Image:
    """The picture as RGBA, without its see-through border when trimming."""
    with Image.open(path) as source:
        source.load()
        image = source.convert('RGBA')
    if trim:
        bounds = image.getchannel('A').getbbox()
        if bounds is None:
            raise ValueError("the picture is completely see-through")
        if bounds != (0, 0) + image.size:
            image = image.crop(bounds)
    return image


def scale_image(image: Image.Image, size: Size, scaling: str = 'smooth') -> Image.Image:
    """Sharp: enlarge by the largest whole number of times that fits, pixel for
    pixel, so pixel art stays crisp; the last step to the exact size is smooth."""
    if image.size == size:
        return image
    if scaling == 'sharp':
        times = min(size[0] // image.width, size[1] // image.height)
        if times > 1:
            image = image.resize((image.width * times, image.height * times), Image.NEAREST)
    return image if image.size == size else image.resize(size, Image.LANCZOS)


def _round_corners(image: Image.Image, radius: int) -> Image.Image:
    radius = min(radius, image.width // 2, image.height // 2)
    if radius < 1:
        return image
    # One corner drawn large and scaled down, for a smooth edge
    big = Image.new('L', (radius * 4, radius * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, radius * 8 - 1, radius * 8 - 1), fill=255)
    corner = big.resize((radius, radius), Image.LANCZOS)
    mask = Image.new('L', image.size, 255)
    mask.paste(corner, (0, 0))
    mask.paste(corner.transpose(Image.FLIP_LEFT_RIGHT), (image.width - radius, 0))
    mask.paste(corner.transpose(Image.FLIP_TOP_BOTTOM), (0, image.height - radius))
    mask.paste(corner.transpose(Image.ROTATE_180), (image.width - radius, image.height - radius))
    image.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
    return image


def _draw(canvas: Image.Image, image: Image.Image, x: int, y: int):
    """Composite image onto canvas at (x, y); what falls outside is left off."""
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(image.width, canvas.width - x), min(image.height, canvas.height - y)
    if right > left and bottom > top:
        canvas.alpha_composite(image.crop((left, top, right, bottom)), (x + left, y + top))


def _draw_shadow(canvas: Image.Image, image: Image.Image, x: int, y: int, shadow: Dict):
    opacity = float(shadow.get('opacity') or 0)
    if opacity <= 0:
        return
    blur = max(0, round((shadow.get('blur') or 0) * canvas.width))
    dx, dy = shadow.get('offset') or (0, 0)
    pad = blur * 3
    alpha = Image.new('L', (image.width + pad * 2, image.height + pad * 2), 0)
    alpha.paste(image.getchannel('A'), (pad, pad))
    if blur:
        alpha = alpha.filter(ImageFilter.GaussianBlur(blur))
    dark = Image.new('RGBA', alpha.size, (0, 0, 0, 0))
    dark.putalpha(alpha.point(lambda v: int(v * opacity)))
    _draw(canvas, dark, x + round(dx * canvas.width) - pad, y + round(dy * canvas.height) - pad)


def render_mix(template: Dict, sources: Dict[str, List[Tuple[str, Path]]], canvas: Optional[Size] = None):
    """Draw one Mix. sources: {role: [(media folder, file), ...]}, tried in
    order, so a file that can't be read falls back to the next.
    Returns (the picture, {role: the media folder used}, [what was skipped]).
    Raises MixError when what's readable isn't enough to make one."""
    size = canvas or (int(template['canvas']['width']), int(template['canvas']['height']))
    images, used, warnings = {}, {}, []
    for role in ROLES:
        if role not in template['elements']:
            continue
        for folder, path in sources.get(role) or []:
            try:
                # Trimming is decided before the layout: it doesn't depend on what else is there
                images[role] = _open(Path(path), bool(template['elements'][role].get('trim')))
                used[role] = folder
                break
            except Exception as e:
                warnings.append(f"{folder}: can't be read ({e})")
    tier, reason = classify(images)
    if tier == 'ineligible':
        unreadable = bool(warnings) and classify(sources)[0] != 'ineligible'
        raise MixError('asset_unreadable' if unreadable else reason, '; '.join(warnings))

    layout = compute_layout(template, {role: image.size for role, image in images.items()}, size)
    picture = Image.new('RGBA', size, (0, 0, 0, 0))
    for role in [r for r in template.get('layers') or ROLES if r in layout]:
        element = element_for(template, role, layout)
        x, y, w, h = layout[role]['rect']
        scaling = element.get('scaling') or (template.get('screenshot_scaling') if layout[role]['panel'] else None) or 'smooth'
        image = scale_image(images.pop(role), (w, h), scaling)
        clip = layout[role]['clip']
        if clip:
            image = image.crop((clip[0] - x, clip[1] - y, clip[0] - x + clip[2], clip[1] - y + clip[3]))
            x, y = clip[0], clip[1]
        radius = round((element.get('radius') or 0) * size[0])
        panel = layout[role]['panel']
        if panel and element.get('fill'):
            # The panel's own colour shows around a picture that doesn't fill it
            backing = _round_corners(Image.new('RGBA', panel[2:], tuple(element['fill'])), radius)
            backing.alpha_composite(image, (x - panel[0], y - panel[1]))
            image, x, y = backing, panel[0], panel[1]
        if radius:
            image = _round_corners(image, radius)
        frame = element.get('frame') if panel else None
        if frame:
            # A bezel around the whole panel, like the television a scraped Mix shows the game on
            thick = max(1, round((frame.get('width') or 0) * size[0]))
            outer = (panel[2] + thick * 2, panel[3] + thick * 2)
            corner = round((frame.get('radius') or 0) * size[0])
            bezel = _round_corners(Image.new('RGBA', outer, tuple(frame.get('color') or (0, 0, 0, 255))), corner)
            if frame.get('edge'):
                # A lighter rim, a pixel or two wide, so the bezel reads against a dark background
                rim = max(1, round(size[0] / 480))
                lit = _round_corners(Image.new('RGBA', outer, tuple(frame['edge'])), corner)
                lit.alpha_composite(_round_corners(bezel.crop((rim, rim, outer[0] - rim, outer[1] - rim)), max(0, corner - rim)), (rim, rim))
                bezel = lit
            bezel.alpha_composite(image, (x - panel[0] + thick, y - panel[1] + thick))
            image, x, y = bezel, panel[0] - thick, panel[1] - thick
        if element.get('shadow'):
            _draw_shadow(picture, image, x, y, element['shadow'])
        _draw(picture, image, x, y)
        image.close()
    return picture, used, warnings


def provenance(template: Dict, used: Dict[str, str], assets: Optional[Dict[str, str]] = None) -> Dict:
    """What's recorded about a generated Mix: used is {role: media folder},
    assets {role: the media file}."""
    return {SOURCE_KEY: GENERATED, 'template': template['name'], 'template_version': template.get('version', 1),
            'sources': dict(used), 'assets': dict(assets or {}),
            'generated_at': datetime.now().isoformat(timespec='seconds')}


def save_png(picture: Image.Image, path: Path, record: Dict):
    """Save with the record written into the file as PNG text."""
    info = PngInfo()
    info.add_text('Software', 'RetroManager')
    info.add_text(SOURCE_KEY, record[SOURCE_KEY])
    info.add_text('mix_template', str(record['template']))
    info.add_text('mix_template_version', str(record['template_version']))
    info.add_text('mix_assets', json.dumps(record.get('assets') or record.get('sources') or {}, ensure_ascii=True))
    info.add_text('mix_generated_at', record['generated_at'])
    picture.save(path, 'PNG', pnginfo=info)


def read_provenance(path: Path) -> Optional[Dict]:
    """The record a generated Mix carries in its file, or None for a picture
    RetroManager didn't generate (or can't read)."""
    try:
        with Image.open(path) as image:
            text = dict(getattr(image, 'text', None) or {})
    except Exception:
        return None
    if text.get(SOURCE_KEY) != GENERATED:
        return None
    try:
        assets = json.loads(text.get('mix_assets') or '{}')
    except ValueError:
        assets = {}
    return {SOURCE_KEY: GENERATED, 'template': text.get('mix_template'), 'template_version': text.get('mix_template_version'),
            'assets': assets, 'generated_at': text.get('mix_generated_at')}
