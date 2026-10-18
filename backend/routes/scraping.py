"""
Matching a game on the sources other than ScreenScraper, and IGDB's search, for Fill the gaps
(backend/routes/fill.py), which looks games up and applies what's chosen.
"""

import re

from pathlib import Path
from backend.bulk_scrape import name_score
from backend.folder_games import folder_game_name
from backend.igdb_scraper import IGDBError
from backend.core import (
    _hasheous_lookup,
    _request_rom_file,
    DATA_DIR,
    igdb_scraper,
)

def _hash_match_first(results, match):
    """Put the game found from the ROM's checksum first, without listing it twice."""
    if not match:
        return results
    return [match] + [r for r in results if str(r.get('id')) != str(match.get('id'))]


SCRAPE_MEDIA_FOLDERS = ('box2d', 'box3d', 'boxside', 'screenshot', 'screenshottitle', 'wheel', 'fanart', 'mix', 'support', 'manuals')


# Matching on a source other than ScreenScraper: its matches' ids are
# "<source>:<its id>", which Fill the gaps fetches from that source
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


# Pictures a scrape replaced are kept here, as they were under the media folder
REPLACED_MEDIA = DATA_DIR / 'replaced-media'


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
