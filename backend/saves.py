"""
Find a game's in-game saves and save states.

Layout on the NAS (RetroArch-style names: the ROM file name plus a suffix):
    saves/<system>/<rom>.srm                    shared (not per person)
    savestates/<person>/<system>/<rom>.state3   per person
    savestates/<person>/<system>/<rom>.state.auto(.png)
Emulator-named folders (e.g. mGBA/, Nestopia/) and loose files in a person's
folder are searched too. Anything else in these folders is ignored.

Or, where RetroArch keeps them beside the games (RetroPie's way, and its
"write saves to the content directory"): roms/<system>/<rom>.srm and
roms/<system>/<rom>.state3, the "roms" root, which is everyone's (people's
own saves need the folders above).
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from backend.media_index import title_key

# In-game (battery / memory card) save extensions -> label
SAVE_EXTENSIONS = {
    '.srm': 'In-game save',
    '.sav': 'In-game save',
    '.dsv': 'In-game save',
    '.esv': 'In-game save',
    '.eep': 'In-game save',
    '.fla': 'In-game save',
    '.sra': 'In-game save',
    '.mpk': 'Controller pak',
    '.mcr': 'Memory card',
    '.rtc': 'Real-time clock',
}

# "<base>[.sync-conflict-…](.srm|.state|.state3|.state.auto|.auto)[.png]"
_NAME_RE = re.compile(
    r'^(?P<base>.+?)'
    r'(?P<conflict>\.sync-conflict-[^.]+)?'
    r'(?P<kind>\.state(?P<slot>\d+)?(?P<auto>\.auto)?|\.auto|' + '|'.join(re.escape(e) for e in SAVE_EXTENSIONS) + r')'
    r'(?P<png>\.png)?$',
    re.IGNORECASE,
)

SHARED = 'shared'


def _never_written(path: Path, size: int) -> bool:
    """Whether a battery save is nothing but empty cells: the file an emulator
    makes for a game that was never saved in (played with save states only, say)."""
    if size > 8 * 1024 * 1024:
        return False
    try:
        return not path.read_bytes().strip(b'\x00').strip(b'\xff')
    except OSError:
        return False


def is_save_file(name: str) -> bool:
    """An in-game save, a save state, or a state's screenshot (by file name)."""
    return _NAME_RE.match(name) is not None


def _parse(name: str) -> Optional[dict]:
    m = _NAME_RE.match(name)
    if not m:
        return None
    kind_text = m.group('kind').lower()
    if kind_text.startswith('.state') or kind_text == '.auto':
        if m.group('auto') or kind_text == '.auto':
            kind, label, slot = 'auto', 'Auto save state', None
        else:
            slot = int(m.group('slot')) if m.group('slot') else 0
            kind, label = 'state', f'Save state, slot {slot}'
    else:
        kind, label, slot = 'save', SAVE_EXTENSIONS[kind_text], None
    return {
        'base': m.group('base'),
        'kind': kind,
        'label': label,
        'slot': slot,
        'conflict': bool(m.group('conflict')),
        'is_screenshot': bool(m.group('png')),
    }


