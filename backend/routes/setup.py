"""
The first time RetroManager is opened: a few steps (/setup) that show where
the library is and whether it can be written to, and where RetroArch keeps its
saves (in folders of their own, or beside the games), and ask for a ScreenScraper
account, with how to get one, or to go on without. Nothing has to be put in a
file first: docker-compose.yml has a place for everything unless told otherwise.

It's wanted until it has been gone through (or skipped) once, on a copy that
looks new: no ScreenScraper credentials, no profiles and no login. An
installation from before there was one is never asked.
"""

import json
import os
import time
from pathlib import Path

from flask import jsonify

from backend.core import (
    app,
    BIOS_BASE,
    DATA_DIR,
    INBOX_BASE,
    logger,
    MEDIA_BASE,
    ROMS_BASE,
    SAVE_BACKUP_BASE,
    SAVE_PROFILES,
    SAVES_BASE,
    SAVESTATES_BASE,
    save_finder,
    scraper,
    settings,
)
from backend.saves import is_save_file
from backend.routes.accounts import accounts, is_admin

DONE = Path(DATA_DIR) / 'setup.json'
# (key, what it's called, where it is, whether RetroManager writes there)
FOLDERS = [
    ('roms', 'Games', ROMS_BASE, True, 'a folder per system (snes, gba, psx...), with each system\'s games inside'),
    ('media', 'Pictures and videos', MEDIA_BASE, True, 'box art, screenshots and the rest, fetched for your games'),
    ('saves', 'Saves', SAVES_BASE, True, 'in-game saves, shared with RetroArch'),
    ('savestates', 'Save states', SAVESTATES_BASE, True, 'RetroArch\'s save states'),
    ('bios', 'BIOS files', BIOS_BASE, False, 'for the systems that need one to play in the browser or on a phone'),
    ('inbox', 'New games', INBOX_BASE, True, 'files dropped here are added from the Add games page'),
    ('data', 'RetroManager\'s own files', DATA_DIR, True, 'settings, backups and what it remembers'),
    ('save-backups', 'Save backups', SAVE_BACKUP_BASE, True, 'copies of saves it replaces'),
]


def needed():
    """Whether the first-run steps are still to be gone through here."""
    return not DONE.is_file() and not scraper.configured and not accounts.enabled and not SAVE_PROFILES


def _folder(key, label, path, written, holds):
    path = Path(path)
    there = path.is_dir()
    return {'key': key, 'label': label, 'holds': holds, 'path': str(path), 'exists': there,
            'writable': there and os.access(path, os.W_OK), 'written': written}


def _library():
    """{systems, games}: the system folders with anything in them, and a count of their files (top level only: quick)."""
    systems = games = 0
    try:
        for folder in Path(ROMS_BASE).iterdir():
            if not folder.is_dir() or folder.name.startswith('.') or folder.name == 'media':
                continue
            files = sum(1 for f in folder.iterdir() if not f.name.startswith('.') and f.suffix.lower() not in ('.xml', '.txt', '.cfg'))
            if files:
                systems += 1
                games += files
    except OSError:
        pass
    return {'systems': systems, 'games': games}


def _count(files, most=500):
    count = 0
    for _ in files:
        count += 1
        if count >= most:
            break
    return count


def _saves():
    """{location: 'folders' | 'roms', beside_roms, in_folders}: where saves are
    kept (Settings > Saves), and how many save files are found each way
    (counting stops at 500), to suggest which way RetroArch keeps them here."""
    def in_folders():
        for base in (SAVES_BASE, SAVESTATES_BASE):
            for path in Path(base).rglob('*'):
                if path.is_file() and is_save_file(path.name) and '.stversions' not in path.parts:
                    yield path
    try:
        beside = _count(save_finder._roms_files(Path(ROMS_BASE), save_finder.system_folders()))
    except OSError:
        beside = 0
    try:
        separate = _count(in_folders())
    except OSError:
        separate = 0
    return {'location': settings.get('save_location') or 'folders', 'beside_roms': beside, 'in_folders': separate}


@app.route("/api/setup", methods=["GET"])
def setup_state():
    """{needed, folders: [{key, label, holds, path, exists, writable, written}],
    library: {systems, games}, saves: {location, beside_roms, in_folders},
    on_host (where the library is on the machine running it, if
    docker-compose said), screenscraper (whether it's set up)}."""
    return jsonify(success=True, needed=needed(), folders=[_folder(*f) for f in FOLDERS], library=_library(), saves=_saves(),
                   on_host=os.environ.get('LIBRARY_ON_HOST') or None, screenscraper=scraper.configured)


@app.route("/api/setup/done", methods=["POST"])
def setup_done():
    """The steps have been gone through (or skipped): not shown again."""
    if not is_admin():
        return jsonify(success=False, error="Only an admin can do that."), 403
    try:
        DONE.parent.mkdir(parents=True, exist_ok=True)
        DONE.write_text(json.dumps({'done': True, 'at': int(time.time())}))
    except OSError as e:
        logger.warning(f"Couldn't note that setup is done: {e}")
        return jsonify(success=False, error=f"RetroManager can't write to its own folder ({DONE.parent}): {e}"), 500
    return jsonify(success=True)
