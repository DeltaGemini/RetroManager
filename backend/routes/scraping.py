"""
Scraping from ScreenScraper and IGDB: search, apply, matching on the other sources
(for Fill the gaps), and filling in a game as it's added.
"""

import re
import shutil
import time

from flask import jsonify
from pathlib import Path
from backend.bulk_scrape import name_score
from backend.models import Game
from backend.folder_games import folder_game_name
from backend.scraper import ScreenscraperError, ScreenscraperNotFound
from backend.igdb_scraper import IGDBError
from backend.libretro_thumbs import THUMBNAIL_TYPES
from backend.retroachievements import ID_PREFIX as RA_ID_PREFIX
from backend.systems import screenscraper_system_id, thegamesdb_platform_id
from backend.media_index import title_key
from backend.steamgriddb import SteamGridDBError
from backend.thegamesdb import TheGamesDBError
from backend.core import (
    _hasheous_lookup,
    _request_json,
    _request_rom_file,
    _saveable_fields,
    app,
    DATA_DIR,
    gamelist_mgr,
    gametdb,
    igdb_scraper,
    jeu_cache,
    launchbox_index,
    libretro_thumbs,
    logger,
    MEDIA_BASE,
    ra_scraper,
    ROMS_BASE,
    scanner,
    scraper,
    settings,
    steamgriddb_scraper,
    thegamesdb_scraper,
)
from backend.routes.media import _download_media, _download_one

def _hash_match_first(results, match):
    """Put the game found from the ROM's checksum first, without listing it twice."""
    if not match:
        return results
    return [match] + [r for r in results if str(r.get('id')) != str(match.get('id'))]


@app.route("/api/scraper/search", methods=["POST"])
def scraper_search():
    """Body: {name, system_name?, system_id?, rom_path?}. With rom_path, the game
    Hasheous knows the file as is listed first."""
    data = _request_json()
    game_name = (data.get("name") or '').strip()
    if not game_name:
        return jsonify(success=False, error="Missing game name"), 400

    system_id = data.get("system_id") or screenscraper_system_id(data.get("system_name"))
    rom_file = _request_rom_file(data)
    known = _hasheous_lookup(data.get("system_name"), rom_file) if rom_file else None
    try:
        jeux = scraper.search_game(game_name, system_id)
        if not jeux and system_id:
            # Retry across all systems in case the folder maps to the wrong one
            jeux = scraper.search_game(game_name)
        hash_match = None
        ss_id = ((known or {}).get('ids') or {}).get('screenscraper')
        if ss_id:
            try:
                jeu = next((j for j in jeux if str(j.get('id')) == str(ss_id)), None) or scraper.get_game_info(ss_id)
                hash_match = scraper.summarize_search_result(jeu, hash_match=True)
            except ScreenscraperNotFound:
                pass
    except ScreenscraperError as e:
        return jsonify(success=False, error=str(e), results=[])

    # Stable sort: hacks go after originals, otherwise ScreenScraper's order is kept
    results = sorted((scraper.summarize_search_result(j) for j in jeux), key=lambda r: r['is_hack'])
    results = _hash_match_first(results, hash_match)
    if not results:
        return jsonify(success=False, error=f'ScreenScraper found nothing for "{game_name}". Try a shorter name.', results=[])
    return jsonify(success=True, results=results)


@app.route("/api/scraper/game-info", methods=["POST"])
def scraper_game_info():
    data = _request_json()
    game_data = data.get("game_data") or {}

    # Search results already carry the full game, which saves an API call
    jeu = game_data.get("jeu")
    if not jeu:
        game_id = data.get("game_id")
        if not game_id:
            return jsonify(success=False, error="Missing game_id"), 400
        try:
            jeu = scraper.get_game_info(game_id, data.get("system_id"))
        except ScreenscraperError as e:
            return jsonify(success=False, error=str(e))

    return jsonify(success=True, metadata=scraper.extract_game_data(jeu))


@app.route("/api/scraper/download-media", methods=["POST"])
def download_scraper_media():
    """Body: {system_name, rom_path, game_name, media_types: {folder: url}}"""
    try:
        return _download_media(_request_json())
    except Exception as e:
        logger.exception("Error in download_scraper_media")
        return jsonify(success=False, error=str(e)), 500
# Text fields apply_scrape may fill; existing values are never replaced
BULK_TEXT_FIELDS = ('name', 'desc', 'genre', 'developer', 'publisher', 'releasedate', 'players', 'rating')
# Media apply_scrape may download, for a game added (videos are left out: large and slow)
SCRAPE_MEDIA_FOLDERS = ('box2d', 'box3d', 'boxside', 'screenshot', 'screenshottitle', 'wheel', 'fanart', 'mix', 'support', 'manuals')


