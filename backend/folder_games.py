"""
PC-style systems (DOS, Windows, ScummVM) keep each game as an installed folder
full of programs: the game, its setup, an uninstaller, a bundled DOSBox...
For those systems each top-level folder is one game, represented by a single
launch file:

  1. the file an existing gamelist entry points at, if there is one, or
  2. the likeliest game program: .exe/.bat/.com before disc images, named like
     the folder ("STARTREK.EXE" in "Star Trek 25th Anniversary"), and never
     setup, install, uninstall, DOSBox or config tools.

Files directly in the system folder, and folders with no programs in them (a
folder of disc images), stay games of their own.
"""

import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

FOLDER_GAME_SYSTEMS = {'dos', 'pc', 'msdos', 'winxp', 'win', 'windows', 'win3x', 'scummvm'}

# Programs that aren't the game
_NOT_GAME_RE = re.compile(
    r'setup|install|unins|uninst|dosbox|config|cfg|pictview|dos4gw|eregcard|regist|'
    r'readme|patch|update|crack|vcredist|directx|dxsetup|launcher_?config|sound|'
    r'drivers?|debug|support|intro_?view|chkdsk',
    re.IGNORECASE,
)
# Folders whose contents are never the game
_SKIP_DIRS = {'dosbox', '__support', 'redist', 'directx', '_redist', 'commonredist',
              'cloud_saves', 'documentation', 'docs', 'manual', 'extras'}
_PROGRAM_EXTS = {'.exe', '.com', '.bat'}
_EXT_WEIGHT = {'.exe': 3.0, '.com': 3.0, '.bat': 2.5, '.iso': 1.0, '.cue': 1.2, '.chd': 1.0}


# A PS3 disc game is a folder too (PS3_GAME/, PS3_DISC.SFB), but with thousands
# of data files rather than programs to choose from. Named "<Game>.ps3" the
# folder itself is the game: one ROM, never looked inside. That is the name
# Batocera and ES-DE expect, and RPCS3 opens the folder directly.
GAME_FOLDER_SUFFIX = '.ps3'


def is_game_folder(path: Path) -> bool:
    return path.name.lower().endswith(GAME_FOLDER_SUFFIX) and path.is_dir()


def is_unnamed_ps3_folder(path: Path) -> bool:
    """A PS3 game folder that hasn't been given the .ps3 name yet."""
    return not path.name.lower().endswith(GAME_FOLDER_SUFFIX) and (path / 'PS3_GAME').is_dir()


def walk_roms(system_path: Path) -> Iterator[Path]:
    """Every file under a system folder, and each game folder ("X.ps3") as one
    item. Game folders aren't entered, named .ps3 or not, so their data files
    are never taken for ROMs, discs or saves."""
    for root, dirs, files in os.walk(system_path):
        root_path = Path(root)
        enter = []
        for name in dirs:
            path = root_path / name
            if name.lower().endswith(GAME_FOLDER_SUFFIX):
                yield path
            elif not (path / 'PS3_GAME').is_dir():
                enter.append(name)
        dirs[:] = enter
        for name in files:
            yield root_path / name


def _changed_recently(folder: Path, seconds: int = 120) -> bool:
    """Whether anything in the folder was written in the last couple of minutes
    (a copy still running). Uses the change time, which copying can't backdate."""
    cutoff = time.time() - seconds
    try:
        for root, dirs, files in os.walk(folder):
            if os.stat(root).st_ctime > cutoff:
                return True
            for name in files:
                if os.lstat(os.path.join(root, name)).st_ctime > cutoff:
                    return True
    except OSError:
        return True   # files vanishing or unreadable mid-walk: not safe to rename
    return False