class SaveFinder:
    def __init__(self, roots: Dict[str, str], profiles: List[str], system_folders, roms_root=None, beside_roms=None):
        """roots: {'saves': path, 'savestates': path}; profiles: person folder names;
        system_folders: callable returning the set of ROM system folder names.
        roms_root and beside_roms (a callable): the ROM folder, looked in as the
        "roms" root while beside_roms() says saves are kept beside the games."""
        self._roots = {name: Path(path) for name, path in roots.items() if path}
        self.profiles = profiles
        self.system_folders = system_folders
        self.roms_root = Path(roms_root) if roms_root else None
        self.beside_roms = beside_roms or (lambda: False)

    @property
    def roots(self) -> Dict[str, Path]:
        if self.roms_root and self.beside_roms():
            return {**self._roots, 'roms': self.roms_root}
        return self._roots

    def available(self) -> Dict[str, bool]:
        return {name: root.is_dir() for name, root in self.roots.items()}

    def _search_dirs(self, root: Path, owner: Path, system: str, is_person: bool):
        """Folders under one owner (a person, or the shared root) that can hold this system's saves."""
        systems = self.system_folders()
        dirs = [owner / system]
        try:
            for child in owner.iterdir():
                if not child.is_dir() or child.name.startswith('.') or child.name == system:
                    continue
                if child.name in systems:  # another system's folder
                    continue
                if not is_person and (child.name in self.profiles or child.name == 'users'):
                    continue
                dirs.append(child)  # emulator-named folder, e.g. mGBA
        except OSError:
            pass
        if is_person:
            dirs.append(owner)  # loose files in the person's folder
        return dirs

    def find(self, system: str, rom_path: str) -> List[dict]:
        rom_stem = Path(rom_path.replace('\\', '/')).stem
        stem_lower, stem_key = rom_stem.lower(), title_key(rom_stem)
        results = {}

        for root_name, root in self.roots.items():
            if not root.is_dir():
                continue
            owners = [(SHARED, root, False)]
            if root_name != 'roms':
                owners += [(p, root / p, True) for p in self.profiles if (root / p).is_dir()]
            for owner_name, owner_dir, is_person in owners:
                # (beside the games: the folder the game itself is in)
                folders = ([root / system / Path(rom_path.replace('\\', '/')).parent] if root_name == 'roms'
                           else self._search_dirs(root, owner_dir, system, is_person))
                for folder in folders:
                    try:
                        files = [f for f in folder.iterdir() if f.is_file()]
                    except OSError:
                        continue
                    for f in files:
                        info = _parse(f.name)
                        if not info:
                            continue
                        base = info['base']
                        if base.lower() != stem_lower and (not stem_key or title_key(base) != stem_key):
                            continue
                        rel = f.relative_to(root).as_posix()
                        # A state's .png screenshot attaches to the state itself
                        key = (root_name, rel[:-4] if info['is_screenshot'] else rel)
                        entry = results.setdefault(key, {})
                        if info['is_screenshot']:
                            entry['screenshot'] = rel
                            continue
                        stat = f.stat()
                        entry.update({
                            'root': root_name,
                            'profile': owner_name,
                            'path': rel,
                            'file': f.name,
                            'folder': folder.name if folder != owner_dir else '',
                            'kind': info['kind'],
                            'label': info['label'],
                            'slot': info['slot'],
                            'conflict': info['conflict'],
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                            'exact_name': base.lower() == stem_lower,
                            'empty': info['kind'] == 'save' and _never_written(f, stat.st_size),
                        })

        # Drop screenshots whose state file wasn't found
        found = [e for e in results.values() if 'path' in e]
        for e in found:
            e.setdefault('screenshot', None)
        found.sort(key=lambda e: e['modified'], reverse=True)
        return found

    def screenshot_path(self, root_name: str, rel: str) -> Optional[Path]:
        """Resolve a state screenshot for serving; None unless it's a .png inside that root."""
        root = self.roots.get(root_name)
        if not root or not rel.lower().endswith('.png'):
            return None
        path = (root / rel).resolve()
        if not str(path).startswith(str(root.resolve()) + '/') or not path.is_file():
            return None
        return path

    # ------------------------------------------------------------------
    # Whole library: play history, sync conflicts, backups
    # ------------------------------------------------------------------

    def scan_all(self) -> List[dict]:
        """Every save and state file (screenshots attached), with who it belongs to
        and which system folder it's in (None for emulator-named or loose files)."""
        systems = self.system_folders()
        records = {}
        for root_name, root in self.roots.items():
            if not root.is_dir():
                continue
            for f in (self._roms_files(root, systems) if root_name == 'roms' else root.rglob('*')):
                if not f.is_file():
                    continue
                info = _parse(f.name)
                if not info:
                    continue
                rel_parts = f.relative_to(root).parts
                if rel_parts[0] == 'users' or '.stversions' in rel_parts:
                    continue  # Syncthing's archive of old versions isn't live saves
                if rel_parts[0] in self.profiles and root_name != 'roms':
                    profile, inner = rel_parts[0], rel_parts[1:]
                else:
                    profile, inner = SHARED, rel_parts
                folder = inner[0] if len(inner) > 1 else ''
                rel = f.relative_to(root).as_posix()
                key = (root_name, rel[:-4] if info['is_screenshot'] else rel)
                entry = records.setdefault(key, {})
                if info['is_screenshot']:
                    entry['screenshot'] = rel
                    continue
                stat = f.stat()
                entry.update({
                    'root': root_name, 'profile': profile, 'path': rel, 'file': f.name,
                    'folder': folder, 'system': folder if folder in systems else None,
                    'base': info['base'], 'kind': info['kind'], 'label': info['label'],
                    'slot': info['slot'], 'conflict': info['conflict'], 'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'modified': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
        found = [e for e in records.values() if 'path' in e]
        for e in found:
            e.setdefault('screenshot', None)
        return found

    @staticmethod
    def _roms_files(root: Path, systems):
        """The files in the system folders of the ROM folder (not its media/ or
        any hidden folder), for the saves among them."""
        for system in sorted(systems):
            for dirpath, dirnames, filenames in os.walk(root / system):
                dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != 'media']
                for name in filenames:
                    if _NAME_RE.match(name):
                        yield Path(dirpath) / name

    def conflicts(self, records: Optional[List[dict]] = None) -> List[dict]:
        """Files Syncthing kept two versions of: [{id, root, path (the original), versions:
        [the original if present, then each conflict copy], newest first}]."""
        records = records if records is not None else self.scan_all()
        by_path = {(r['root'], r['path']): r for r in records}
        groups = {}
        for r in records:
            if not r['conflict']:
                continue
            original = re.sub(r'\.sync-conflict-[^.]+', '', r['path'], count=1)
            groups.setdefault((r['root'], original), []).append(r)
        result = []
        for (root, original), copies in groups.items():
            versions = list(copies)
            if (root, original) in by_path:
                versions.append(by_path[(root, original)])
            versions.sort(key=lambda v: v['mtime'], reverse=True)
            result.append({'id': f"{root}/{original}", 'root': root, 'path': original,
                           'base': versions[0]['base'], 'profile': versions[0]['profile'],
                           'system': versions[0]['system'], 'folder': versions[0]['folder'],
                           'has_original': (root, original) in by_path, 'versions': versions})
        result.sort(key=lambda g: g['versions'][0]['mtime'], reverse=True)
        return result

    def resolve_path(self, root_name: str, rel: str) -> Optional[Path]:
        """A file inside one of the roots (None if it escapes the root or is missing)."""
        root = self.roots.get(root_name)
        if not root:
            return None
        path = (root / rel).resolve()
        if not str(path).startswith(str(root.resolve()) + '/'):
            return None
        return path
