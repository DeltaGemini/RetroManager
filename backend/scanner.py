"""
System and ROM scanner
Discovers systems, ROMs, and media assets on the filesystem
"""

import os
import logging
import re
from pathlib import Path
from typing import List, Dict, Set
from lxml import etree

from backend.models import System, Game
from backend.media_index import (
    MediaIndex, relink_score, strip_dot_slash, title_key, xml_media_to_relative,
)
from backend.name_style import style_name
from backend.folder_games import choose_launch_files, folder_game_name, is_folder_game_system
from backend.saves import is_save_file

logger = logging.getLogger(__name__)

# Common ROM file extensions
ROM_EXTENSIONS = {
    '.rar',
    '.nes', '.smc', '.sfc', '.gb', '.gbc', '.gba',
    '.nds', '.3ds', '.n64', '.z64',
    '.iso', '.cue', '.bin',
    '.md', '.smd', '.gen', '.exe',
    '.pce', '.sgx', '.cia',
    '.ws', '.wsc', '.min',
    '.ngp', '.ngc', '.nsp',
    '.gg', '.sms', '.xci',
    '.a26', '.a52', '.a78',
    '.col', '.rom',
    '.chd', '.pbp', '.rvz',
    '.wbfs', '.wad', '.ciso', '.gcm', '.gcz', '.wia',
    '.cci', '.dsi', '.fig', '.swc', '.sgb', '.sg',
    '.vb', '.v64', '.t64', '.d64',
    '.m3u',
}


# A cue sheet line naming a track file: FILE "Game (Track 01).bin" BINARY
_CUE_FILE_RE = re.compile(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE | re.MULTILINE)

# "(Disc 2)", "(Disc 2 of 3)", "(CD2)", "[Disk 1]": one disc of a multi-disc game
DISC_TAG_RE = re.compile(r'\s*[\(\[](?:disc|disk|cd)\s*(\d+)(?:\s*of\s*\d+)?[\)\]]', re.IGNORECASE)
# Files that can be a disc in an .m3u playlist
DISC_EXTENSIONS = {'.cue', '.chd', '.iso', '.ccd', '.mds', '.gdi', '.cdi', '.rvz', '.gcz', '.ciso', '.wbfs', '.img'}
# Regions and revisions preferred when suggesting which duplicate to keep
_PREFERRED_TAG_RE = re.compile(r'\((?:[^)]*\b(?:usa|europe|world|uk|australia)\b[^)]*)\)', re.IGNORECASE)
_UNWANTED_TAG_RE = re.compile(r'[\(\[](?:beta|proto|demo|sample|hack|pirate|bad|b\d*|t\d*|h\d*)[^\)\]]*[\)\]]', re.IGNORECASE)


def restore_truncated_name(name: str, rom_stem: str):
    """A name missing its first one or two characters, restored from the ROM file
    name ("arry Potter (UK)" + file "Harry Potter (UK)" -> "Harry Potter (UK)").
    Tries the file name as is, then without (region)/[version] tags. None if the
    name isn't exactly that kind of cut-off copy."""
    name = (name or '').strip()
    if len(name) < 3:
        return None
    clean_stem = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', rom_stem).strip()
    for full in (rom_stem, clean_stem):
        missing = len(full) - len(name)
        if 1 <= missing <= 2 and full.endswith(name) and full[:missing].strip():
            return full[:missing] + name
    return None


