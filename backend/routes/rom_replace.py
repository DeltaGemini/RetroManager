"""
A game's ROM file replaced by an updated one (a fixed dump, a hack's new
version), and the version noted beside it (backend/rom_versions.py).

The new file takes the old one's name, so saves, save states and pictures (all
named after it) keep working; if it's a different kind of file (.zip for .nds)
it keeps the old name with its own extension, and the gamelist follows. The old
file is kept in DATA_PATH/replaced-roms/<date-time>/<system>/ (Tools > Storage).

/api/systems/<system>/rom-version   GET ?rom=: the version noted; PUT {rom, version}: note it
/api/systems/<system>/replace-rom   POST {rom, upload (an /api/uploads id), version?}
/api/systems/<system>/patch-rom     POST {rom, upload (an IPS, UPS or BPS patch), as: replace | new, name?, version?}
"""

import hashlib
import os
import shutil
import time
import zlib
from pathlib import Path

from flask import jsonify, request

from backend.core import (
    _game_moved_hooks, _invalidate_caches, _request_json, _system_path_or_none, app, DATA_DIR, game_moved, gamelist_mgr, logger, ROMS_BASE,
)
from backend.importer import safe_name
from backend.models import Game
from backend.rom_patch import PatchError, apply_patch
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
    result, status = _swap(system_name, rom, path, Path(upload['path']), new_ext, upload['name'], data.get("version"))
    if result.get('success'):
        importer.discard_upload(data.get('upload'))
    return jsonify(**result), status


def _swap(system_name, rom, path, new_file, new_ext, what, version, patch=None):
    """Put new_file in place of the game's ROM, under its name (its own extension if it's another
    kind of file), the old one kept in replaced-roms/: ({success, rom, kept, version...}, HTTP status)."""
    # The old name, so its saves, states and pictures still go with it
    target = path.with_suffix(path.suffix if new_ext == path.suffix.lower() else new_ext)
    new_rom = str(Path(rom).with_suffix(target.suffix)) if target != path else rom
    if target != path and target.exists():
        return {'success': False, 'error': f"There's already a {target.name} beside it"}, 409

    kept = REPLACED_ROMS / time.strftime('%Y%m%d-%H%M%S') / system_name / rom
    try:
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(kept))
    except OSError as e:
        logger.exception("Couldn't set the old ROM aside")
        return {'success': False, 'error': f"The old file couldn't be set aside, so nothing was changed ({e})"}, 500
    try:
        part = target.with_name(f".{target.name}.part")
        shutil.move(str(new_file), str(part))
        part.replace(target)
    except OSError as e:
        logger.exception("Couldn't put the new ROM in place")
        try:
            shutil.move(str(kept), str(path))   # the old one back
        except OSError:
            logger.exception("Couldn't put the old ROM back either")
        return {'success': False, 'error': f"The new file couldn't be put in place; the old one is back ({e})"}, 500

    kept_rel = str(kept.relative_to(DATA_DIR))
    # (before the move below, whose hooks would otherwise carry the old record over first)
    rom_versions.replaced(f"{system_name}/{rom}", f"{system_name}/{new_rom}", kept_rel, version, patch=patch)
    if new_rom != rom:
        try:
            gamelist_mgr.relink_paths(system_name, ROMS_BASE, {rom: new_rom})
        except Exception:
            logger.exception("Couldn't point the gamelist at the new file")
        game_moved(system_name, rom, new_rom)
    logger.info(f"Replaced {system_name}/{rom} with {what} (as {target.name}); the old one is in {kept_rel}")
    return {'success': True, 'rom': new_rom, 'kept': kept_rel, **rom_versions.get(f"{system_name}/{new_rom}")}, 200


# The largest patch taken (a translation of a big disc can be tens of MB)
PATCH_LIMIT = 256 * 1024 * 1024
# The largest ROM patched (it's read whole)
PATCH_ROM_LIMIT = 512 * 1024 * 1024


@app.route("/api/systems/<system_name>/patch-rom", methods=["POST"])
def patch_rom(system_name):
    """Body: {rom, upload (the patch, an /api/uploads id), as: "replace" | "new", name? (the new
    game's, for "new"), version?}. The patch applied to the game's ROM: in its place (as Replace,
    the old one kept), or as a new game beside it. -> {success, rom, notes, crc32, sha1, ...}"""
    data = _request_json()
    path, rom = _rom(system_name, data.get("rom"))
    if not path:
        return jsonify(success=False, error="Unknown system or ROM"), 404
    if path.suffix.lower() in _SEVERAL_FILES or path.suffix.lower() in ('.zip', '.7z'):
        return jsonify(success=False, error="A patch goes on the ROM itself: this game is a disc list or an archive"), 400
    upload = importer.resolve(f"upload:{data.get('upload') or ''}")
    if not upload:
        return jsonify(success=False, error="The patch hasn't finished uploading"), 400
    if upload['size'] > PATCH_LIMIT or path.stat().st_size > PATCH_ROM_LIMIT:
        return jsonify(success=False, error="Too large to patch here"), 400
    try:
        patched, notes = apply_patch(path.read_bytes(), Path(upload['path']).read_bytes())
    except PatchError as e:
        return jsonify(success=False, error=str(e)), 400
    except OSError as e:
        return jsonify(success=False, error=f"The ROM or the patch couldn't be read ({e})"), 500
    patch_name = upload['name']
    sums = {'crc32': f"{zlib.crc32(patched) & 0xFFFFFFFF:08x}", 'sha1': hashlib.sha1(patched).hexdigest()}
    version = data.get("version")

    if data.get("as") == "new":
        name = safe_name((data.get("name") or Path(patch_name).stem).strip())
        if not name:
            return jsonify(success=False, error="The new game needs a name"), 400
        target = path.with_name(name + path.suffix)
        if target.exists():
            return jsonify(success=False, error=f"There's already a {target.name}: choose another name"), 409
        new_rom = str(Path(rom).with_name(target.name))
        try:
            part = target.with_name(f".{target.name}.part")
            part.write_bytes(patched)
            part.replace(target)
        except OSError as e:
            return jsonify(success=False, error=f"The patched game couldn't be written ({e})"), 500
        importer.discard_upload(data.get('upload'))
        try:
            gamelist_mgr.save_game(system_name, Game(path=f"./{new_rom}", name=name), ROMS_BASE)
        except Exception:
            logger.exception("Couldn't add the patched game to the gamelist")
        rom_versions.set_version(f"{system_name}/{new_rom}", version, patched_from={'rom': rom, 'patch': patch_name})
        _invalidate_caches()
        logger.info(f"Patched {system_name}/{rom} with {patch_name} as a new game, {target.name}")
        return jsonify(success=True, rom=new_rom, notes=notes, **sums, **rom_versions.get(f"{system_name}/{new_rom}"))

    try:
        tmp = REPLACED_ROMS / f".patched-{os.getpid()}-{time.time_ns()}"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(patched)
    except OSError as e:
        return jsonify(success=False, error=f"The patched ROM couldn't be written ({e})"), 500
    result, status = _swap(system_name, rom, path, tmp, path.suffix.lower(), f"itself patched with {patch_name}", version, patch=patch_name)
    if result.get('success'):
        importer.discard_upload(data.get('upload'))
        _invalidate_caches()
    else:
        tmp.unlink(missing_ok=True)
    return jsonify(**result, notes=notes, **sums), status
