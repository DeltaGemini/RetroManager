"""
The ROM check: a checksum index of the whole library (backend/rom_index.py),
its report, and what it knows about one game.
"""

from pathlib import Path

from flask import jsonify, request

import re

from backend.maintenance import Maintenance
from backend.routes.scraping import scrape_queue
from backend.routes.systems import _rename_media_for_relink, move_rom_aside
from backend.media_index import title_key
from backend.models import Game
from backend.name_style import style_name
from backend.core import (
    _saveable_fields,
    game_moved,
    gamelist_mgr,
    library_state,
    save_finder,
    hasheous,
    settings,
    _game_moved_hooks,
    _hasheous_lookup_raw,
    _ra_identify,
    _request_json,
    _rom_exists,
    _system_path_or_none,
    app,
    DATA_DIR,
    hash_cache,
    logger,
    ra_game_ids,
    ra_scraper,
    ROMS_BASE,
    scanner,
)
from backend.media_index import strip_dot_slash
from backend.retroachievements import RetroAchievementsError
from backend.rom_index import RomIndex
from backend.systems import is_arcade


def _library_roms():
    """Every ROM in the library, for the index."""
    games = []
    for system in scanner.discover_systems():
        try:
            listed = scanner.get_games_for_system(system.name)
        except Exception as e:
            logger.warning(f"ROM check: couldn't list {system.name}: {e}")
            continue
        for game in listed:
            if not game.rom_exists:
                continue
            rom_path = strip_dot_slash(game.path)
            games.append({'system': system.name, 'system_name': system.get_full_name(), 'rom_path': rom_path,
                          'name': game.name, 'file': Path(ROMS_BASE) / system.name / rom_path})
    return games


def _identify_ra_and_remember(system, rom_file, known):
    game = _ra_identify(system, rom_file, known)
    # The achievements routes use this cache, so a game's page needn't look again
    rom_path = rom_file.relative_to(Path(ROMS_BASE) / system).as_posix()
    if ra_scraper.configured:
        ra_game_ids.put(f"{system}/{rom_path}", rom_file, game.get('id') if game else None)
    return game


rom_index = RomIndex(
    state_dir=DATA_DIR,
    list_games=_library_roms,
    # Arcade sets are listed as the .zip itself, other systems as the ROM inside
    hash_file=lambda system, rom_file: hash_cache.hashes(rom_file, unzip=not is_arcade(system)),
    lookup=_hasheous_lookup_raw,
    identify_ra=_identify_ra_and_remember,
)


def _follow_move(system, old_rom_path, new_rom_path):
    new_file = Path(ROMS_BASE) / system / new_rom_path if new_rom_path else None
    rom_index.move(system, old_rom_path, new_rom_path, new_file)
    ra_game_ids.move(f"{system}/{old_rom_path}", f"{system}/{new_rom_path}" if new_rom_path else None, new_file)


_game_moved_hooks.append(_follow_move)


_UNSAFE_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _database_file_name(record, rom_path):
    """The file name the ROM databases' name for this file gives: the name
    (the first, if it lists several), made safe, with the file's own extension."""
    name = (record.get('known_name') or '').split('|')[0].strip()
    name = _UNSAFE_FILE_CHARS.sub('', name).strip(' .')
    return f"{name}{Path(rom_path).suffix}" if name else None


def _rename_saves(system_name, old_rom_path, new_stem):
    """Rename a game's saves and save states (named after its ROM) to follow a
    renamed ROM. Returns (how many were renamed, errors)."""
    old_stem = Path(old_rom_path).stem
    renamed, errors = 0, []
    for record in save_finder.find(system_name, old_rom_path):
        for rel in filter(None, (record.get('path'), record.get('screenshot'))):
            source = save_finder.resolve_path(record['root'], rel)
            # Only files named exactly after the ROM, not ones matched loosely by title
            if not source or not source.name.lower().startswith(old_stem.lower() + '.'):
                continue
            target = source.with_name(new_stem + source.name[len(old_stem):])
            try:
                if target.exists():
                    errors.append(f"{target.name}: a save with the new name already exists")
                    continue
                source.rename(target)
                renamed += 1
            except OSError as e:
                errors.append(f"{source.name}: {e}")
    return renamed, errors