# Matching on a source other than ScreenScraper: its matches' ids are
# "<source>:<its id>", which apply_scrape fetches from that source
BULK_SOURCES = ('igdb', 'retroachievements', 'steam', 'steamgriddb', 'thegamesdb', 'launchbox', 'gametdb', 'libretro')
# A source's names for its pictures -> RetroManager's folders (the rest are its folders' own names)
_SOURCE_PICTURES = {'cover': 'box2d', 'grid': 'box2d', 'hero': 'fanart', 'artwork': 'fanart', 'logo': 'wheel'}


def _as_folders(media):
    """A source's media {name: url} as RetroManager's folders, the first of each (screenshot_1 before _2)."""
    folders = {}
    for key in sorted((media or {}), key=lambda k: (re.sub(r'_\d+$', '', k), int((re.findall(r'_(\d+)$', k) or ['0'])[0]))):
        url = media[key]
        if not url:
            continue
        name = re.sub(r'_\d+$', '', key)
        folder = _SOURCE_PICTURES.get(name, name)
        if folder in SCRAPE_MEDIA_FOLDERS and folder not in folders:
            folders[folder] = url
    return folders


def _source_search(source, system_name, rom_path, name):
    """A source's search results for a game, a checksum match first: summaries
    {id, name, cover_url, platform_names, year, is_hack, hash_match}."""
    data = {'system_name': system_name, 'rom_path': rom_path, 'name': name}
    if source == 'igdb':
        return _igdb_results(data, name)
    from backend.routes.sources import _OTHER_SOURCES
    return _OTHER_SOURCES[source][2](data, name)


def _source_game(source, game_id, system_name):
    """A source's game as gamelist fields plus `media` by RetroManager's folders."""
    if source == 'igdb':
        game = igdb_scraper.get_game_info(game_id)
        if not game:
            raise ValueError("IGDB returned no data for that game.")
        data = igdb_scraper.extract_game_data(game)
    else:
        from backend.routes.sources import _OTHER_SOURCES
        data = _OTHER_SOURCES[source][3]({'game_id': game_id, 'system_name': system_name}) or {}
    return {**data, 'media': _as_folders(data.get('media'))}


def _source_errors():
    from backend.routes.sources import _OTHER_SOURCES
    return (IGDBError, ValueError) + tuple(e for entry in _OTHER_SOURCES.values() for e in entry[1])


def _match_from_source(source, system_name, rom_path, query):
    """bulk_matcher.match's answer, from another source: its results scored by
    how near their names are to the game's (a checksum match is exact)."""
    title = query or folder_game_name(system_name, rom_path) or re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', Path(rom_path).stem).strip()
    results = _source_search(source, system_name, rom_path, title)
    alternatives = []
    for r in results[:8]:
        score = 1.0 if r.get('hash_match') else name_score(title, {'noms': [{'text': r.get('name') or ''}]})
        alternatives.append({'id': f"{source}:{r['id']}", 'nom': r.get('name'), 'year': r.get('year'),
                             'systemenom': r.get('platform_names') or '', 'image': r.get('cover_url'),
                             'score': round(score, 2), 'is_hack': bool(r.get('is_hack')), 'hash_match': bool(r.get('hash_match'))})
    alternatives.sort(key=lambda a: (not a['hash_match'], a['is_hack'], -a['score']))
    best = alternatives[0] if alternatives else None
    if not best:
        confidence = 'none'
    elif best['hash_match']:
        confidence = 'exact'
    else:
        confidence = 'likely' if best['score'] >= 0.9 else 'unsure' if best['score'] >= 0.5 else 'none'
    return {'confidence': confidence, 'match_id': best['id'] if best else None, 'alternatives': alternatives, 'source': source}


def _media_urls(system_name, folder, scraped_url, thumbnails):
    """URLs to try for one media folder, in order. `thumbnails()` returns the
    game's libretro thumbnails ({folder: url}) and is only called when needed."""
    mode = settings.get('libretro_thumbnails')  # "fallback", "first" or "off"
    use_libretro = mode != "off" and folder in THUMBNAIL_TYPES
    if use_libretro and mode == "first":
        yield 'libretro', thumbnails().get(folder)
    yield 'scraped', scraped_url
    if use_libretro and mode == "fallback":
        yield 'libretro', thumbnails().get(folder)


# IGDB pictures that can stand in for a media folder nothing else filled
IGDB_MEDIA_FOLDERS = {'box2d': 'cover', 'screenshot': 'screenshot_1', 'fanart': 'artwork_1'}


