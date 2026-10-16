"""
A system's tile drawn from its monochrome logo (frontend/logos/<folder>.svg,
fetched by tools/fetch_system_logos.py) in the colours of the theme in use,
which the page passes with the address (common/systems.js). Three looks:

    plain   the theme's panel colour, faint stripes, an accent line; the logo in its text colour
    panels  black with an elbow down the left in the theme's three colours (Starship Panels)
    bridge  a dark screen over a row of lit console buttons (Starship Bridge · 1960s)

The logos are white shapes; a filter fills whatever they draw with the colour wanted.
"""

import re
from html import escape
from pathlib import Path
from typing import Dict, Optional

SIZE = 720
_COLOUR = re.compile(r'^(#[0-9a-fA-F]{3,8}|rgba?\(\s*[\d.]+%?\s*,\s*[\d.]+%?\s*,\s*[\d.]+%?\s*(,\s*[\d.]+\s*)?\))$')
# The colours a tile can be given, and what each is when not given (the Midnight theme's)
DEFAULTS = {'bg': '#1a1f3a', 'bg2': '#0a0e27', 'fg': '#f2f2f7', 'a1': '#ff6b9d', 'a2': '#ff9d3d', 'a3': '#7c6cf0', 'a4': '#6bd09a'}
STYLES = ('plain', 'panels', 'bridge')


def colours(asked: Dict[str, str]) -> Dict[str, str]:
    """The tile's colours: each asked-for one that is a colour, else its default."""
    out = {}
    for key, fallback in DEFAULTS.items():
        value = (asked.get(key) or '').strip()
        out[key] = value if _COLOUR.match(value) else fallback
    return out


def _logo(path: Path):
    """(viewBox, inner markup) of a logo file, or None."""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    root = re.search(r'<svg\b([^>]*)>', text)
    end = text.rfind('</svg>')
    if not root or end < root.end():
        return None
    view = re.search(r'viewBox="([^"]+)"', root.group(1))
    if not view:
        size = re.search(r'width="([\d.]+)[^"]*"[^>]*height="([\d.]+)', root.group(1))
        if not size:
            return None
        view_box = f"0 0 {size.group(1)} {size.group(2)}"
    else:
        view_box = view.group(1)
    return view_box, text[root.end():end]


def _placed(logo, x, y, w, h):
    view_box, inner = logo
    return (f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="{escape(view_box)}" preserveAspectRatio="xMidYMid meet">'
            f'<g filter="url(#rm-tint)">{inner}</g></svg>')


def tile(path: Path, label: str, asked: Dict[str, str], style: str) -> Optional[bytes]:
    """The tile's SVG, or None if the logo can't be read."""
    logo = _logo(path)
    if not logo:
        return None
    c = colours(asked)
    style = style if style in STYLES else 'plain'
    tint = (f'<filter id="rm-tint" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">'
            f'<feFlood flood-color="{c["fg"]}"/><feComposite in2="SourceAlpha" operator="in"/></filter>')
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}" '
            f'role="img" aria-label="{escape(label)}">')
    if style == 'panels':
        # An elbow: a bar along the top curving into one down the left, in three segments
        body = (f'<defs>{tint}</defs><rect width="{SIZE}" height="{SIZE}" fill="#000"/>'
                f'<path d="M0 110 A110 110 0 0 1 110 0 H{SIZE} V44 H150 A46 46 0 0 0 104 90 V330 H0 Z" fill="{c["a1"]}"/>'
                f'<rect x="0" y="342" width="104" height="186" fill="{c["a2"]}"/>'
                f'<rect x="0" y="540" width="104" height="{SIZE - 540}" fill="{c["a3"]}"/>'
                f'<rect x="{SIZE - 150}" y="0" width="10" height="44" fill="#000"/>'
                + _placed(logo, 150, 110, 530, 540))
    elif style == 'bridge':
        # A screen's glow over a row of lit buttons
        buttons = ''.join(
            f'<rect x="{40 + i * 82}" y="618" width="68" height="56" rx="6" fill="{colour}"/>'
            f'<rect x="{46 + i * 82}" y="624" width="56" height="12" rx="4" fill="#fff" fill-opacity="0.28"/>'
            for i, colour in enumerate([c['a1'], c['a2'], c['a3'], c['a4']] * 2))
        body = (f'<defs>{tint}<radialGradient id="rm-glow" cx="0.5" cy="0.38" r="0.7">'
                f'<stop offset="0" stop-color="#1d1d38"/><stop offset="1" stop-color="#060609"/></radialGradient></defs>'
                f'<rect width="{SIZE}" height="{SIZE}" fill="url(#rm-glow)"/>'
                f'<rect x="0" y="596" width="{SIZE}" height="{SIZE - 596}" fill="#0e0e12"/>{buttons}'
                + _placed(logo, 70, 90, 580, 450))
    else:
        body = (f'<defs>{tint}<linearGradient id="rm-bg" x1="0" y1="0" x2="1" y2="1">'
                f'<stop offset="0" stop-color="{c["bg"]}"/><stop offset="1" stop-color="{c["bg2"]}"/></linearGradient>'
                f'<pattern id="rm-lines" width="36" height="36" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                f'<rect width="18" height="36" fill="#fff" fill-opacity="0.03"/></pattern></defs>'
                f'<rect width="{SIZE}" height="{SIZE}" fill="url(#rm-bg)"/><rect width="{SIZE}" height="{SIZE}" fill="url(#rm-lines)"/>'
                f'<rect x="0" y="{SIZE - 16}" width="{SIZE}" height="16" fill="{c["a1"]}"/>'
                + _placed(logo, 80, 150, 560, 400))
    return (head + body + '</svg>').encode('utf-8')