@app.route("/api/rom-index/rename", methods=["POST"])
def rom_index_rename():
    """Body: {items: [{system, rom_path}]}. Renames each ROM file to the name the
    ROM databases give its contents (see the report's `mislabelled`), and with
    it the gamelist entry's path, its media, its saves and save states, and its
    play status and collections. A file is left alone if one with the new name
    already exists."""
    results, backed_up = [], set()
    for item in _request_json().get("items") or []:
        system, rom_path = item.get("system"), strip_dot_slash(item.get("rom_path"))
        result = {'system': system, 'rom_path': rom_path}
        results.append(result)
        system_path = _system_path_or_none(system)
        record = rom_index.get(system, rom_path) if system_path else None
        new_name = _database_file_name(record, rom_path) if record else None
        source = system_path / rom_path if system_path else None
        if not new_name or not source or not source.is_file():
            result['error'] = "Not a file the ROM check has a name for"
            continue
        new_rom_path = (Path(rom_path).parent / new_name).as_posix()
        target = system_path / new_rom_path
        if target.exists():
            result['error'] = f"{new_name} already exists (this file may be a duplicate of it)"
            continue
        try:
            source.rename(target)
            if system not in backed_up and (system_path / 'gamelist.xml').exists():
                gamelist_mgr.backup(system, ROMS_BASE)
                backed_up.add(system)
            gamelist_mgr.relink_paths(system, ROMS_BASE, {rom_path: new_rom_path})
            _, media_errors = _rename_media_for_relink(system, {rom_path: new_rom_path})
            saves, save_errors = _rename_saves(system, rom_path, Path(new_name).stem)
            game_moved(system, rom_path, new_rom_path)
            # An entry that was only ever named after the wrong file name takes the right name too
            game = scanner.get_game_details(system, new_rom_path)
            if game and game.has_metadata and title_key(game.name or '') == title_key(Path(rom_path).stem):
                fields = game.to_dict()
                fields.update(name=style_name(Path(new_name).stem), path=f"./{new_rom_path}")
                gamelist_mgr.update_game(system, new_rom_path, Game.from_dict(_saveable_fields(fields)), ROMS_BASE)
            result.update(new_rom_path=new_rom_path, saves_renamed=saves, errors=media_errors + save_errors)
        except Exception as e:
            logger.exception(f"Couldn't rename {system}/{rom_path}")
            result['error'] = str(e)
    return jsonify(success=True, results=results, renamed=sum(1 for r in results if r.get('new_rom_path')))


@app.route("/api/rom-index/duplicates/resolve", methods=["POST"])
def rom_index_resolve_duplicates():
    """Body: {keep: {system, rom_path}, remove: [{system, rom_path}]}. Moves the
    other copies of a file out of the library, to DATA_PATH/duplicates/<system>/
    (nothing is deleted), removes their gamelist entries, and gives the kept
    copy their play status and collections. Only files the ROM check found to
    have the same contents as the kept one are moved."""
    data = _request_json()
    keep = data.get("keep") or {}
    keep_record = rom_index.get(keep.get("system"), strip_dot_slash(keep.get("rom_path")))
    if not keep_record or not keep_record.get('md5'):
        return jsonify(success=False, error="The ROM check doesn't know the copy to keep"), 400
    keep_key = f"{keep['system']}/{strip_dot_slash(keep['rom_path'])}"
    moved, errors, backed_up = [], [], set()
    for item in data.get("remove") or []:
        system, rom_path = item.get("system"), strip_dot_slash(item.get("rom_path"))
        key = f"{system}/{rom_path}"
        record = rom_index.get(system, rom_path)
        if key == keep_key or not record or record.get('md5') != keep_record['md5'] or not _system_path_or_none(system):
            errors.append(f"{key}: not a copy of the file being kept")
            continue
        try:
            move_rom_aside(system, rom_path)
            if system not in backed_up:
                gamelist_mgr.backup(system, ROMS_BASE)
                backed_up.add(system)
            gamelist_mgr.delete_game(system, rom_path, ROMS_BASE)
            # The kept copy takes over what was set on this one, unless it has its own
            library_state.move_game(key, keep_key if not library_state.for_game(keep_key)['play_status'] else None)
            _follow_move(system, rom_path, None)
            moved.append(key)
        except Exception as e:
            logger.exception(f"Couldn't move the duplicate {key}")
            errors.append(f"{key}: {e}")
    if not moved and not errors:
        return jsonify(success=False, error="Nothing to move"), 400
    return jsonify(success=bool(moved) or not errors, moved=moved, errors=errors, moved_to=str(DATA_DIR / 'duplicates'))


def _nightly():
    if settings.get('rom_check_nightly') != 'off' and hasheous.enabled:
        rom_index.start(False)
    # New games are matched to their series (does nothing without IGDB keys)
    try:
        from backend.routes import series
        series.start_matching()
    except Exception:
        logger.exception("Couldn't start the night's series matching")
    # Mix previews nobody committed
    try:
        from backend.routes import mix
        mix.mix_jobs.cleanup()
    except Exception:
        logger.exception("Couldn't clear old Mix previews")


maintenance = Maintenance(DATA_DIR, _nightly)