class SystemScanner:
    """Scans filesystem for systems, ROMs, and media"""
    
    def __init__(self, roms_base: str, media_base: str):
        self.roms_base = Path(roms_base)
        self.media_base = Path(media_base)
        
    def discover_systems(self) -> List[System]:
        """Discover all systems by scanning ROM directories"""
        systems = []
        
        if not self.roms_base.exists():
            logger.error(f"ROMs base path does not exist: {self.roms_base}")
            return systems
        
        for item in self.roms_base.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                system = self._scan_system_info(item.name)
                if system:
                    systems.append(system)
        
        return sorted(systems, key=lambda s: s.name)
    
    def _scan_system_info(self, system_name: str) -> System:
        """Get basic info about a system"""
        system_path = self.roms_base / system_name
        gamelist_path = system_path / 'gamelist.xml'
        
        rom_files = self._find_rom_files(system_path)
        game_count = 0
        missing_count = 0
        
        if gamelist_path.exists():
            try:
                tree = etree.parse(str(gamelist_path))
                game_count = len(tree.findall('.//game'))
                
                # Quick check for missing metadata
                rom_paths = {self._normalize_path(f) for f in rom_files}
                metadata_paths = set()
                for game in tree.findall('.//game'):
                    path_elem = game.find('path')
                    if path_elem is not None and path_elem.text:
                        metadata_paths.add(self._normalize_path(path_elem.text))
                
                missing_count = len(rom_paths - metadata_paths)
            except Exception as e:
                logger.error(f"Error reading gamelist for {system_name}: {e}")
        else:
            missing_count = len(rom_files)
        
        return System(
            name=system_name,
            path=str(system_path),
            rom_count=len(rom_files),
            game_count=game_count,
            missing_metadata_count=missing_count,
            has_gamelist=gamelist_path.exists()
        )
    
    def disc_parts(self, system_path: Path) -> Dict[str, str]:
        """Files that are part of a disc rather than games of their own:
        {part path (lowercase, relative): the .cue it belongs to}.

        A .cue's FILE lines name its track files ("… (Track 03).bin"). A .cue
        whose files are all covered by a bigger .cue (a leftover per-track
        sheet) is a part of that bigger one too."""
        refs = {}
        for cue in system_path.rglob('*'):
            if not cue.is_file() or cue.suffix.lower() != '.cue':
                continue
            try:
                if cue.stat().st_size > 256 * 1024:
                    continue
                text = cue.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            cue_rel = cue.relative_to(system_path).as_posix()
            folder = cue.relative_to(system_path).parent
            files = set()
            for m in _CUE_FILE_RE.finditer(text):
                name = (m.group(1) or m.group(2)).replace('\\', '/')
                files.add((folder / name).as_posix().lower())
            refs[cue_rel] = files

        # An .m3u playlist's discs are parts of the playlist
        playlist_parts = {}
        for m3u in system_path.rglob('*.m3u'):
            try:
                lines = m3u.read_text(encoding='utf-8', errors='replace').splitlines()
            except OSError:
                continue
            m3u_rel = m3u.relative_to(system_path).as_posix()
            folder = m3u.relative_to(system_path).parent
            for line in lines:
                line = line.strip().replace('\\', '/')
                if line and not line.startswith('#'):
                    playlist_parts[(folder / line).as_posix().lower()] = m3u_rel

        parts = dict(playlist_parts)
        for cue_rel, files in refs.items():
            covering = [other for other, other_files in refs.items()
                        if other != cue_rel and files and files < other_files]
            if covering:
                parts[cue_rel.lower()] = max(covering, key=lambda c: len(refs[c]))
        for cue_rel, files in refs.items():
            if cue_rel.lower() in parts and cue_rel.lower() not in playlist_parts:
                continue
            for f in files:
                parts.setdefault(f, cue_rel)
        return parts

    def saves_in_roms(self, system_path: Path) -> List[str]:
        """Save files and save states inside a ROM folder. They belong in the top-level
        saves/ and savestates/ folders. PC game folders keep their own saves."""
        if is_folder_game_system(system_path.name) or not system_path.is_dir():
            return []
        return sorted(p.relative_to(system_path).as_posix() for p in system_path.rglob('*')
                      if p.is_file() and not any(part.startswith('.') for part in p.relative_to(system_path).parts)
                      and is_save_file(p.name))

    def multi_disc_sets(self, system_path: Path, parts: Dict[str, str]) -> List[Dict]:
        """Discs of one game ("… (Disc 1).cue", "… (Disc 2).cue") not yet in an .m3u:
        [{m3u: path to create, discs: [paths in disc order]}]."""
        groups: Dict[str, Dict[int, str]] = {}
        for item in system_path.rglob('*'):
            if not item.is_file() or item.suffix.lower() not in DISC_EXTENSIONS:
                continue
            rel = item.relative_to(system_path).as_posix()
            if rel.lower() in parts:
                continue  # a track of a .cue, or already in a playlist
            match = DISC_TAG_RE.search(item.stem)
            if not match:
                continue
            base = (DISC_TAG_RE.sub('', item.stem).strip() or item.stem)
            key = (Path(rel).parent / base).as_posix()
            number = int(match.group(1))
            current = groups.setdefault(key, {}).get(number)
            # One file per disc: prefer the .cue/.chd over its raw image
            if current is None or Path(current).suffix.lower() not in ('.cue', '.chd', '.m3u'):
                groups[key][number] = rel
        sets = []
        for key, discs in sorted(groups.items()):
            if len(discs) < 2:
                continue
            m3u = f"{key}.m3u"
            if (system_path / m3u).exists():
                continue
            sets.append({'m3u': m3u, 'discs': [discs[n] for n in sorted(discs)]})
        return sets

    def _find_rom_files(self, system_path: Path) -> List[str]:
        """Find all ROM files in a system directory, preferring .cue over .bin/.iso for the same base name (prevents duplicate entries for PSX/Playstation). Condense multi-track games (e.g., Track 1, Track 2) into a single entry."""
        rom_files = []
        cue_basenames = set()
        all_files = []
        cue_files = []
        parts = self.disc_parts(system_path)
        for item in system_path.rglob('*'):
            if item.is_file() and item.suffix.lower() in ROM_EXTENSIONS:
                rel_path = item.relative_to(system_path)
                if rel_path.as_posix().lower() in parts:
                    continue  # a track or sub-sheet of a disc listed by its .cue
                all_files.append(rel_path)
                if item.suffix.lower() == '.cue':
                    cue_basenames.add(item.with_suffix('').name.lower())
                    cue_files.append(rel_path)

        # Group .cue files by base name before ' (Track' or similar
        import re
        cue_groups = {}
        for cue in cue_files:
            base = cue.with_suffix('').name
            # Remove ' (Track X)' or ' (Disc X)' or similar
            group_key = re.sub(r'\s*\((track|disc)\s*\d+\)$', '', base, flags=re.IGNORECASE).lower()
            if group_key not in cue_groups:
                cue_groups[group_key] = []
            cue_groups[group_key].append(cue)

        # Only keep the first .cue per group
        condensed_cues = set()
        for group in cue_groups.values():
            if group:
                condensed_cues.add(str(group[0]))

        filtered_files = []
        for rel_path in all_files:
            suffix = rel_path.suffix.lower()
            base = rel_path.with_suffix('').name.lower()
            # If .cue, only include if it's the first in its group
            if suffix == '.cue':
                if str(rel_path) in condensed_cues:
                    filtered_files.append(str(rel_path))
                continue
            # If .cue exists for this base, only include the .cue, skip .bin/.iso for that base
            if suffix in {'.bin', '.img', '.iso'} and base in cue_basenames:
                continue
            # If not .cue, only include if .cue does not exist for this base
            if base not in cue_basenames:
                filtered_files.append(str(rel_path))

        if is_folder_game_system(system_path.name):
            filtered_files = choose_launch_files(filtered_files, self._entry_paths(system_path))
        return filtered_files

    def all_rom_files(self, system_path: Path) -> List[str]:
        """Every ROM-type file, including the extra programs in PC game folders."""
        return [item.relative_to(system_path).as_posix() for item in system_path.rglob('*')
                if item.is_file() and item.suffix.lower() in ROM_EXTENSIONS]

    def _entry_paths(self, system_path: Path) -> List[str]:
        gamelist_path = system_path / 'gamelist.xml'
        if not gamelist_path.exists():
            return []
        try:
            return [self._normalize_path(p) for p in etree.parse(str(gamelist_path)).xpath('//game/path/text()')]
        except Exception:
            return []
    
    def get_games_for_system(self, system_name: str) -> List[Game]:
        """Get all games for a system, including ROMs without a gamelist entry."""
        system_path = self.roms_base / system_name
        gamelist_path = system_path / 'gamelist.xml'
        index = self.media_index(system_name)
        parts = self.disc_parts(system_path) if system_path.is_dir() else {}

        games = []
        games_by_path = {}

        # Find ROMs on disk first to know which .cue files exist
        rom_files = self._find_rom_files(system_path)
        cue_bases = {Path(rf).with_suffix('').name.lower() for rf in rom_files if Path(rf).suffix.lower() == '.cue'}

        if gamelist_path.exists():
            try:
                tree = etree.parse(str(gamelist_path))
                for game_elem in tree.findall('.//game'):
                    game = self._parse_game_element(game_elem, system_name, index)
                    if game and self._normalize_path(game.path).lower() in parts:
                        continue  # entry for a disc track; the .cue's entry is the game
                    if game:
                        # Skip .bin/.iso entries if a .cue exists for the same base
                        p = Path(game.path)
                        if p.suffix.lower() in {'.bin', '.img', '.iso'} and p.with_suffix('').name.lower() in cue_bases:
                            continue
                        games_by_path[self._normalize_path(game.path)] = game
                        games.append(game)
            except Exception as e:
                logger.error(f"Error parsing gamelist for {system_name}: {e}")

        # Add ROMs that have no gamelist entry
        for rom_file in rom_files:
            normalized = self._normalize_path(rom_file)
            if normalized in games_by_path:
                games_by_path[normalized].rom_exists = True
            else:
                game = Game.from_filename(rom_file)
                game.name = folder_game_name(system_name, rom_file) or game.name
                for field_name, media_path in index.discover(Path(rom_file).stem).items():
                    if getattr(game, field_name, None) is None:
                        setattr(game, field_name, media_path)
                games.append(game)

        # Mark gamelist entries whose ROM file is gone
        for game in games:
            if game.has_metadata:
                game.rom_exists = (system_path / self._normalize_path(game.path)).exists()
        return games

    def media_index(self, system_name: str) -> MediaIndex:
        """List a system's media folders once, for matching many games."""
        return MediaIndex(self.media_base, self._resolve_media_system(system_name))
    
    def _parse_game_element(self, game_elem, system_name: str, index: MediaIndex = None) -> Game:
        """Parse a <game> element from XML"""
        path_elem = game_elem.find('path')
        if path_elem is None or not path_elem.text:
            return None
        
        def get_text(tag):
            elem = game_elem.find(tag)
            return elem.text if elem is not None and elem.text else None
        
        def get_float(tag):
            text = get_text(tag)
            try:
                return float(text) if text else None
            except ValueError:
                return None
        
        def get_int(tag):
            text = get_text(tag)
            try:
                return int(text) if text else None
            except ValueError:
                return 0
        
        def get_bool(tag):
            text = get_text(tag)
            return text == 'true' if text else False
        
        def extract_media_info(media_path):
            """Extract system/type/filename from paths like ../../media/Game Boy Advance/images/file.png
            Returns tuple of (system_name, filename) or (None, filename) if can't parse
            """
            if not media_path:
                return None, None
            
            # Normalize path separators
            normalized = media_path.replace('\\', '/')
            
            # Try to match pattern: ...media/SYSTEM/TYPE/FILENAME
            parts = normalized.split('/')
            if len(parts) >= 3:
                # Look for 'media' in the path
                try:
                    media_idx = parts.index('media')
                    if media_idx + 2 < len(parts):
                        system_name = parts[media_idx + 1]
                        filename = parts[-1]
                        # Return in format "system/type/filename" for the URL
                        media_type = parts[media_idx + 2]
                        return f"{system_name}/{media_type}/{filename}", system_name
                except (ValueError, IndexError):
                    pass
            
            # Fallback: can't determine proper format, return None so it will be auto-discovered
            return None, None
        
        path = path_elem.text
        image_path, image_system = extract_media_info(get_text('image'))
        video_path, _ = extract_media_info(get_text('video'))
        marquee_path, _ = extract_media_info(get_text('marquee'))
        thumbnail_path, _ = extract_media_info(get_text('thumbnail'))
        
        # Map XML fields to our standardized media types
        screenshot_path, _ = extract_media_info(get_text('screenshot'))
        screenshottitle_path, _ = extract_media_info(get_text('screenshottitle'))
        wheel_path, _ = extract_media_info(get_text('wheel'))
        manuals_path, _ = extract_media_info(get_text('manuals'))
        videos_path, _ = extract_media_info(get_text('videos'))
        mix_path, _ = extract_media_info(get_text('mix'))
        box2d_path, _ = extract_media_info(get_text('box2d'))  # 'image' in XML = 'box2d' in our model
        box3d_path, _ = extract_media_info(get_text('box3d'))
        fanart_path, _ = extract_media_info(get_text('fanart'))
        images_path, _ = extract_media_info(get_text('images'))
        posters_path, _ = extract_media_info(get_text('posters'))
        
        game = Game(
            path=path,
            name=get_text('name') or Path(path).stem,
            desc=get_text('desc'),
            image=image_path,
            video=video_path,
            marquee=marquee_path,
            thumbnail=thumbnail_path,
            screenshot=screenshot_path,
            screenshottitle=screenshottitle_path,
            wheel=wheel_path,
            manuals=manuals_path,
            videos=videos_path,
            mix=mix_path,
            box2d=box2d_path,
            box3d=box3d_path,
            fanart=fanart_path,
            images=images_path,
            posters=posters_path,
            rating=get_float('rating'),
            releasedate=get_text('releasedate'),
            developer=get_text('developer'),
            publisher=get_text('publisher'),
            genre=get_text('genre'),
            players=get_text('players'),
            favorite=get_bool('favorite'),
            playcount=get_int('playcount'),
            lastplayed=get_text('lastplayed'),
            has_metadata=True
        )
        
        # Debug: log what media fields were found
        media_fields = {
            'image': image_path,
            'screenshot': screenshot_path,
            'screenshottitle': screenshottitle_path,
            'wheel': wheel_path,
            'manuals': manuals_path,
            'videos': videos_path,
            'mix': mix_path,
            'box2d': box2d_path,
            'box3d': box3d_path,
            'fanart': fanart_path,
            'images': images_path,
            'posters': posters_path
        }
        found_fields = {k: v for k, v in media_fields.items() if v}
        if found_fields:
            logger.info(f"Game '{game.name}' media fields: {found_fields}")
        
        # Fill media fields the XML doesn't set from files named after the ROM
        if index is None:
            index = self.media_index(system_name)
        for field_name, media_path in index.discover(Path(self._normalize_path(path)).stem).items():
            if getattr(game, field_name, None) is None:
                setattr(game, field_name, media_path)

        return game
    
    def _resolve_media_system(self, rom_system_name: str) -> str:
        """Resolve the media folder name for a given ROM system name.
        Handles common cases where ROM folders use short names (e.g. `GBA`) while media
        folders use full names (e.g. `Game Boy Advance`). Returns the best matching
        media folder name found under `MEDIA_BASE`, or the original `rom_system_name`
        if none found.
        """
        # Explicit mappings for known cases
        explicit_map = {
            'psx': 'Playstation',
            'ps2': 'Playstation 2',
            'gc': 'Gamecube',
            'snes': 'Super Nintendo',
            'pokemini': 'Pokémon mini',
            'nds': 'Nintendo DS',
            'n64': 'Nintendo 64',
            'nsw': 'Nintendo Switch',
        }
        try:
            key = rom_system_name.lower()
            if key in explicit_map:
                return explicit_map[key]

            if not self.media_base.exists():
                return rom_system_name

            candidates = [p.name for p in self.media_base.iterdir() if p.is_dir()]
            # Exact matches
            if rom_system_name in candidates:
                return rom_system_name

            lower = rom_system_name.lower()
            for c in candidates:
                if c.lower() == lower:
                    return c

            # Normalized compare (remove non-alnum)
            def norm(s):
                return ''.join(ch.lower() for ch in s if ch.isalnum())

            nrom = norm(rom_system_name)
            for c in candidates:
                if norm(c) == nrom:
                    return c

            # Initials match (e.g. 'Game Boy Advance' -> 'gba')
            def initials(s):
                return ''.join(w[0].lower() for w in s.split() if w)

            for c in candidates:
                if initials(c) == lower:
                    return c

            # Substring matching
            for c in candidates:
                if lower in c.lower() or c.lower() in lower:
                    return c

        except Exception:
            pass

        return rom_system_name
    
    def get_game_details(self, system_name: str, rom_path: str) -> Game:
        """Get detailed information for a specific game"""
        games = self.get_games_for_system(system_name)
        normalized = self._normalize_path(rom_path)
        
        for game in games:
            if self._normalize_path(game.path) == normalized:
                return game
        
        return None
    
    def scan_system(self, system_name: str) -> Dict:
        """Compare ROMs, gamelist entries and media, and suggest fixes."""
        system_path = self.roms_base / system_name
        gamelist_path = system_path / 'gamelist.xml'
        index = self.media_index(system_name)
        media_base = self.media_base

        rom_files = self._find_rom_files(system_path)
        rom_by_lower = {r.lower(): r for r in rom_files}
        parts = self.disc_parts(system_path) if system_path.is_dir() else {}

        entries = []  # (path, name, {xml field: text})
        if gamelist_path.exists():
            try:
                tree = etree.parse(str(gamelist_path))
                for game in tree.findall('.//game'):
                    path_text = game.findtext('path')
                    if not path_text:
                        continue
                    fields = {f: game.findtext(f) for f in ('image', 'thumbnail', 'video')}
                    entries.append((self._normalize_path(path_text), (game.findtext('name') or '').strip(), fields))
            except Exception as e:
                logger.error(f"Error scanning {system_name}: {e}")

        # Entries for disc tracks: merged into their .cue's entry, not games of their own
        disc_tracks = [{'path': p, 'name': n, 'disc': parts[p.lower()]} for p, n, _ in entries if p.lower() in parts]
        entries = [e for e in entries if e[0].lower() not in parts]

        entry_lower = {e[0].lower() for e in entries}
        orphans = [e for e in entries
                   if e[0].lower() not in rom_by_lower and not (system_path / e[0]).exists()]
        unmatched = [r for r in rom_files if r.lower() not in entry_lower]

        # Pair entries that lost their ROM with ROMs that have no entry
        candidates = []
        for o_path, o_name, _ in orphans:
            for r in unmatched:
                score = relink_score(o_path, r)
                if score >= 0.85:
                    candidates.append((score, o_path, o_name, r))
        candidates.sort(key=lambda c: c[0], reverse=True)
        relink, used_o, used_r = [], set(), set()
        for score, o_path, o_name, r in candidates:
            if o_path in used_o or r in used_r:
                continue
            used_o.add(o_path)
            used_r.add(r)
            relink.append({'from': o_path, 'to': r, 'name': o_name, 'score': round(score, 2)})

        # Entries whose <image>/<thumbnail>/<video> is empty or points at a missing file
        media_links = []
        for path, name, fields in entries:
            if path.lower() not in rom_by_lower:
                continue
            suggestions = index.suggest_links(Path(path).stem)
            fills = {}
            for xml_field, current in fields.items():
                rel = xml_media_to_relative(current)
                if rel and (media_base / rel).is_file():
                    continue
                if xml_field in suggestions:
                    fills[xml_field] = suggestions[xml_field]
            if fills:
                media_links.append({'path': path, 'name': name, 'fields': fills})

        # Media files no ROM matches and no gamelist entry references
        referenced = set()
        for _, _, fields in entries:
            for value in fields.values():
                rel = xml_media_to_relative(value)
                if rel:
                    referenced.add(rel.lower())
        rom_stems = {Path(r).stem.lower() for r in rom_files}
        rom_titles = {title_key(Path(r).stem) for r in rom_files}
        orphaned_media = []
        for folder, (_, _, names) in index.folders.items():
            for name in names:
                rel = f"{index.media_system}/{folder}/{name}"
                stem = Path(name).stem
                if (stem.lower() in rom_stems or title_key(stem) in rom_titles
                        or rel.lower() in referenced):
                    continue
                orphaned_media.append(rel)

        # Names cut short (Skraper sometimes drops the first letter or two), for
        # entries whose ROM exists and whose file name has the full version
        truncated_names = []
        for path, name, _ in entries:
            if path.lower() not in rom_by_lower:
                continue
            fixed = restore_truncated_name(name, Path(path).stem)
            if fixed:
                truncated_names.append({'path': path, 'name': name, 'fixed': fixed})

        # Names not in house style ("Star Wars - X" -> "Star Wars: X"), styled
        # from the restored name when the first letters were cut off too
        name_style = []
        for path, name, _ in entries:
            if not name:
                continue
            base = restore_truncated_name(name, Path(path).stem) if path.lower() in rom_by_lower else None
            base = base or name.strip()
            styled = style_name(base)
            if styled and styled != name:
                name_style.append({'path': path, 'name': name, 'styled': styled})

        # Several discs of one game that could be one .m3u entry
        multi_disc = []
        entry_by_lower = {e[0].lower(): e for e in entries}
        for disc_set in self.multi_disc_sets(system_path, parts):
            named = [entry_by_lower[d.lower()][1] for d in disc_set['discs'] if d.lower() in entry_by_lower]
            multi_disc.append({**disc_set, 'name': (named[0] if named else Path(disc_set['m3u']).stem)})

        duplicates = self._find_duplicates(system_path, rom_files, entries, index)

        return {
            'system': system_name,
            'media_system': index.media_system,
            'multi_disc': multi_disc,
            'duplicates': duplicates,
            'truncated_names': truncated_names,
            'name_style': name_style,
            'relink': relink,
            'new_roms': [r for r in unmatched if r not in used_r],
            'orphaned_metadata': [{'path': p, 'name': n} for p, n, _ in orphans if p not in used_o],
            'media_links': media_links,
            'orphaned_media': orphaned_media,
            'disc_tracks': disc_tracks,
            'saves_in_roms': self.saves_in_roms(system_path),
        }

    def _find_duplicates(self, system_path: Path, rom_files: List[str], entries, index: MediaIndex) -> List[Dict]:
        """Groups of ROMs that are the same game: the same file name apart from
        (region)/[version] tags, or gamelist entries with the same name. Discs of
        one game ("Disc 1", "Disc 2") and PC game folders aren't duplicates."""
        if is_folder_game_system(system_path.name):
            return []
        entry_by_lower = {e[0].lower(): e for e in entries}
        roms = [r for r in rom_files if not DISC_TAG_RE.search(Path(r).stem)]
        parent = {r: r for r in roms}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        by_key: Dict[str, str] = {}
        for rom in roms:
            keys = [('file', title_key(Path(rom).stem))]
            entry = entry_by_lower.get(rom.lower())
            if entry and entry[1]:
                keys.append(('name', title_key(entry[1])))
            for key in keys:
                if not key[1]:
                    continue
                if key in by_key:
                    parent[find(rom)] = find(by_key[key])
                else:
                    by_key[key] = rom

        groups: Dict[str, List[str]] = {}
        for rom in roms:
            groups.setdefault(find(rom), []).append(rom)

        # Details from the gamelist for comparing copies
        details = {}
        gamelist_path = system_path / 'gamelist.xml'
        if gamelist_path.exists():
            try:
                for game in etree.parse(str(gamelist_path)).findall('.//game'):
                    path = self._normalize_path(game.findtext('path') or '')
                    details[path.lower()] = {
                        'playcount': int(game.findtext('playcount') or 0) if (game.findtext('playcount') or '0').isdigit() else 0,
                        'lastplayed': game.findtext('lastplayed'),
                        'has_desc': bool((game.findtext('desc') or '').strip()),
                    }
            except Exception:
                pass

        result = []
        for members in groups.values():
            if len(members) < 2:
                continue
            copies = []
            for rom in sorted(members):
                entry = entry_by_lower.get(rom.lower())
                info = details.get(rom.lower(), {})
                try:
                    size = (system_path / rom).stat().st_size
                except OSError:
                    size = 0
                media = len(index.discover(Path(rom).stem))
                score = (10 if entry else 0) + (3 if info.get('has_desc') else 0) + media \
                    + min(info.get('playcount', 0), 20) + (2 if _PREFERRED_TAG_RE.search(rom) else 0) \
                    - (8 if _UNWANTED_TAG_RE.search(rom) else 0)
                copies.append({'path': rom, 'name': entry[1] if entry else None, 'size': size,
                               'media': media, 'playcount': info.get('playcount', 0),
                               'lastplayed': info.get('lastplayed'), 'score': score})
            keep = max(copies, key=lambda c: (c['score'], -len(c['path'])))
            result.append({'id': keep['path'], 'name': keep['name'] or Path(keep['path']).stem,
                           'keep': keep['path'], 'copies': copies})
        return sorted(result, key=lambda g: g['name'].lower())

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize a ROM path for comparison ("./a/b.sfc" -> "a/b.sfc")."""
        return strip_dot_slash(path)
