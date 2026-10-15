"""
RetroAchievements: a game's achievements and the overview of every game with progress.
"""

from flask import jsonify, request
from backend.name_style import style_name
from backend.retroachievements import RetroAchievementsError
from backend.systems import retroachievements_console_id
from backend.media_index import strip_dot_slash
from backend.media_index import title_key
from difflib import SequenceMatcher
from backend.routes.accounts import person
from backend.core import (
    ra_people,
    ra_user_for,
    _hasheous_lookup,
    _ra_identify,
    _request_rom_file,
    app,
    logger,
    ra_game_ids,
    ra_scraper,
    scanner,
)

@app.route("/api/systems/<system_name>/achievements", methods=["GET"])
def get_game_achievements(system_name):
    """?rom=<path>[&refresh=1]. The game's RetroAchievements list, with the ones
    the RetroAchievements user in Settings has earned. `configured` is false without an API key;
    `matched` is false when RetroAchievements doesn't know the ROM."""
    if not ra_scraper.configured:
        return jsonify(success=True, configured=False, matched=False)
    data = {"system_name": system_name, "rom_path": request.args.get("rom", "")}
    rom_file = _request_rom_file(data)
    if not rom_file:
        # Game folders and missing files have no checksum to look up
        return jsonify(success=True, configured=True, matched=False)
    refresh = request.args.get("refresh") == "1"
    key = f"{system_name}/{strip_dot_slash(data['rom_path'])}"
    known, game_id = ra_game_ids.get(key, rom_file)
    if not known or (refresh and game_id is None):
        game = _ra_identify(system_name, rom_file, _hasheous_lookup(system_name, rom_file))
        game_id = game.get('id') if game else None
        ra_game_ids.put(key, rom_file, game_id)
    if not game_id:
        return jsonify(success=True, configured=True, matched=False)
    try:
        return jsonify(success=True, configured=True, matched=True, people=[p['name'] for p in ra_people()],
                       **ra_scraper.get_achievements(game_id, refresh, ra_user_for(request.args.get("who") or person())))
    except RetroAchievementsError as e:
        return jsonify(success=False, configured=True, error=str(e))


def _library_game_for(progress, by_console):
    """The library game an achievement-overview row is about, or None: a ROM
    already identified as that game by checksum, else the closest title on a
    system of the same console."""
    known = None
    for key in ra_game_ids.roms_for(progress['game_id']):
        system, _, rom_path = key.partition('/')
        known = next((g for g in by_console.get(progress['console_id'], []) if g['system'] == system and g['rom_path'] == rom_path), known)
    if known:
        return known
    best, best_score = None, 0.0
    for part in progress['title'].split('|'):
        wanted = title_key(style_name(part.strip()))
        if not wanted:
            continue
        for game in by_console.get(progress['console_id'], []):
            score = SequenceMatcher(None, wanted, game['key']).ratio()
            if score > best_score:
                best, best_score = game, score
    return best if best_score >= 0.9 else None


@app.route("/api/achievements/overview", methods=["GET"])
def achievements_overview():
    """[?refresh=1]. Every game the RetroAchievements user in Settings has earned an achievement
    in, most complete first, each with the library game it matches (if any)."""
    if not ra_scraper.configured:
        return jsonify(success=True, configured=False, games=[])
    try:
        user = ra_user_for(request.args.get("who") or person())
        progress = ra_scraper.get_user_progress(request.args.get("refresh") == "1", user)
    except RetroAchievementsError as e:
        return jsonify(success=False, configured=True, error=str(e))

    wanted_consoles = {g['console_id'] for g in progress}
    by_console = {}
    for system in scanner.discover_systems():
        console_id = retroachievements_console_id(system.name)
        if console_id not in wanted_consoles:
            continue
        try:
            games = scanner.get_games_for_system(system.name)
        except Exception as e:
            logger.warning(f"Achievement overview: couldn't list {system.name}: {e}")
            continue
        for game in games:
            if game.rom_exists:
                by_console.setdefault(console_id, []).append({
                    'system': system.name, 'full_name': system.get_full_name(), 'rom_path': strip_dot_slash(game.path),
                    'name': game.name, 'box2d': game.box2d, 'key': title_key(style_name(game.name or '')),
                })

    rows = []
    for item in progress:
        match = _library_game_for(item, by_console)
        rows.append({**item, 'library': {k: match[k] for k in ('system', 'full_name', 'rom_path', 'name', 'box2d')} if match else None})
    return jsonify(success=True, configured=True, user=user, people=[p['name'] for p in ra_people()], games=rows,
                   total=sum(g['total'] for g in rows), earned=sum(g['earned'] for g in rows))


@app.route("/api/achievements/unlocks", methods=["GET"])
def achievement_unlocks():
    """[?who=<person>&refresh=1]. A person's achievements over time: the latest
    60 unlocks, and how many were earned each month with a running total."""
    if not ra_scraper.configured:
        return jsonify(success=True, configured=False, unlocks=[], months=[])
    try:
        user = ra_user_for(request.args.get("who") or person())
        unlocks = ra_scraper.get_unlocks(request.args.get("refresh") == "1", user)
    except RetroAchievementsError as e:
        return jsonify(success=False, configured=True, error=str(e))
    per_month = {}
    for unlock in unlocks:
        per_month[unlock['date'][:7]] = per_month.get(unlock['date'][:7], 0) + 1
    months, total = [], 0
    for month in sorted(per_month):
        total += per_month[month]
        months.append({'month': month, 'earned': per_month[month], 'total': total})
    return jsonify(success=True, configured=True, user=user, people=[p['name'] for p in ra_people()],
                   count=len(unlocks), unlocks=unlocks[:60], months=months)