def start_background_work():
    """Called once the app is set up: start the nightly housekeeping, and pick up
    a ROM check or background scrape that a restart cut short."""
    maintenance.start()
    try:
        if rom_index.resume_if_interrupted():
            logger.info("Resumed the ROM check a restart interrupted")
        if scrape_queue.resume_if_interrupted():
            logger.info("Resumed the background scrape a restart interrupted")
        # Have the Console page's lists ready before anyone asks for them
        from backend.routes import console
        console.refresh_in_background()
        from backend.routes import series
        if series.resume_if_interrupted():
            logger.info("Resumed the series matching a restart interrupted")
    except Exception:
        logger.exception("Couldn't resume interrupted work")


@app.route("/api/data-backups", methods=["GET"])
def list_data_backups():
    """Backups of RetroManager's own data, newest first."""
    return jsonify(success=True, backups=maintenance.list_backups(), folder=str(maintenance.backup_dir))


@app.route("/api/data-backups", methods=["POST"])
def make_data_backup():
    try:
        name = maintenance.backup_data()
    except OSError as e:
        logger.exception("Couldn't back up the data folder")
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True, name=name, backups=maintenance.list_backups())


@app.route("/api/rom-index", methods=["GET"])
def rom_index_status():
    """Progress of the ROM check, and what it has found so far (?report=0 leaves the report out)."""
    result = dict(success=True, **rom_index.snapshot())
    if request.args.get("report") != "0":
        systems = {s.name: s.get_full_name() for s in scanner.discover_systems()}
        result['report'] = rom_index.report(systems)
    return jsonify(**result)


@app.route("/api/rom-index/start", methods=["POST"])
def rom_index_start():
    """Body: {recheck?: bool}. Checks every ROM that's new or changed (or all of them)."""
    result = rom_index.start(bool(_request_json().get("recheck")))
    return jsonify(**result), 200 if result.get('success') else 409


@app.route("/api/rom-index/stop", methods=["POST"])
def rom_index_stop():
    rom_index.stop()
    return jsonify(success=True)


@app.route("/api/systems/<system_name>/rom-info", methods=["GET"])
def rom_info(system_name):
    """?rom=<path>. What the ROM check knows about one game's file: checksums,
    which databases list it, and the name they give it. `checked` is false if
    the file hasn't been looked at yet."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    record = rom_index.get(system_name, strip_dot_slash(request.args.get("rom", "")))
    if not record:
        return jsonify(success=True, checked=False)
    return jsonify(success=True, checked=True, **{k: v for k, v in record.items() if k != 'stamp'})


@app.route("/api/systems/<system_name>/rom-files", methods=["GET"])
def rom_files(system_name):
    """?rom=<path>[&hash=1]. The files a game is made of (a disc game: its .cue
    and every track), each with its size and the checksums already worked out.
    hash=1 works out the missing ones first, which reads each file whole (slow
    for a disc): [{name, size, sha1, md5, crc32}]."""
    from backend.routes.play import _disc_files
    system_path = _system_path_or_none(system_name)
    rom_path = strip_dot_slash(request.args.get("rom", ""))
    if not system_path or not rom_path or not _rom_exists(system_path, rom_path):
        return jsonify(success=False, error="Unknown game"), 404
    rom_file = system_path / rom_path
    files = _disc_files(system_name, rom_path) if rom_file.suffix.lower() == '.cue' else ([rom_file] if rom_file.is_file() else [])
    work_out = request.args.get("hash") == "1"
    result = []
    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            continue
        # As the file is on disk (a .zip isn't opened), which is what you'd compare it with
        hashes = hash_cache.hashes(f, unzip=False, cached_only=not work_out) or {}
        result.append({'name': f.name, 'size': size, **{k: hashes.get(k) for k in ('sha1', 'md5', 'crc32')}})
    return jsonify(success=True, files=result, is_folder=rom_file.is_dir())


@app.route("/api/systems/<system_name>/achievement-badges", methods=["GET"])
def achievement_badges(system_name):
    """{rom_path: {game_id, total, earned, completion}} for the system's games
    that have RetroAchievements, going by the ROM check. `earned` and
    `completion` are the RetroAchievements user's, 0 where nothing is earned."""
    if not _system_path_or_none(system_name) or not ra_scraper.configured:
        return jsonify(success=True, badges={})
    try:
        console = ra_scraper.console_games(system_name)
        progress = {g['game_id']: g for g in ra_scraper.get_user_progress()} if ra_scraper.user else {}
    except RetroAchievementsError as e:
        return jsonify(success=False, error=str(e), badges={})
    badges = {}
    prefix = f"{system_name}/"
    for key, record in rom_index.records().items():
        game_id = record.get('ra_id')
        if not key.startswith(prefix) or not game_id:
            continue
        earned = progress.get(game_id)
        total = (earned or {}).get('total') or (console.get(game_id) or {}).get('achievements') or 0
        if not total:
            continue
        badges[key[len(prefix):]] = {'game_id': game_id, 'total': total, 'earned': (earned or {}).get('earned', 0),
                                     'completion': (earned or {}).get('completion', 0.0)}
    return jsonify(success=True, badges=badges)
