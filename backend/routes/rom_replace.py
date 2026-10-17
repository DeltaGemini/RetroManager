"""
A game's ROM file replaced by an updated one (a fixed dump, a hack's new
version), and the version noted beside it (backend/rom_versions.py).

The new file takes the old one's name, so saves, save states and pictures (all
named after it) keep working; if it's a different kind of file (.zip for .nds)
it keeps the old name with its own extension, and the gamelist follows. The old
file is kept in DATA_PATH/replaced-roms/<date-time>/<system>/ (Tools > Storage).

/api/systems/<system>/rom-version   GET ?rom=: the version noted; PUT {rom, version}: note it
/api/systems/<system>/replace-rom   POST {rom, upload (an /api/uploads id), version?}
"""

import shutil
import time
from pathlib import Path

from flask import jsonify, request

from backend.core import (
    _game_moved_hooks, _request_json, _system_path_or_none, app, DATA_DIR, game_moved, gamelist_mgr, logger, ROMS_BASE,
)
from backend.media_index import strip_dot_slash
from backend.rom_versions import RomVersions
from backend.routes.importing import importer

REPLACED_ROMS = Path(DATA_DIR) / 'replaced-roms'
rom_versions = RomVersions(DATA_DIR)
_game_moved_hooks.append(rom_versions.game_moved)
# A game made of several files: replacing one here would leave the others behind
_SEVERAL_FILES = {'.cue', '.m3u', '.gdi', '.ccd', '.toc', '.mds'}


def _rom(system_name, rom):
    system_path = _system_path_or_none(system_name)
    rom = strip_dot_slash(rom)
    if not system_path or not rom:
        return None, None
    path = (system_path / rom).resolve()
    if not str(path).startswith(str(system_path.resolve()) + '/') or not path.is_file():
        return None, None
    return path, rom


@app.route("/api/systems/<system_name>/rom-version", methods=["GET"])
def get_rom_version(system_name):
    """?rom=: {version, at, history: [{version, file, at}]} (empty when none is noted)."""
    path, rom = _rom(system_name, request.args.get("rom"))
    if not path:
        return jsonify(success=False, error="Unknown system or ROM"), 404
    return jsonify(success=True, **rom_versions.get(f"{system_name}/{rom}"))


@app.route("/api/systems/<system_name>/rom-version", methods=["PUT"])
def set_rom_version(system_name):
    data = _request_json()
    path, rom = _rom(system_name, data.get("rom"))
    if not path:
        return jsonify(success=False, error="Unknown system or ROM"), 404
    rom_versions.set_version(f"{system_name}/{rom}", data.get("version"))
    return jsonify(success=True, **rom_versions.get(f"{system_name}/{rom}"))


@app.route("/api/systems/<system_name>/replace-rom", methods=["POST"])
def replace_rom(system_name):
    data = _request_json()
    path, rom = _rom(system_name, data.get("rom"))
    if not path:
        return jsonify(success=False, error="Unknown system or ROM"), 404
    if path.suffix.lower() in _SEVERAL_FILES:
        return jsonify(success=False, error="This game is several files (a disc and its tracks): replace them in the ROMs folder instead"), 400
    upload = importer.resolve(f"upload:{data.get('upload') or ''}")
    if not upload:
        return jsonify(success=False, error="The new file hasn't finished uploading"), 400
    new_ext = Path(upload['name']).suffix.lower() or path.suffix
    if new_ext in _SEVERAL_FILES:
        return jsonify(success=False, error="That's a disc list: it needs its track files too, so add it on the Add games page"), 400
    # The old name, so its saves, states and pictures still go with it; its own extension if it's another kind of file
    target = path.with_suffix(path.suffix if new_ext == path.suffix.lower() else new_ext)
    new_rom = str(Path(rom).with_suffix(target.suffix)) if target != path else rom
    if target != path and target.exists():
        return jsonify(success=False, error=f"There's already a {target.name} beside it"), 409

    kept = REPLACED_ROMS / time.strftime('%Y%m%d-%H%M%S') / system_name / rom
    try:
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(kept))
    except OSError as e:
        logger.exception("Couldn't set the old ROM aside")
        return jsonify(success=False, error=f"The old file couldn't be set aside, so nothing was changed ({e})"), 500
    try:
        part = target.with_name(f".{target.name}.part")
        shutil.move(str(upload['path']), str(part))
        part.replace(target)
    except OSError as e:
        logger.exception("Couldn't put the new ROM in place")
        try:
            shutil.move(str(kept), str(path))   # the old one back
        except OSError:
            logger.exception("Couldn't put the old ROM back either")
        return jsonify(success=False, error=f"The new file couldn't be put in place; the old one is back ({e})"), 500
    importer.discard_upload(data.get('upload'))

    kept_rel = str(kept.relative_to(DATA_DIR))
    # (before the move below, whose hooks would otherwise carry the old record over first)
    rom_versions.replaced(f"{system_name}/{rom}", f"{system_name}/{new_rom}", kept_rel, data.get("version"))
    if new_rom != rom:
        try:
            gamelist_mgr.relink_paths(system_name, ROMS_BASE, {rom: new_rom})
        except Exception:
            logger.exception("Couldn't point the gamelist at the new file")
        game_moved(system_name, rom, new_rom)
    logger.info(f"Replaced {system_name}/{rom} with {upload['name']} (as {target.name}); the old one is in {kept_rel}")
    return jsonify(success=True, rom=new_rom, kept=kept_rel, **rom_versions.get(f"{system_name}/{new_rom}"))