def _igdb_for_rom(system_name, rom_path):
    """IGDB's metadata for the game this ROM is, found from its checksum
    (through Hasheous), or {}. Only an exact match is used: a name search could
    pick the wrong game, and this runs without anyone checking it. Never raises."""
    if not igdb_scraper.configured:
        return {}
    rom_file = Path(ROMS_BASE) / system_name / rom_path
    try:
        if not rom_file.is_file():
            return {}
        igdb_id = ((_hasheous_lookup(system_name, rom_file) or {}).get('ids') or {}).get('igdb')
        if not igdb_id or not igdb_id.isdigit():
            return {}
        game = igdb_scraper.get_game_info(igdb_id)
        return igdb_scraper.extract_game_data(game) if game else {}
    except (IGDBError, OSError) as e:
        logger.warning(f"IGDB lookup for {system_name}/{rom_path} failed: {e}")
        return {}


# SteamGridDB pictures that can stand in for a media folder nothing else filled
STEAMGRIDDB_MEDIA_FOLDERS = {'box2d': 'grid_1', 'fanart': 'hero_1', 'wheel': 'logo_1'}
# A source that failed (its quota, usually) is left alone for this long, not asked for every game
_SOURCE_REST = 15 * 60
_resting = {}


def _resting_source(name, error=None):
    """Whether a source is being left alone after failing; with `error`, starts that."""
    if error is not None:
        logger.warning(f"{name} couldn't be asked, so it's left out for a while: {error}")
        _resting[name] = time.time() + _SOURCE_REST
    return _resting.get(name, 0) > time.time()


def _thegamesdb_pictures(system_name, names):
    """TheGamesDB's pictures ({media folder: url}) for the game with one of
    these names on this system, or {}. It can't look a ROM up by checksum, so
    only a game on the system's own platform whose title is the same (but for
    tags and punctuation) is used. Never raises."""
    keys = {title_key(n) for n in names if n} - {''}
    if not thegamesdb_scraper.configured or not keys or not thegamesdb_platform_id(system_name) or _resting_source('TheGamesDB'):
        return {}
    try:
        for name in dict.fromkeys(n for n in names if n and title_key(n)):
            for found in thegamesdb_scraper.search_game(name, system_name):
                if title_key(found.get('game_title') or '') in keys:
                    return thegamesdb_scraper.extract_game_data({'_images': thegamesdb_scraper.get_images(found.get('id'))})['media']
            break  # one search a game: its allowance is by the month
    except TheGamesDBError as e:
        _resting_source('TheGamesDB', e)
    return {}


def _steamgriddb_pictures(system_name, rom_path, names):
    """SteamGridDB's pictures ({media folder: url}) for this game, or {}: the
    game its checksum identifies there (through Hasheous), else one whose title
    is the same but for tags and punctuation. Never raises."""
    keys = {title_key(n) for n in names if n} - {''}
    if not steamgriddb_scraper.configured or _resting_source('SteamGridDB'):
        return {}
    try:
        rom_file = Path(ROMS_BASE) / system_name / rom_path
        known = _hasheous_lookup(system_name, rom_file) if rom_file.is_file() else None
        game_id = ((known or {}).get('ids') or {}).get('steamgriddb')
        if not (game_id and str(game_id).isdigit()):
            name = next((n for n in names if n and title_key(n)), None)
            game_id = next((g.get('id') for g in (steamgriddb_scraper.search_game(name) if name else [])
                            if title_key(g.get('name') or '') in keys), None)
        if not game_id:
            return {}
        media = steamgriddb_scraper.extract_game_data(steamgriddb_scraper.get_game_info(game_id))['media']
        return {folder: media[key] for folder, key in STEAMGRIDDB_MEDIA_FOLDERS.items() if media.get(key)}
    except (SteamGridDBError, OSError) as e:
        _resting_source('SteamGridDB', e)
    return {}


# Pictures a scrape replaced are kept here, as they were under the media folder
REPLACED_MEDIA = DATA_DIR / 'replaced-media'


