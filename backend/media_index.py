"""
Shared helpers for matching ROMs to media files and gamelist paths.
"""

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Optional, Tuple

MEDIA_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.avi', '.mkv', '.webm', '.pdf'}

# Media folder -> Game field, for folders the app understands
MEDIA_FOLDER_FIELDS = {
    'wheel': 'wheel',
    'thumbnail': 'thumbnail',
    'thumbnails': 'thumbnail',
    'images': 'images',
    'screenshot': 'screenshot',
    'screenshottitle': 'screenshottitle',
    'manuals': 'manuals',
    'videos': 'videos',
    'mix': 'mix',
    'box2d': 'box2d',
    'box3d': 'box3d',
    'fanart': 'fanart',
    'posters': 'posters',
    'boxside': 'boxside',
}

# Which media folders fill the gamelist's <image>, <thumbnail> and <video>,
# in order of preference. Matches how the existing library was scraped.
LINK_PREFERENCES = {
    'image': ['images', 'mix', 'box2d', 'screenshot'],
    'thumbnail': ['screenshottitle', 'screenshot', 'box2d', 'wheel'],
    'video': ['videos'],
}

# Folder that "move orphaned media" uses; never scanned for matches
ORPHANED_FOLDER = '_orphaned'

# gamelist.xml media paths look like "../../media/<media system>/<folder>/<file>".
# EmulationStation reads them relative to the system's ROM folder, so from
# roms/<system>/ this is the media folder beside roms (RetroGames/media on the
# NAS, ~/RetroPie/media on the Pi). Reading also accepts the old "../media/...".
XML_MEDIA_PREFIX = '../../media'

_TAG_RE = re.compile(r'\s*[\(\[][^\)\]]*[\)\]]')
_DIGITS_RE = re.compile(r'\d+')


def strip_dot_slash(path: Optional[str]) -> str:
    """Remove a leading "./" prefix (not every leading dot, as lstrip('./') does)."""
    p = (path or '').replace('\\', '/').strip()
    while p.startswith('./'):
        p = p[2:]
    return p


def title_key(stem: str) -> str:
    """Name without (tags)/[tags], lowercased letters and digits only.
    "3D Classics Excitebike (CTR-N-SAEP) (E) (v1.1.0)" -> "3dclassicsexcitebike"."""
    return ''.join(ch for ch in _TAG_RE.sub('', stem or '').lower() if ch.isalnum())


def xml_media_to_relative(xml_path: Optional[str]) -> Optional[str]:
    """"../../media/Sys/type/file.png" -> "Sys/type/file.png"; None if the path has no media/ segment."""
    if not xml_path:
        return None
    parts = xml_path.replace('\\', '/').split('/')
    if 'media' not in parts:
        return None
    rel = parts[parts.index('media') + 1:]
    return '/'.join(rel) if len(rel) >= 3 else None


def relink_score(orphan_path: str, rom_path: str) -> float:
    """How likely a gamelist path with no ROM refers to this unmatched ROM (0-1)."""
    o, r = Path(orphan_path), Path(rom_path)
    if o.suffix.lower() != r.suffix.lower() or str(o.parent).lower() != str(r.parent).lower():
        return 0.0
    so, sr = o.stem.lower(), r.stem.lower()
    if so == sr:
        return 1.0
    # Skraper sometimes drops the first character or two of the file name
    if sr.endswith(so) and 0 < len(sr) - len(so) <= 2:
        return 0.99
    # Otherwise require the same numbers, so "Part 1" never matches "Part 2"
    if _DIGITS_RE.findall(so) != _DIGITS_RE.findall(sr):
        return 0.0
    matcher = SequenceMatcher(None, so, sr)
    if matcher.quick_ratio() < 0.85:
        return 0.0
    # Kept below the exact and truncation scores above
    return min(matcher.ratio(), 0.95)


class MediaIndex:
    """One listing of a system's media folders, for fast repeated lookups."""

    def __init__(self, media_base: Path, media_system: str):
        self.media_system = media_system
        # folder -> (stem.lower() -> file name, title_key -> file name, all file names)
        self.folders: Dict[str, Tuple[Dict[str, str], Dict[str, str], list]] = {}
        root = media_base / media_system
        if not root.is_dir():
            return
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or folder.name == ORPHANED_FOLDER:
                continue
            by_stem, by_title, names = {}, {}, []
            try:
                files = sorted(folder.iterdir())
            except OSError:
                continue
            for f in files:
                if not f.is_file() or f.name.startswith('.') or f.suffix.lower() not in MEDIA_EXTENSIONS:
                    continue
                names.append(f.name)
                by_stem.setdefault(f.stem.lower(), f.name)
                key = title_key(f.stem)
                if key:
                    by_title.setdefault(key, f.name)
            self.folders[folder.name] = (by_stem, by_title, names)

    def find(self, folder: str, rom_stem: str, exact: bool = False) -> Optional[str]:
        """Media-relative path ("Sys/folder/file") for a ROM, or None.
        Matches the ROM file name, then (unless exact) the same title ignoring
        region/version tags."""
        entry = self.folders.get(folder)
        if not entry:
            return None
        by_stem, by_title, _ = entry
        name = by_stem.get(rom_stem.lower())
        if not name and not exact:
            key = title_key(rom_stem)
            name = by_title.get(key) if key else None
        return f"{self.media_system}/{folder}/{name}" if name else None

    def discover(self, rom_stem: str, exact: bool = False) -> Dict[str, str]:
        """{Game field: media-relative path} for every known folder with a match.
        Use exact=True before deleting, so files shared by another region's ROM are kept."""
        found = {}
        for folder, field_name in MEDIA_FOLDER_FIELDS.items():
            if field_name in found:
                continue
            path = self.find(folder, rom_stem, exact)
            if path:
                found[field_name] = path
        return found

    def suggest_links(self, rom_stem: str) -> Dict[str, str]:
        """{"image"/"thumbnail"/"video": media-relative path} using LINK_PREFERENCES."""
        links = {}
        for xml_field, folders in LINK_PREFERENCES.items():
            for folder in folders:
                path = self.find(folder, rom_stem)
                if path:
                    links[xml_field] = path
                    break
        return links
