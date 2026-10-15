"""
Systems, scans and the Scan panel's fixes. Each gamelist change makes a dated backup first.
"""

from flask import jsonify, request
from datetime import datetime
import shutil
from pathlib import Path
from lxml import etree
from backend.scanner import DISC_TAG_RE
from backend.models import Game
from backend.name_style import style_name
from backend.folder_games import folder_game_name, unnamed_ps3_folders
from backend.media_index import ORPHANED_FOLDER, strip_dot_slash
from backend.media_index import title_key
from backend.core import (
    saves_beside_roms,
    game_moved,
    _bulk_result,
    _rom_exists,
    _system_path_or_none,
    app,
    DATA_DIR,
    gamelist_mgr,
    logger,
    MEDIA_BASE,
    ROMS_BASE,
    SAVE_BACKUP_BASE,
    scanner,
)
from backend.routes.saves import _backup_folder_ok

# -----------------------------------------------------------------------------
# API Routes
# -----------------------------------------------------------------------------
@app.route("/api/systems", methods=["GET"])
def get_systems():
    try:
        systems = scanner.discover_systems()
        return jsonify(success=True, systems=[s.to_dict() for s in systems])
    except Exception as e:
        logger.exception("Error discovering systems")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/scan", methods=["POST"])
def scan_system(system_name):
    try:
        result = scanner.scan_system(system_name)
        result['empty_roms'] = _empty_roms(system_name)
        return jsonify(success=True, result=result)
    except Exception as e:
        logger.exception("Error scanning system")
        return jsonify(success=False, error=str(e)), 500


def _empty_roms(system_name):
    """ROM files with nothing in them (0 bytes): a download or copy that failed."""
    system_path = Path(ROMS_BASE) / system_name
    empty = []
    try:
        for game in scanner.get_games_for_system(system_name):
            rom_path = strip_dot_slash(game.path)
            rom_file = system_path / rom_path
            if game.rom_exists and rom_file.is_file() and rom_file.stat().st_size == 0:
                empty.append({'path': rom_path, 'name': game.name})
    except OSError as e:
        logger.warning(f"Couldn't look for empty ROMs in {system_name}: {e}")
    return empty


def move_rom_aside(system_name, rom_path):
    """Move a ROM file out of the library, to DATA_PATH/duplicates/<system>/ (nothing
    is deleted), and note it in moved.log. Returns where it went. Raises OSError."""
    source = Path(ROMS_BASE) / system_name / rom_path
    target = DUPLICATES_DIR / system_name / rom_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(f"{target.stem} ({datetime.now().strftime('%Y%m%d-%H%M%S')}){target.suffix}")
    shutil.move(str(source), str(target))
    try:
        with open(DUPLICATES_DIR / 'moved.log', 'a', encoding='utf-8') as log:
            log.write(f"{datetime.now().isoformat(timespec='seconds')}\t{system_name}\t{rom_path}\n")
    except OSError:
        pass
    return target


