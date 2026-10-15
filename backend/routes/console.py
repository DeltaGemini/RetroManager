"""
What the Console page shows beside the systems: the games played most recently
(going by their saves), the favourites, and each collection.
"""

import threading
import time

from flask import jsonify

from pathlib import Path

from backend.core import app, library_state, logger, ROMS_BASE, save_finder, scanner
from backend.media_index import strip_dot_slash
from backend.routes.accounts import person
from backend.routes.saves import _match_save_records
from backend.systems import browser_playable, phone_players

RECENT_GAMES = 12
# Building the lists reads every gamelist and save folder, which takes a while,
# so it's done in the background: a request gets what's ready (or "pending" the
# first time), and anything older than this is worked out again for the next one
MAX_AGE = 120
_caches = {}   # person (None with login off) -> {"time", "value", "building"}
_cache_lock = threading.Lock()


def _cache_for(who):
    return _caches.setdefault(who, {"time": 0.0, "value": None, "building": False})


def _library(who):
    """Every game with a ROM, as the game list has it, plus `_system` (its
    folder) and `_system_label`: {"system/rom path": game}."""
    games = {}
    for system in scanner.discover_systems():
        try:
            listed = scanner.get_games_for_system(system.name)
        except Exception as e:
            logger.warning(f"Console: skipping {system.name}: {e}")
            continue
        for g in listed:
            if not g.rom_exists:
                continue
            key = f"{system.name}/{strip_dot_slash(g.path)}"
            try:
                # The file's own date. (Its change time would be truer to "arrived here", but
                # anything that touches every file's permissions resets that for the lot.)
                added = (Path(ROMS_BASE) / system.name / strip_dot_slash(g.path)).stat().st_mtime
            except OSError:
                added = 0
            games[key] = {**g.to_dict(), **library_state.for_game(key, who), '_added': added,
                          'playable': browser_playable(system.name, g.path),
                          'phone_playable': bool(phone_players(system.name)),
                          '_system': system.name, '_system_label': system.get_full_name()}
    return games


def _build(who):
    games = _library(who)
    # Most recently saved first
    latest = {}
    try:
        for record in _match_save_records(save_finder.scan_all()):
            game = record.get('game')
            # With login on: this person's saves, and the ones nobody's folder holds
            if game and (who is None or record['profile'] in (who, 'shared')):
                key = f"{game['system']}/{game['rom_path']}"
                latest[key] = max(latest.get(key, 0), record['mtime'])
    except Exception:
        logger.exception("Console: couldn't read the saves for the recent games")
    # ...and what a phone said it started (backend/routes/phone.py)
    from backend.routes.phone import played_on_phones
    for key, when in played_on_phones(who).items():
        latest[key] = max(latest.get(key, 0), when)
    recent = [{**games[key], '_last_played': when} for key, when in sorted(latest.items(), key=lambda item: -item[1]) if key in games][:RECENT_GAMES]
    added = sorted(games.values(), key=lambda g: -g['_added'])[:RECENT_GAMES]
    lists = [{'id': 'favourites', 'name': 'Favourites', 'kind': 'favourites', 'games': [g for g in games.values() if g.get('favorite')]}]
    for collection in library_state.snapshot()['collections']:
        lists.append({'id': collection['id'], 'name': collection['name'], 'kind': 'collection',
                      'games': [games[key] for key in collection['games'] if key in games]})
    return {'recent': recent, 'added': added, 'lists': [entry for entry in lists if entry['games']]}


def refresh_in_background(who=None):
    """Work a person's lists out again, unless that's already under way."""
    _cache = _cache_for(who)
    with _cache_lock:
        if _cache["building"]:
            return
        _cache["building"] = True

    def work():
        try:
            value = _build(who)
            with _cache_lock:
                _cache["value"], _cache["time"] = value, time.time()
        except Exception:
            logger.exception("Error building the Console page's lists")
        finally:
            with _cache_lock:
                _cache["building"] = False
    threading.Thread(target=work, daemon=True, name="console-home").start()


@app.route("/api/console/home", methods=["GET"])
def console_home():
    """{recent: [games], added: [games], lists: [{id, name, kind, games}]}: the
    games saved most recently, the newest files, then Favourites and each
    collection that has games. {pending: true}
    while they're being worked out for the first time: ask again shortly."""
    who = person()
    _cache = _cache_for(who)
    with _cache_lock:
        value, age = _cache["value"], time.time() - _cache["time"]
    if value is None or age > MAX_AGE:
        refresh_in_background(who)
    if value is None:
        return jsonify(success=True, pending=True, recent=[], added=[], lists=[])
    return jsonify(success=True, pending=False, **value)