def apply_scrape(system_name, rom_path, game_id, wanted_media, replace=False):
    """Fill a game's empty fields from a matched game (ScreenScraper's, or a
    RetroAchievements one when the id starts "ra:"), download the media it
    doesn't have yet, link <image>/<thumbnail>/<video> and save the entry.
    What the match leaves empty (a RetroAchievements match has no description,
    say) is filled from IGDB when the ROM's checksum identifies the game there.
    A picture none of those has is looked for at GameTDB (a disc or cartridge,
    by the ID in the ROM), then LaunchBox, TheGamesDB and SteamGridDB (where
    they're set up), for a game of the same title.
    With `replace`, media the game already has is downloaded again too, for
    pictures that are the wrong ones: the old file is copied to
    DATA_PATH/replaced-media/<when>/ first, and stays if the download fails.
    Raises ScreenscraperError on quota/credential problems and
    RetroAchievementsError when that site can't be asked."""
    game = scanner.get_game_details(system_name, rom_path)
    if game is None:
        return dict(success=False, error="Game not found")
    known_names = []
    source, _, raw = str(game_id).partition(':')
    if source in BULK_SOURCES and raw:
        # A match from another source (Fill the gaps, or the scrape popup)
        scraped = _source_game(source, raw, system_name)
    elif str(game_id).startswith(RA_ID_PREFIX):
        scraped = ra_scraper.extract_game_data(ra_scraper.get_game_info(game_id))
    else:
        jeu = jeu_cache.get(game_id) or scraper.get_game_info(game_id)
        scraped = scraper.extract_game_data(jeu)
        # The name ScreenScraper knows the ROM by is usually its No-Intro name
        known_names.append(Path((jeu.get('rom') or {}).get('romfilename') or '').stem)

    current = game.to_dict()
    merged = dict(current)
    filled, from_igdb = [], []
    second_cache = {}

    def second_source():
        if 'data' not in second_cache:
            second_cache['data'] = _igdb_for_rom(system_name, rom_path)
        return second_cache['data']

    for field in BULK_TEXT_FIELDS:
        value = scraped.get(field)
        # A game without an entry only has a name made from its file name, so it's replaced too
        has_value = current.get(field) not in (None, '') and (game.has_metadata or field != 'name')
        if has_value:
            continue
        if value in (None, '') and field != 'name':
            # The match has nothing for this field: try the second source
            value = second_source().get(field)
            if value not in (None, ''):
                from_igdb.append(field)
        if value not in (None, ''):
            merged[field] = value
            filled.append(field)

    stem = Path(rom_path).stem
    index = scanner.media_index(system_name)
    downloaded, skipped, errors, from_libretro, replaced = [], [], [], [], []
    kept_at = REPLACED_MEDIA / time.strftime('%Y%m%d-%H%M%S')
    thumbnail_cache = {}
    from_others = {'gametdb': [], 'launchbox': [], 'thegamesdb': [], 'steamgriddb': []}

    def thumbnails():
        if 'found' not in thumbnail_cache:
            names = [stem] + known_names + [folder_game_name(system_name, rom_path), scraped.get('name')]
            thumbnail_cache['found'] = libretro_thumbs.find(system_name, names)
        return thumbnail_cache['found']

    other_cache = {}

    def others(folder):
        """The same picture from the sources asked last, only as each is needed."""
        if folder in IGDB_MEDIA_FOLDERS:
            yield 'igdb', (second_source().get('media') or {}).get(IGDB_MEDIA_FOLDERS[folder])
        names = [merged.get('name'), scraped.get('name'), folder_game_name(system_name, rom_path), stem]
        if folder == 'support':
            # The disc or cartridge of the game whose ID is in the ROM itself
            if 'gametdb' not in other_cache:
                other_cache['gametdb'] = gametdb.support_url(system_name, Path(ROMS_BASE) / system_name / rom_path)
            yield 'gametdb', other_cache['gametdb']
        if 'launchbox' not in other_cache:
            other_cache['launchbox'] = launchbox_index.pictures(system_name, names)
        yield 'launchbox', other_cache['launchbox'].get(folder)
        if 'thegamesdb' not in other_cache:
            other_cache['thegamesdb'] = _thegamesdb_pictures(system_name, names)
        yield 'thegamesdb', other_cache['thegamesdb'].get(folder)
        if folder in STEAMGRIDDB_MEDIA_FOLDERS:
            if 'steamgriddb' not in other_cache:
                other_cache['steamgriddb'] = _steamgriddb_pictures(system_name, rom_path, names)
            yield 'steamgriddb', other_cache['steamgriddb'].get(folder)

    for folder in wanted_media:
        had = index.find(folder, stem)
        if had and not (replace and scraped.get('media', {}).get(folder)):
            if scraped.get('media', {}).get(folder):
                skipped.append(folder)
            continue
        if had:
            # Being replaced: the one it has is kept first
            try:
                (kept_at / had).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(MEDIA_BASE) / had, kept_at / had)
            except OSError as e:
                errors.append(f"{folder}: couldn't keep the old one, so it wasn't replaced ({e})")
                continue
        problem = None
        candidates = list(_media_urls(system_name, folder, scraped.get('media', {}).get(folder), thumbnails))
        if not any(url for _, url in candidates):
            # Nothing from the match or libretro: IGDB's picture if the checksum finds the game
            # there, GameTDB's by the ROM's ID, then LaunchBox's, TheGamesDB's and SteamGridDB's by title
            candidates = others(folder)
        for source, url in candidates:
            if not url:
                continue
            try:
                _download_one(url, Path(MEDIA_BASE) / index.media_system / folder, stem)
            except (ValueError, OSError) as e:
                problem = problem or f"{folder}: {e}"
                continue
            downloaded.append(folder)
            if had:
                replaced.append(folder)
            if source == 'libretro':
                from_libretro.append(folder)
            elif source == 'igdb':
                from_igdb.append(folder)
            elif source in from_others:
                from_others[source].append(folder)
            problem = None
            break
        if problem:
            errors.append(problem)

    # Link what EmulationStation shows, where it's empty or points at a missing file
    links = scanner.media_index(system_name).suggest_links(stem)
    for xml_field, media_path in links.items():
        current_path = merged.get(xml_field)
        if current_path and (Path(MEDIA_BASE) / current_path).is_file():
            continue
        merged[xml_field] = media_path
        filled.append(xml_field)

    merged['path'] = f"./{rom_path}"
    new_game = Game.from_dict(_saveable_fields(merged))
    if game.has_metadata:
        ok = gamelist_mgr.update_game(system_name, rom_path, new_game, ROMS_BASE)
    else:
        ok = gamelist_mgr.save_game(system_name, new_game, ROMS_BASE)
    if not ok:
        return dict(success=False, error="Couldn't write gamelist.xml", downloaded=downloaded, errors=errors)
    return dict(success=True, filled=filled, downloaded=downloaded, already_had=skipped, errors=errors,
                from_libretro=from_libretro, from_igdb=from_igdb, replaced=replaced,
                from_gametdb=from_others['gametdb'], from_launchbox=from_others['launchbox'],
                from_thegamesdb=from_others['thegamesdb'], from_steamgriddb=from_others['steamgriddb'],
                kept=str(kept_at.relative_to(DATA_DIR)) if replaced else None)