@app.route("/api/systems/<system_name>/empty-roms/move", methods=["POST"])
def move_empty_roms(system_name):
    """Body: {paths: [...]}. Moves empty (0-byte) ROM files out of the library, to
    DATA_PATH/duplicates/<system>/, and removes their gamelist entries."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    empty = {e['path'] for e in _empty_roms(system_name)}
    wanted = [strip_dot_slash(p) for p in (request.get_json(silent=True) or {}).get("paths") or []]
    moved, errors, backup = [], [], None
    try:
        for rom_path in wanted:
            if rom_path not in empty:
                continue
            try:
                move_rom_aside(system_name, rom_path)
            except OSError as e:
                errors.append(f"{rom_path}: {e}")
                continue
            if backup is None:
                backup = gamelist_mgr.backup(system_name, ROMS_BASE)
            gamelist_mgr.delete_game(system_name, rom_path, ROMS_BASE)
            game_moved(system_name, rom_path, None)
            moved.append(rom_path)
        if not moved and not errors:
            return jsonify(success=False, error="Nothing to move"), 400
        return jsonify(success=True, changed=len(moved), backup=backup, moved=moved, errors=errors,
                       moved_to=str(DUPLICATES_DIR / system_name))
    except Exception as e:
        logger.exception("Error moving empty ROMs")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/relink", methods=["POST"])
def relink_entries(system_name):
    """Body: {pairs: [{from: old rom path, to: existing rom path}]}"""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    pairs = (request.get_json(silent=True) or {}).get("pairs") or []
    mapping = {p["from"]: p["to"] for p in pairs
               if p.get("from") and p.get("to") and _rom_exists(system_path, p["to"])}
    if not mapping:
        return jsonify(success=False, error="No valid pairs to relink"), 400
    try:
        changed, backup = gamelist_mgr.relink_paths(system_name, ROMS_BASE, mapping)
        renamed, errors = _rename_media_for_relink(system_name, mapping)
        for old, new in mapping.items():
            game_moved(system_name, old, new)
        return jsonify(success=True, changed=changed, backup=backup, renamed_media=renamed, errors=errors)
    except Exception as e:
        logger.exception("Error relinking entries")
        return jsonify(success=False, error=str(e)), 500


def _rename_media_for_relink(system_name, mapping):
    """Media saved under the old (wrong) ROM name is renamed to the new one, so it
    still matches. Files are never overwritten."""
    index = scanner.media_index(system_name)
    system_media = Path(MEDIA_BASE) / index.media_system
    renamed, errors = 0, []
    for old, new in mapping.items():
        old_stem, new_stem = Path(old).stem, Path(new).stem
        for folder, (by_stem, _, _) in index.folders.items():
            name = by_stem.get(old_stem.lower())
            if not name:
                continue
            source = system_media / folder / name
            target = source.with_name(new_stem + source.suffix)
            if target.exists():
                continue
            try:
                source.rename(target)
                renamed += 1
            except OSError as e:
                errors.append(f"{folder}/{name}: {e}")
    return renamed, errors


@app.route("/api/systems/<system_name>/entries/create", methods=["POST"])
def create_entries(system_name):
    """Body: {rom_paths: [...]}. Adds a basic entry (name from the file name,
    media linked from matching files) for each ROM that has none."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    rom_paths = (request.get_json(silent=True) or {}).get("rom_paths") or []
    index = scanner.media_index(system_name)
    games = []
    for rom_path in rom_paths:
        if not _rom_exists(system_path, rom_path):
            continue
        game = Game.from_filename(strip_dot_slash(rom_path))
        game.name = style_name(folder_game_name(system_name, rom_path) or game.name)
        for field, media_path in index.suggest_links(Path(rom_path).stem).items():
            setattr(game, field, media_path)
        games.append(game)
    if not games:
        return jsonify(success=False, error="No valid ROM paths"), 400
    try:
        return _bulk_result(*gamelist_mgr.add_entries(system_name, ROMS_BASE, games))
    except Exception as e:
        logger.exception("Error creating entries")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/entries/remove", methods=["POST"])
