"""
Other sources: RetroAchievements, Steam, SteamGridDB, TheGamesDB and libretro thumbnails.
"""

from flask import jsonify
from pathlib import Path
from backend.retroachievements import RetroAchievementsError
from backend.steam import SteamError
from backend.steamgriddb import SteamGridDBError
from backend.thegamesdb import TheGamesDBError
from backend.systems import libretro_thumbnail_folder
from backend.media_index import strip_dot_slash
from backend.core import (
    _hasheous_lookup,
    _ra_identify,
    _request_json,
    _request_rom_file,
    app,
    hasheous,
    igdb_scraper,
    libretro_thumbs,
    logger,
    ra_scraper,
    scraper,
    settings,
    steam_scraper,
    steamgriddb_scraper,
    gametdb,
    launchbox_index,
    thegamesdb_scraper,
)
from backend.routes.scraping import _hash_match_first

# -----------------------------------------------------------------------------
# Other sources: RetroAchievements, Steam, SteamGridDB, libretro thumbnails.
# Each has a search and a game-info route shaped like ScreenScraper's and IGDB's;
# media is downloaded through /api/scraper/download-media.
# -----------------------------------------------------------------------------
def available_sources():
    """Every source, with whether it can be used here: [{id, label, available, hint}]."""
    def source(source_id, label, available, missing):
        return {'id': source_id, 'label': label, 'available': available,
                'hint': None if available else f'Add {missing} in Tools > Settings to use {label}'}
    return [
        source('screenscraper', 'ScreenScraper', scraper.configured, 'the ScreenScraper developer credentials'),
        source('igdb', 'IGDB', igdb_scraper.configured, 'the IGDB client ID and secret'),
        source('retroachievements', 'RetroAchievements', ra_scraper.configured, 'your RetroAchievements API key'),
        {'id': 'steam', 'label': 'Steam', 'available': True},
        source('steamgriddb', 'SteamGridDB', steamgriddb_scraper.configured, 'your SteamGridDB API key'),
        source('thegamesdb', 'TheGamesDB', thegamesdb_scraper.configured, 'your TheGamesDB API key'),
        {'id': 'launchbox', 'label': 'LaunchBox', 'available': launchbox_index.enabled and launchbox_index.ready,
         'hint': None if launchbox_index.enabled and launchbox_index.ready else
         ("LaunchBox's list of games is still being fetched" if launchbox_index.enabled else 'LaunchBox is switched off in Tools > Settings')},
        {'id': 'gametdb', 'label': 'GameTDB', 'available': True},
        {'id': 'libretro', 'label': 'libretro thumbnails', 'available': libretro_thumbs.enabled,
         'hint': None if libretro_thumbs.enabled else 'libretro thumbnails are switched off in Tools > Settings'},
    ]


@app.route("/api/scrape-sources", methods=["GET"])
def scrape_sources():
    """Which sources the Scrape popup can offer. `available` is false for one
    that needs a key that isn't set, with `hint` saying which."""
    return jsonify(success=True, sources=available_sources(), hasheous=hasheous.enabled, libretro_mode=settings.get('libretro_thumbnails'))


def _ra_search(data, game_name):
    system_name = data.get("system_name")
    rom_file = _request_rom_file(data)
    hash_match = None
    if rom_file:
        game = _ra_identify(system_name, rom_file, _hasheous_lookup(system_name, rom_file))
        if game:
            hash_match = {**ra_scraper.summarize_search_result(game), 'hash_match': True}
    try:
        results = [ra_scraper.summarize_search_result(g) for g in ra_scraper.search_game(game_name, system_name)]
    except RetroAchievementsError:
        if not hash_match:
            raise
        results = []
    return _hash_match_first(sorted(results, key=lambda r: r['is_hack']), hash_match)


def _steamgriddb_search(data, game_name):
    rom_file = _request_rom_file(data)
    known = _hasheous_lookup(data.get("system_name"), rom_file) if rom_file else None
    games = steamgriddb_scraper.search_game(game_name)
    hash_match = None
    grid_id = ((known or {}).get('ids') or {}).get('steamgriddb')
    if grid_id and grid_id.isdigit():
        game = next((g for g in games if str(g.get('id')) == grid_id), None) or steamgriddb_scraper.get_game(grid_id)
        if game:
            hash_match = steamgriddb_scraper.summarize_search_result(game, hash_match=True)
    return _hash_match_first([steamgriddb_scraper.summarize_search_result(g) for g in games], hash_match)


