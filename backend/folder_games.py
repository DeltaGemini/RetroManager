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

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional

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