def unnamed_ps3_folders(system_path: Path) -> List[Dict]:
    """PS3 game folders to rename: [{path, to, complete, copying}]. `complete`
    is false while the game's PARAM.SFO or EBOOT.BIN is missing; `copying` is
    true while files are still arriving. Renaming mid-copy would break the copy."""
    found = []
    for root, dirs, _ in os.walk(system_path):
        enter = []
        for name in dirs:
            path = Path(root) / name
            if name.lower().endswith(GAME_FOLDER_SUFFIX):
                continue
            if (path / 'PS3_GAME').is_dir():
                rel = path.relative_to(system_path).as_posix()
                found.append({
                    'path': rel,
                    'to': rel + GAME_FOLDER_SUFFIX,
                    'complete': (path / 'PS3_GAME' / 'PARAM.SFO').is_file()
                                and (path / 'PS3_GAME' / 'USRDIR' / 'EBOOT.BIN').is_file(),
                    'copying': _changed_recently(path),
                })
            elif not name.startswith('.'):
                enter.append(name)
        dirs[:] = enter
    return sorted(found, key=lambda f: f['path'].lower())


def is_folder_game_system(system_name: str) -> bool:
    return (system_name or '').lower() in FOLDER_GAME_SYSTEMS


def game_folder(rom_path: str) -> Optional[str]:
    """The top-level folder a launch file belongs to ("Doom/DOOM.EXE" -> "Doom")."""
    path = rom_path.replace('\\', '/')
    parts = Path(path[2:] if path.startswith('./') else path).parts
    return parts[0] if len(parts) > 1 else None


def folder_game_name(system_name: str, rom_path: str) -> Optional[str]:
    """A PC game's name comes from its folder, not "STARTREK.EXE"."""
    if not is_folder_game_system(system_name):
        return None
    folder = game_folder(rom_path)
    return re.sub(r'\s+', ' ', folder.replace('_', ' ')).strip() if folder else None


def _key(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())


def _initials(text: str) -> str:
    return ''.join(w[0] for w in re.findall(r'[a-z0-9]+', text.lower()))


def is_helper_program(rel_path: str) -> bool:
    """Setup, uninstallers, bundled DOSBox and the like."""
    path = Path(rel_path)
    if any(part.lower() in _SKIP_DIRS for part in path.parts[:-1]):
        return True
    return bool(_NOT_GAME_RE.search(path.stem))


def launch_score(rel_path: str, folder: str) -> float:
    """How likely a file is the folder's game. Helpers score below zero."""
    path = Path(rel_path)
    score = _EXT_WEIGHT.get(path.suffix.lower(), 0.5)
    stem, folder_key = _key(path.stem), _key(folder)
    if stem and folder_key:
        if stem in folder_key or folder_key in stem:
            similarity = 1.0
        elif _initials(folder).startswith(stem[:4]) and len(stem) >= 3:
            similarity = 0.9  # STTNG in "Star Trek The Next Generation"
        else:
            similarity = SequenceMatcher(None, stem, folder_key).ratio()
        score += 2 * similarity
    score -= 0.2 * (len(path.parts) - 2)  # shallower first
    if is_helper_program(rel_path):
        score -= 10
    return score


def choose_launch_files(rom_files: Iterable[str], entry_paths: Iterable[str]) -> List[str]:
    """Reduce a PC system's files to one per top-level folder (see module doc)."""
    entries = {p.lower() for p in entry_paths}
    by_folder: Dict[str, List[str]] = {}
    chosen = []
    for rel in rom_files:
        folder = game_folder(rel)
        if folder is None:
            chosen.append(rel)
        else:
            by_folder.setdefault(folder, []).append(rel)
    for folder, files in by_folder.items():
        if not any(Path(f).suffix.lower() in _PROGRAM_EXTS for f in files):
            chosen.extend(files)  # a folder of disc images, not an installed game
            continue
        with_entry = [f for f in files if f.lower() in entries]
        if with_entry:
            chosen.extend(with_entry)  # normally one; keep all the user listed
        else:
            chosen.append(max(files, key=lambda f: launch_score(f, folder)))
    return chosen


def launch_candidates(rom_files: Iterable[str], folder: str) -> List[Dict]:
    """Every possible launch file in a game folder, likeliest first."""
    files = [f for f in rom_files if game_folder(f) == folder]
    ranked = sorted(files, key=lambda f: launch_score(f, folder), reverse=True)
    return [{'path': f, 'helper': is_helper_program(f)} for f in ranked]