def _igdb_results(data, game_name):
    """IGDB's search results, the game Hasheous knows the ROM as first. Raises IGDBError."""
    rom_file = _request_rom_file(data)
    known = _hasheous_lookup(data.get("system_name"), rom_file) if rom_file else None
    games = igdb_scraper.search_game(game_name, data.get("system_name"))
    hash_match = None
    igdb_id = ((known or {}).get('ids') or {}).get('igdb')
    if igdb_id and igdb_id.isdigit():
        game = next((g for g in games if str(g.get('id')) == igdb_id), None) or igdb_scraper.get_search_result(igdb_id)
        if game:
            hash_match = igdb_scraper.summarize_search_result(game, hash_match=True)
    results = sorted((igdb_scraper.summarize_search_result(g) for g in games), key=lambda r: r['is_hack'])
    return _hash_match_first(results, hash_match)


@app.route("/api/igdb/search", methods=["POST"])
def igdb_search():
    """Body: {name, system_name?, rom_path?}. With rom_path, the game Hasheous
    knows the file as is listed first, whatever IGDB's search ranks above it."""
    data = _request_json()
    game_name = (data.get("name") or '').strip()
    if not game_name:
        return jsonify(success=False, error="Missing game name"), 400

    try:
        results = _igdb_results(data, game_name)
    except IGDBError as e:
        return jsonify(success=False, error=str(e), results=[])
    if not results:
        return jsonify(success=False, error=f'IGDB found nothing for "{game_name}". Try a shorter name.', results=[])
    return jsonify(success=True, results=results, source='igdb')


@app.route("/api/igdb/game-info", methods=["POST"])
def igdb_game_info():
    data = _request_json()
    game_id = data.get("game_id")
    if not game_id:
        return jsonify(success=False, error="Missing game_id"), 400

    try:
        game = igdb_scraper.get_game_info(game_id)
    except IGDBError as e:
        return jsonify(success=False, error=str(e))
    if not game:
        return jsonify(success=False, error="IGDB returned no data for that game.")

    return jsonify(success=True, metadata=igdb_scraper.extract_game_data(game))


@app.route("/api/igdb/download-media", methods=["POST"])
def igdb_download_media():
    """Body: {system_name, rom_path, game_name, media_types: {folder: url}}"""
    try:
        return _download_media(_request_json())
    except Exception as e:
        logger.exception("Error in igdb_download_media")
        return jsonify(success=False, error=str(e)), 500
