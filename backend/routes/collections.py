"""
Play status, favourites and collections (backend/library_state.py).
"""

from flask import jsonify

from backend.core import (
    _request_json,
    _rom_exists,
    _system_path_or_none,
    app,
    gamelist_mgr,
    library_state,
    logger,
    ROMS_BASE,
    scanner,
    settings,
)
from backend.library_state import STATUSES
from backend.media_index import strip_dot_slash
from backend.models import Game
from backend.routes.accounts import person


def _game_key(data):
    """"system/rom path" for the game a request names, or None if it isn't one."""
    system_path = _system_path_or_none(data.get("system"))
    rom_path = strip_dot_slash(data.get("rom_path"))
    if not system_path or not rom_path or not _rom_exists(system_path, rom_path):
        return None
    return f"{data['system']}/{rom_path}"


def _export():
    library_state.export(settings.get('es_roms_path'))


@app.route("/api/library-state", methods=["GET"])
def get_library_state():
    """Every game's play status, and the collections: {status: {"system/rom": key},
    collections: [{id, name, games}], statuses: [[key, label]]}."""
    return jsonify(success=True, statuses=STATUSES, **library_state.snapshot(person()))


@app.route("/api/play-status", methods=["PUT"])
def set_play_status():
    """Body: {system, rom_path, status}. status is "playing", "backlog",
    "finished", or null to clear it."""
    data = _request_json()
    key = _game_key(data)
    if not key:
        return jsonify(success=False, error="Unknown game"), 404
    try:
        library_state.set_status(key, data.get("status") or None, person())
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    _export()
    return jsonify(success=True, **library_state.for_game(key, person()))


@app.route("/api/favorite", methods=["PUT"])
def set_favorite():
    """Body: {system, rom_path, favorite}. Sets the gamelist's <favorite>, which
    EmulationStation shows; a game without an entry gets one."""
    data = _request_json()
    key = _game_key(data)
    if not key:
        return jsonify(success=False, error="Unknown game"), 404
    system, rom_path = data["system"], strip_dot_slash(data["rom_path"])
    try:
        game = scanner.get_game_details(system, rom_path)
        if game is None:
            return jsonify(success=False, error="Unknown game"), 404
        had_entry = game.has_metadata
        fields = game.to_dict()
        fields['favorite'] = bool(data.get("favorite"))
        fields['path'] = f"./{rom_path}"
        entry = Game.from_dict(fields)
        ok = gamelist_mgr.update_game(system, rom_path, entry, ROMS_BASE) if had_entry else gamelist_mgr.save_game(system, entry, ROMS_BASE)
    except Exception as e:
        logger.exception("Error setting favourite")
        return jsonify(success=False, error=str(e)), 500
    if not ok:
        return jsonify(success=False, error="Couldn't write gamelist.xml"), 500
    return jsonify(success=True, favorite=fields['favorite'])


@app.route("/api/collections", methods=["GET"])
def list_collections():
    """The collections with their games described, for the Collections panel:
    [{id, name, games: [{system, full_name, rom_path, name, box2d, missing}]}].
    `missing` marks a game whose ROM file is no longer there under that name."""
    snapshot = library_state.snapshot()
    wanted = {key.partition('/')[0] for c in snapshot['collections'] for key in c['games']}
    known = {}
    for system in scanner.discover_systems():
        if system.name not in wanted:
            continue
        try:
            for game in scanner.get_games_for_system(system.name):
                known[f"{system.name}/{strip_dot_slash(game.path)}"] = {
                    'system': system.name, 'full_name': system.get_full_name(), 'rom_path': strip_dot_slash(game.path),
                    'name': game.name, 'box2d': game.box2d, 'missing': not game.rom_exists}
        except Exception as e:
            logger.warning(f"Collections: couldn't list {system.name}: {e}")
    collections = []
    for collection in snapshot['collections']:
        games = []
        for key in collection['games']:
            system, _, rom_path = key.partition('/')
            games.append(known.get(key) or {'system': system, 'full_name': system, 'rom_path': rom_path,
                                             'name': rom_path, 'box2d': None, 'missing': True})
        games.sort(key=lambda g: (g['name'] or '').lower())
        collections.append({'id': collection['id'], 'name': collection['name'], 'games': games})
    return jsonify(success=True, collections=collections)


@app.route("/api/collections", methods=["POST"])
def create_collection():
    """Body: {name}."""
    try:
        collection = library_state.create_collection(_request_json().get("name"))
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, collection=collection)


@app.route("/api/collections/<collection_id>", methods=["PUT"])
def rename_collection(collection_id):
    """Body: {name}."""
    try:
        library_state.rename_collection(collection_id, _request_json().get("name"))
    except KeyError:
        return jsonify(success=False, error="Unknown collection"), 404
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    _export()
    return jsonify(success=True)


@app.route("/api/collections/<collection_id>", methods=["DELETE"])
def delete_collection(collection_id):
    try:
        library_state.delete_collection(collection_id)
    except KeyError:
        return jsonify(success=False, error="Unknown collection"), 404
    _export()
    return jsonify(success=True)


@app.route("/api/collections/<collection_id>/games", methods=["PUT"])
def set_collection_game(collection_id):
    """Body: {system, rom_path, member}, or {games: [{system, rom_path}], member}
    for several at once. Adds the games to the collection or takes them out.
    Taking out works for a game whose file has gone, too."""
    data = _request_json()
    member = bool(data.get("member"))
    several = isinstance(data.get("games"), list)
    keys = []
    for game in (data["games"] if several else [data]):
        key = _game_key(game) if isinstance(game, dict) else None
        if not key and not member and isinstance(game, dict) and game.get("system") and game.get("rom_path"):
            key = f"{game['system']}/{strip_dot_slash(game['rom_path'])}"
        if key:
            keys.append(key)
    if not keys:
        return jsonify(success=False, error="Unknown game"), 404
    try:
        changed = library_state.set_membership(collection_id, keys, member)
    except KeyError:
        return jsonify(success=False, error="Unknown collection"), 404
    _export()
    if several:
        return jsonify(success=True, changed=changed)
    return jsonify(success=True, **library_state.for_game(keys[0], person()))