def _libretro_search(data, game_name):
    system_name = data.get("system_name")
    if not libretro_thumbnail_folder(system_name):
        raise ValueError("libretro has no thumbnails for this system (or RetroManager doesn't know its folder name).")
    # Thumbnails are filed by exact name, so there is at most one result: the
    # ROM's own name if libretro has it, else the text you typed
    rom_stem = Path(strip_dot_slash(data.get("rom_path"))).stem
    name = libretro_thumbs.matching_name(system_name, [rom_stem, game_name])
    if not name:
        return []
    return [{'id': name, 'name': name, 'cover_url': libretro_thumbs.url(system_name, 'box2d', name),
             'platform_names': libretro_thumbnail_folder(system_name), 'year': None, 'regions': [],
             'is_hack': False, 'hash_match': False}]
def _launchbox_search(data, game_name):
    return [{'id': g['id'], 'name': g['name'], 'cover_url': g['cover_url'], 'platform_names': g['platform'], 'year': None,
             'regions': [], 'is_hack': False, 'hash_match': False}
            for g in launchbox_index.search(data.get("system_name"), game_name)]


def _gametdb_search(data, game_name):
    # Filed by the ID inside the ROM, so there is one result at most: this game
    found = gametdb.find(data.get("system_name"), _request_rom_file(data))
    media = gametdb.game(found)
    if not media:
        return []
    return [{'id': found, 'name': f"{game_name} ({found.split(':')[1]})", 'cover_url': media.get('box2d') or media.get('support'),
             'platform_names': 'GameTDB, by the ID in the ROM', 'year': None, 'regions': [], 'is_hack': False, 'hash_match': True}]


# source -> (name, error types whose message is shown, search, game-info)
_OTHER_SOURCES = {
    'retroachievements': (
        'RetroAchievements', (RetroAchievementsError,), _ra_search,
        lambda data: ra_scraper.extract_game_data(ra_scraper.get_game_info(data.get("game_id"))),
    ),
    'steam': (
        'Steam', (SteamError,),
        lambda data, name: [steam_scraper.summarize_search_result(i) for i in steam_scraper.search_game(name)],
        lambda data: steam_scraper.extract_game_data(steam_scraper.get_game_info(data.get("game_id"))),
    ),
    'steamgriddb': (
        'SteamGridDB', (SteamGridDBError,), _steamgriddb_search,
        lambda data: steamgriddb_scraper.extract_game_data(steamgriddb_scraper.get_game_info(data.get("game_id"))),
    ),
    'thegamesdb': (
        'TheGamesDB', (TheGamesDBError,),
        lambda data, name: [thegamesdb_scraper.summarize_search_result(g) for g in thegamesdb_scraper.search_game(name, data.get("system_name"))],
        lambda data: thegamesdb_scraper.extract_game_data(thegamesdb_scraper.get_game_info(data.get("game_id"))),
    ),
    'launchbox': (
        'LaunchBox', (ValueError,), _launchbox_search,
        lambda data: launchbox_index.game(data.get("game_id")),
    ),
    'gametdb': (
        'GameTDB', (ValueError,), _gametdb_search,
        lambda data: {'media': gametdb.game(data.get("game_id"))},
    ),
    'libretro': (
        'libretro', (ValueError,), _libretro_search,
        lambda data: {'media': libretro_thumbs.find(data.get("system_name"), [str(data.get("game_id") or '')])},
    ),
}


@app.route("/api/sources/<source>/search", methods=["POST"])
def source_search(source):
    """Body: {name, system_name?, rom_path?}. With rom_path, a game recognised
    from the ROM's checksum is listed first (hash_match: true)."""
    if source not in _OTHER_SOURCES:
        return jsonify(success=False, error="Unknown source"), 404
    label, errors, search, _ = _OTHER_SOURCES[source]
    data = _request_json()
    game_name = (data.get("name") or '').strip()
    if not game_name:
        return jsonify(success=False, error="Missing game name"), 400
    try:
        results = search(data, game_name)
    except errors as e:
        return jsonify(success=False, error=str(e), results=[])
    except Exception as e:
        logger.exception(f"Error searching {label}")
        return jsonify(success=False, error=str(e), results=[]), 500
    if not results:
        return jsonify(success=False, error=f'{label} found nothing for "{game_name}". Try a shorter name.', results=[])
    return jsonify(success=True, results=results, source=source)


@app.route("/api/sources/<source>/game-info", methods=["POST"])
def source_game_info(source):
    """Body: {game_id, system_name?}. Returns `metadata` with gamelist field names
    and a `media` dict, like the ScreenScraper and IGDB routes."""
    if source not in _OTHER_SOURCES:
        return jsonify(success=False, error="Unknown source"), 404
    label, errors, _, game_info = _OTHER_SOURCES[source]
    data = _request_json()
    if not data.get("game_id"):
        return jsonify(success=False, error="Missing game_id"), 400
    try:
        metadata = game_info(data)
    except errors as e:
        return jsonify(success=False, error=str(e))
    except Exception as e:
        logger.exception(f"Error loading {label} game")
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True, metadata=metadata)