def remove_entries(system_name):
    """Body: {paths: [...]}. Removes gamelist entries only; no files are deleted."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    paths = (request.get_json(silent=True) or {}).get("paths") or []
    if not paths:
        return jsonify(success=False, error="No paths given"), 400
    try:
        return _bulk_result(*gamelist_mgr.remove_entries(system_name, ROMS_BASE, paths))
    except Exception as e:
        logger.exception("Error removing entries")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/library-scan", methods=["GET"])
def library_scan():
    """Scan every system and return how many of each problem it has (the same
    checks as each system's Scan panel), for the Library health page."""
    systems = []
    for system in scanner.discover_systems():
        if not system.rom_count and not system.game_count:
            continue
        try:
            result = scanner.scan_system(system.name)
        except Exception as e:
            logger.warning(f"Library scan: {system.name} failed: {e}")
            systems.append({'system': system.name, 'full_name': system.get_full_name(), 'error': str(e), 'counts': {}})
            continue
        result['empty_roms'] = _empty_roms(system.name)
        counts = {k: len(v) for k, v in result.items() if isinstance(v, list)}
        systems.append({
            'system': system.name,
            'full_name': system.get_full_name(),
            'rom_count': system.rom_count,
            'counts': counts,
        })
    return jsonify(success=True, systems=systems)


@app.route("/api/systems/<system_name>/names/fix", methods=["POST"])
def fix_truncated_names(system_name):
    """Body: {paths: [...]} (optional; default all). Puts back the first letters
    Skraper cut off names, taken from each ROM's file name."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("paths")
    try:
        # Recompute on the server rather than trusting names from the client
        names = scanner.scan_system(system_name)["truncated_names"]
        if only is not None:
            wanted = {strip_dot_slash(p).lower() for p in only}
            names = [n for n in names if n["path"].lower() in wanted]
        if not names:
            return _bulk_result(0, None)
        return _bulk_result(*gamelist_mgr.set_names(system_name, ROMS_BASE, {n["path"]: n["fixed"] for n in names}))
    except Exception as e:
        logger.exception("Error fixing names")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/names/style", methods=["POST"])
def style_names(system_name):
    """Body: {paths: [...]} (optional; default all). Renames entries to the house
    style ("Star Wars: Rogue Leader - Rogue Squadron II"); see name_style.py."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("paths")
    try:
        names = scanner.scan_system(system_name)["name_style"]
        if only is not None:
            wanted = {strip_dot_slash(p).lower() for p in only}
            names = [n for n in names if n["path"].lower() in wanted]
        if not names:
            return _bulk_result(0, None)
        return _bulk_result(*gamelist_mgr.set_names(system_name, ROMS_BASE, {n["path"]: n["styled"] for n in names}))
    except Exception as e:
        logger.exception("Error styling names")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/disc-tracks/merge", methods=["POST"])
def merge_disc_tracks(system_name):
    """Body: {paths: [...]} (optional; default all). Folds gamelist entries for disc
    tracks into their .cue's entry. No files are touched."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("paths")
    try:
        # Recompute on the server rather than trusting paths from the client
        tracks = scanner.scan_system(system_name)["disc_tracks"]
        if only is not None:
            wanted = {strip_dot_slash(p).lower() for p in only}
            tracks = [t for t in tracks if t["path"].lower() in wanted]
        if not tracks:
            return _bulk_result(0, None)
        return _bulk_result(*gamelist_mgr.merge_disc_parts(system_name, ROMS_BASE, {t["path"]: t["disc"] for t in tracks}))
    except Exception as e:
        logger.exception("Error merging disc track entries")
        return jsonify(success=False, error=str(e)), 500
DUPLICATES_DIR = DATA_DIR / 'duplicates'


@app.route("/api/systems/<system_name>/duplicates/resolve", methods=["POST"])
def resolve_duplicates(system_name):
    """Body: {groups: [{keep: path, remove: [paths]}]}. Moves the removed copies (and
    a .cue's track files) to DATA_PATH/duplicates/<system>/, folds their
    gamelist details into the kept copy's entry, and gives the kept copy any media
    only the removed one had. Nothing is deleted."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    wanted = (request.get_json(silent=True) or {}).get("groups") or []
    try:
        found = {g['id']: g for g in scanner.scan_system(system_name)['duplicates']}
        members = {}
        for g in found.values():
            for c in g['copies']:
                members[c['path'].lower()] = g['id']
        mapping = {}
        for g in wanted:
            keep = strip_dot_slash(g.get('keep', ''))
            group = members.get(keep.lower())
            for rem in g.get('remove') or []:
                rem = strip_dot_slash(rem)
                if group and rem.lower() != keep.lower() and members.get(rem.lower()) == group:
                    mapping[rem] = keep
        if not mapping:
            return jsonify(success=False, error="Nothing to move"), 400

        changed, backup = gamelist_mgr.merge_disc_parts(system_name, ROMS_BASE, mapping)
        renamed, errors = _rename_media_for_relink(system_name, mapping)
        for removed, kept in mapping.items():
            game_moved(system_name, removed, kept)
        parts = scanner.disc_parts(system_path)
        target_root = DUPLICATES_DIR / system_name
        moved = []
        for rem in mapping:
            files = [rem] + [p for p, owner in parts.items() if owner.lower() == rem.lower()]
            for rel in files:
                source = system_path / rel
                if not source.is_file():
                    # parts are stored lowercase: find the real file name
                    matches = [f for f in source.parent.glob('*') if f.name.lower() == Path(rel).name.lower()]
                    if not matches:
                        continue
                    source = matches[0]
                target = target_root / source.relative_to(system_path)
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
                    moved.append(source.relative_to(system_path).as_posix())
                except OSError as e:
                    errors.append(f"{rel}: {e}")
        try:
            with open(DUPLICATES_DIR / 'moved.log', 'a', encoding='utf-8') as log:
                for rel in moved:
                    log.write(f"{datetime.now().isoformat(timespec='seconds')}\t{system_name}\t{rel}\n")
        except OSError:
            pass
        return jsonify(success=True, changed=len(mapping), backup=backup, moved=moved,
                       renamed_media=renamed, errors=errors,
                       moved_to=str(DUPLICATES_DIR / system_name))
    except Exception as e:
        logger.exception("Error resolving duplicates")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/saves-in-roms/move", methods=["POST"])
def move_saves_out_of_roms(system_name):
    """Body: {paths?: [...]} (default all). Saves and save states belong only in the
    top-level saves/ and savestates/ folders; ones found in a ROM folder move to
    SAVE_BACKUP_PATH/in-rom-folders/<time>/<system>/ (kept, not deleted)."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    if saves_beside_roms():
        return jsonify(success=False, error="Saves are kept beside the games here (Tools > Settings > Saves), so they stay where they are."), 400
    if not _backup_folder_ok():
        return jsonify(success=False, error=f"Can't write to {SAVE_BACKUP_BASE}"), 400
    only = (request.get_json(silent=True) or {}).get("paths")
    found = scanner.saves_in_roms(Path(system_path))
    if only is not None:
        wanted = {strip_dot_slash(p).lower() for p in only}
        found = [f for f in found if f.lower() in wanted]
    target_root = SAVE_BACKUP_BASE / 'in-rom-folders' / datetime.now().strftime('%Y%m%d_%H%M%S') / system_name
    moved, errors = [], []
    for rel in found:
        try:
            target = target_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(Path(system_path) / rel), str(target))
            moved.append(rel)
        except OSError as e:
            errors.append(f"{rel}: {e}")
    return jsonify(success=True, changed=len(moved), moved=moved, errors=errors,
                   moved_to=str(target_root))


@app.route("/api/systems/<system_name>/game-folders/rename", methods=["POST"])
def rename_game_folders(system_name):
    """Body: {paths?: [...]} (default: every finished one). A PS3 disc game is a
    folder, not a file; renamed to "<Game>.ps3" it is one game (see folder_games.py).
    Nothing inside the folder changes. A gamelist entry pointing inside it (the
    game's EBOOT.BIN, listed as "Eboot") becomes the folder's entry."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    system_path = Path(system_path)
    found = unnamed_ps3_folders(system_path)
    only = (request.get_json(silent=True) or {}).get("paths")
    if only is not None:
        wanted = {strip_dot_slash(p).lower() for p in only}
        found = [f for f in found if f['path'].lower() in wanted]
    else:
        found = [f for f in found if f['complete']]
    # Never rename a folder that is still being copied: it would break the copy
    copying = [f['path'] for f in found if f['copying']]
    found = [f for f in found if not f['copying']]
    if not found:
        return jsonify(success=False, error="Still being copied: " + ", ".join(copying) if copying
                       else "No game folders to rename"), 400

    # Entries now in the gamelist, to carry over: {path: name}
    entries = {}
    gamelist_path = system_path / 'gamelist.xml'
    if gamelist_path.exists():
        try:
            for game_elem in etree.parse(str(gamelist_path)).findall('.//game'):
                path = strip_dot_slash(game_elem.findtext('path') or '')
                if path:
                    entries[path] = (game_elem.findtext('name') or '').strip()
        except Exception as e:
            return jsonify(success=False, error=f"Couldn't read gamelist.xml: {e}"), 500

    renamed, errors, relink, names, drop = [], [f"{p}: still being copied, not renamed" for p in copying], {}, {}, []
    for item in found:
        source, target = system_path / item['path'], system_path / item['to']
        if target.exists():
            errors.append(f"{item['to']} already exists")
            continue
        try:
            source.rename(target)
        except OSError as e:
            errors.append(f"{item['path']}: {e}")
            continue
        renamed.append(item['to'])
        inside = sorted(p for p in entries if p.lower().startswith(item['path'].lower() + '/'))
        if inside and item['to'] not in entries:
            relink[inside[0]] = item['to']
            # "Eboot" (named after the file it pointed at) -> the game's own name
            if title_key(entries[inside[0]]) in ('', title_key(Path(inside[0]).stem)):
                names[item['to']] = style_name(Game.from_filename(item['to']).name)
            inside = inside[1:]
        drop += inside
    try:
        backup = None
        if relink:
            backup = gamelist_mgr.relink_paths(system_name, ROMS_BASE, relink)[1]
            for old, new in relink.items():
                game_moved(system_name, old, new)
        if names:
            gamelist_mgr.set_names(system_name, ROMS_BASE, names)
        if drop:
            gamelist_mgr.remove_entries(system_name, ROMS_BASE, drop)
    except Exception as e:
        logger.exception("Error updating the gamelist after renaming game folders")
        errors.append(f"gamelist.xml: {e}")
    return jsonify(success=True, changed=len(renamed), renamed=renamed, errors=errors, backup=backup)


@app.route("/api/systems/<system_name>/multi-disc/create", methods=["POST"])
def create_multi_disc(system_name):
    """Body: {m3us: [paths]} (optional; default all). Writes an .m3u playlist for each
    multi-disc game and makes it the game's one gamelist entry (details from the
    disc entries are kept; disc 1's media is renamed to match)."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("m3us")
    try:
        sets = scanner.scan_system(system_name)['multi_disc']
        if only is not None:
            wanted = {strip_dot_slash(p).lower() for p in only}
            sets = [s for s in sets if s['m3u'].lower() in wanted]
        if not sets:
            return _bulk_result(0, None)
        mapping, names, errors = {}, {}, []
        for disc_set in sets:
            m3u_path = system_path / disc_set['m3u']
            folder = m3u_path.parent
            lines = [(system_path / d).relative_to(folder).as_posix() for d in disc_set['discs']]
            try:
                m3u_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            except OSError as e:
                errors.append(f"{disc_set['m3u']}: {e}")
                continue
            for disc in disc_set['discs']:
                mapping[disc] = disc_set['m3u']
            names[disc_set['m3u']] = DISC_TAG_RE.sub('', disc_set['name']).strip()
        changed, backup = gamelist_mgr.merge_disc_parts(system_name, ROMS_BASE, mapping) if mapping else (0, None)
        # Entries renamed "… (Disc 1)" lose the disc tag; games with no entry get one
        existing = {strip_dot_slash(g.path).lower() for g in scanner.get_games_for_system(system_name) if g.has_metadata}
        new_games, renames = [], {}
        for m3u, name in names.items():
            if m3u.lower() in existing:
                renames[m3u] = name
            else:
                game = Game.from_filename(m3u)
                game.name = style_name(name)
                new_games.append(game)
        if renames:
            gamelist_mgr.set_names(system_name, ROMS_BASE, renames)
        if new_games:
            gamelist_mgr.add_entries(system_name, ROMS_BASE, new_games)
        first_discs = {s['discs'][0]: s['m3u'] for s in sets if s['m3u'] in names}
        renamed, rename_errors = _rename_media_for_relink(system_name, first_discs)
        return jsonify(success=True, changed=len(names), backup=backup, renamed_media=renamed,
                       errors=errors + rename_errors)
    except Exception as e:
        logger.exception("Error creating multi-disc playlists")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/link-media", methods=["POST"])
def link_media(system_name):
    """Body: {paths: [...]} (optional; default all). Fills empty or broken
    <image>/<thumbnail>/<video> from matching media files."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("paths")
    try:
        # Recompute on the server rather than trusting paths from the client
        links = scanner.scan_system(system_name)["media_links"]
        if only is not None:
            wanted = {strip_dot_slash(p) for p in only}
            links = [l for l in links if l["path"] in wanted]
        if not links:
            return _bulk_result(0, None)
        updates = {l["path"]: l["fields"] for l in links}
        return _bulk_result(*gamelist_mgr.set_media_fields(system_name, ROMS_BASE, updates))
    except Exception as e:
        logger.exception("Error linking media")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/orphaned-media/move", methods=["POST"])
def move_orphaned_media(system_name):
    """Body: {files: ["<media system>/<folder>/<file>", ...]}. Moves each file to
    <media system>/_orphaned/<folder>/ so it can be restored by hand."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    files = (request.get_json(silent=True) or {}).get("files") or []
    media_system = scanner._resolve_media_system(system_name)
    system_media = (Path(MEDIA_BASE) / media_system).resolve()
    moved, errors = 0, []
    for rel in files:
        parts = rel.replace('\\', '/').split('/')
        if len(parts) != 3 or parts[0] != media_system or parts[1] in ('', '.', '..', ORPHANED_FOLDER):
            errors.append(f"{rel}: not a media file of this system")
            continue
        source = (system_media / parts[1] / parts[2]).resolve()
        if source.parent.parent != system_media or not source.is_file():
            errors.append(f"{rel}: file not found")
            continue
        target_dir = system_media / ORPHANED_FOLDER / parts[1]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        counter = 1
        while target.exists():
            target = target_dir / f"{source.stem}_{counter}{source.suffix}"
            counter += 1
        try:
            shutil.move(str(source), str(target))
            moved += 1
        except OSError as e:
            errors.append(f"{rel}: {e}")
    return jsonify(success=moved > 0 or not errors, changed=moved, errors=errors)
