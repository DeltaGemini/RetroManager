"""
Series: the other games in a game's series, which of them you have, and the
ones you want (backend/series_index.py).
"""

import threading
import time

from flask import jsonify, request

from backend.core import (
    _game_moved_hooks,
    _request_json,
    _rom_exists,
    _system_path_or_none,
    app,
    DATA_DIR,
    igdb_scraper,
    logger,
    scanner,
)
from backend.igdb_scraper import IGDBError
from backend.media_index import strip_dot_slash
from backend.routes.accounts import person
from backend.series_index import MARKS, SeriesIndex
from backend.systems import igdb_platform_id

series_index = SeriesIndex(DATA_DIR / 'series.json', igdb_scraper, igdb_platform_id)
_game_moved_hooks.append(lambda system, old, new: series_index.game_moved(f"{system}/{old}", f"{system}/{new}" if new else None))

NOT_SET_UP = "Series come from IGDB. Add its client ID and secret in Tools › Settings."


def _named_game(system_name, rom_path):
    """(key, name) for a game in the library, or (None, None)."""
    system_path = _system_path_or_none(system_name)
    rom_path = strip_dot_slash(rom_path)
    if not system_path or not rom_path or not _rom_exists(system_path, rom_path):
        return None, None
    game = scanner.get_game_details(system_name, rom_path)
    return f"{system_name}/{rom_path}", (game.name if game and game.name else rom_path.rsplit('/', 1)[-1].rsplit('.', 1)[0])


def _library():
    """Every game with a ROM: [{key, system, name}]."""
    games = []
    for system in scanner.discover_systems():
        try:
            for game in scanner.get_games_for_system(system.name):
                if game.rom_exists:
                    games.append({'key': f"{system.name}/{strip_dot_slash(game.path)}", 'system': system.name, 'name': game.name or game.path})
        except Exception as e:
            logger.warning(f"Series: skipping {system.name}: {e}")
    return games


def _with_library_names(view):
    """Each "have" key ("system/rom path") as {system, path, name} for linking to."""
    names = {}
    for game in view['games']:
        have = []
        for key in game['have']:
            system_name, _, path = key.partition('/')
            if key not in names:
                found = scanner.get_game_details(system_name, path)
                names[key] = found.name if found and found.name else path
            have.append({'system': system_name, 'path': path, 'name': names[key]})
        game['have'] = have
    return view


@app.route("/api/series/game", methods=["GET"])
def series_for_game():
    """?system=&rom=. The game's series and everything in it:
    {configured, match: {id, name, how}, series: {key, name, kind, have, total, games: [...]}}.
    series is null for a game IGDB doesn't know or that isn't in one."""
    if not series_index.configured:
        return jsonify(success=True, configured=False)
    key, name = _named_game(request.args.get("system", ""), request.args.get("rom", ""))
    if not key:
        return jsonify(success=False, error="Unknown game"), 404
    try:
        record = series_index.match(key, request.args["system"], name)
        view = series_index.view(record['series'], refresh=request.args.get("refresh") == "1", person=person()) if record.get('series') else None
    except IGDBError as e:
        return jsonify(success=False, error=str(e)), 502
    return jsonify(success=True, configured=True, match={k: record.get(k) for k in ('id', 'name', 'how')},
                   series=_with_library_names(view) if view else None)


@app.route("/api/series/list", methods=["GET"])
def series_list():
    """?key=. One series, as /api/series/game gives it."""
    try:
        view = series_index.view(request.args.get("key", ""), refresh=request.args.get("refresh") == "1", person=person())
    except IGDBError as e:
        return jsonify(success=False, error=str(e)), 502
    if not view:
        return jsonify(success=False, error="Unknown series"), 404
    return jsonify(success=True, series=_with_library_names(view))


@app.route("/api/series/mark", methods=["PUT"])
def series_mark():
    """{id, mark}: mark a game you don't have as "want" or "skip" (not interested); null clears it."""
    data = _request_json()
    mark = data.get("mark")
    if not isinstance(data.get("id"), int) or (mark is not None and mark not in MARKS):
        return jsonify(success=False, error="Needs a game id and a mark of want, skip or null"), 400
    series_index.set_mark(data["id"], mark, person())
    return jsonify(success=True, mark=mark)


@app.route("/api/series/platform", methods=["PUT"])
def series_platform():
    """{series, platform, skip}: hide (or show again) one platform's games within a series."""
    data = _request_json()
    if not data.get("series") or not data.get("platform"):
        return jsonify(success=False, error="Needs a series and a platform"), 400
    series_index.skip_platform(str(data["series"]), str(data["platform"]), bool(data.get("skip")), person())
    return jsonify(success=True)


@app.route("/api/series/candidates", methods=["GET"])
def series_candidates():
    """?system=&rom=&q=. IGDB games this one could be, for matching it by hand."""
    if not series_index.configured:
        return jsonify(success=False, error=NOT_SET_UP), 400
    key, name = _named_game(request.args.get("system", ""), request.args.get("rom", ""))
    if not key:
        return jsonify(success=False, error="Unknown game"), 404
    try:
        results = series_index.search(request.args.get("q") or name, request.args["system"])
    except IGDBError as e:
        return jsonify(success=False, error=str(e)), 502
    return jsonify(success=True, candidates=[{
        'id': r['id'], 'name': r.get('name'),
        'year': time.gmtime(r['first_release_date']).tm_year if r.get('first_release_date') else None,
        'series': ', '.join(g.get('name', '') for g in (r.get('collections') or r.get('franchises') or []) if isinstance(g, dict)) or None,
    } for r in results[:15]])


@app.route("/api/series/match", methods=["PUT"])
def series_match():
    """{system, rom_path, id}: say which IGDB game this one is; a null id has it looked up again."""
    data = _request_json()
    key, _ = _named_game(data.get("system", ""), data.get("rom_path", ""))
    if not key:
        return jsonify(success=False, error="Unknown game"), 404
    try:
        series_index.set_match(key, data.get("id"))
    except (IGDBError, ValueError) as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True)


@app.route("/api/series/overview", methods=["GET"])
def series_overview():
    """Every series the library has games from, the games marked as wanted, and how the matching is going."""
    if not series_index.configured:
        return jsonify(success=True, configured=False, error=NOT_SET_UP)
    overview = series_index.overview(person())
    # The games IGDB had nothing for, by name, to be found by hand
    listed = []
    for key in overview.pop('unmatched_games'):
        system_name, _, path = key.partition('/')
        game = scanner.get_game_details(system_name, path)
        listed.append({'system': system_name, 'path': path, 'name': game.name if game and game.name else path})
    return jsonify(success=True, configured=True, progress=series_index.progress, unmatched_games=listed, **overview)


@app.route("/api/series/run", methods=["POST"])
def series_run():
    """Match the whole library in the background ({redo: true} looks every game up again)."""
    if not series_index.configured:
        return jsonify(success=False, error=NOT_SET_UP), 400
    start_matching(redo=bool(_request_json().get("redo")))
    return jsonify(success=True)


def start_matching(redo=False, started=None):
    """Match the library in the background, unless that's already going or IGDB
    isn't set up. Also the night's run (new games only) and the way a run that a
    restart cut short is picked up again."""
    if not series_index.configured or series_index.progress['running']:
        return False
    threading.Thread(target=lambda: series_index.run(_library(), redo=redo, started=started), daemon=True, name="series-match").start()
    return True


def resume_if_interrupted():
    marker = series_index.interrupted()
    return bool(marker) and start_matching(redo=bool(marker.get('redo')), started=marker.get('started') or None)
