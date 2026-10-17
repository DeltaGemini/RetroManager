"""
Fill the gaps: for a system's games, every source's version of the pictures
and details a game is missing (or has, to replace), side by side to choose
from, then the chosen ones put in.

/api/fill/look       one game: its match on each source (remembered, or matched
                     now, the sources at once), and each matched source's
                     pictures {folder: url} and details {field: value}
/api/fill/apply      one game: the chosen pictures downloaded, or a made spine or
                     3D box put in (backend/routes/boxes.py) (one replaced is
                     kept in replaced-media first), the chosen details written,
                     and its matches remembered
/api/fill/picture    a picture pasted or dropped in, kept to choose and apply
/api/fill/remembered which of a system's games have matches remembered

Matches are remembered (backend/match_memory.py) when they're Exact or Likely,
or chosen by hand, so a game isn't looked up again next time.
"""

import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from flask import jsonify, request

from backend.core import (
    _game_moved_hooks, _request_json, _saveable_fields, _system_path_or_none, app, bulk_matcher, DATA_DIR,
    gamelist_mgr, jeu_cache, logger, MEDIA_BASE, media_sources, mix_provenance, ROMS_BASE, scanner, scraper,
)
from backend.folder_games import folder_game_name
from backend.match_memory import MatchMemory
from backend.media_index import strip_dot_slash
from backend.models import Game
from backend.routes.boxes import keep_picture, made_file
from backend.routes.media import _download_one, _remove_other_formats
from backend.routes.scraping import BULK_SOURCES, REPLACED_MEDIA, _match_from_source, _source_game
from backend.routes.sources import available_sources

match_memory = MatchMemory(DATA_DIR)
_game_moved_hooks.append(match_memory.game_moved)

# The pictures, then the files (a manual, a video: only ScreenScraper has them)
FILL_PICTURES = ('box2d', 'box3d', 'boxside', 'support', 'screenshot', 'screenshottitle', 'wheel', 'fanart', 'mix')
FILL_MEDIA = FILL_PICTURES + ('manuals', 'videos')
# The largest picture that can be pasted in
PICTURE_LIMIT = 30 * 1024 * 1024
FILL_FIELDS = ('name', 'desc', 'releasedate', 'developer', 'publisher', 'genre', 'players', 'rating')
FILL_SOURCES = ('screenscraper',) + BULK_SOURCES
# What's kept of a source's search results, for "wrong game?"
ALTERNATIVES = 6


def _key(system, rom_path):
    return f"{system}/{strip_dot_slash(rom_path)}"


def _match(source, system, rom_path, query=None):
    """{confidence, id, name, alternatives} of a source's best match for a game."""
    if source == 'screenscraper':
        found = bulk_matcher.match(system, rom_path, Path(ROMS_BASE) / system / rom_path, query, title=folder_game_name(system, rom_path))
    else:
        found = _match_from_source(source, system, rom_path, query)
    alternatives = found.get('alternatives') or []
    best = next((a for a in alternatives if str(a.get('id')) == str(found.get('match_id'))), None)
    return {'confidence': found.get('confidence') or 'none', 'id': found.get('match_id'), 'name': (best or {}).get('nom'),
            'alternatives': [{'id': a.get('id'), 'name': a.get('nom'), 'year': a.get('year'), 'platform': a.get('systemenom'),
                              'score': a.get('score'), 'hash_match': a.get('hash_match')} for a in alternatives[:ALTERNATIVES]]}


def _candidates(source, match_id, system):
    """A matched game's {media: {folder: url}, fields: {field: value}} from its source."""
    if source == 'screenscraper':
        data = scraper.extract_game_data(jeu_cache.get(match_id) or scraper.get_game_info(match_id))
    else:
        data = _source_game(source, str(match_id).partition(':')[2], system)
    return {'media': {k: v for k, v in (data.get('media') or {}).items() if k in FILL_MEDIA and v},
            'fields': {k: data.get(k) for k in FILL_FIELDS if data.get(k) not in (None, '')}}


def _look_one(source, system, rom_path, remembered, rematch):
    """One source's part of /api/fill/look (run beside the others)."""
    try:
        if rematch is not None:
            match = _match(source, system, rom_path, rematch.get('query'))
            if rematch.get('id'):
                pick = next((a for a in match['alternatives'] if str(a['id']) == str(rematch['id'])), None)
                match = {**match, 'id': rematch['id'], 'name': (pick or {}).get('name') or rematch.get('name'), 'confidence': 'chosen'}
        elif remembered:
            match = {**remembered, 'alternatives': [], 'remembered': True}
        else:
            match = _match(source, system, rom_path)
        result = {'match': match, 'candidates': None}
        if match.get('id') and match.get('confidence') != 'none':
            result['candidates'] = _candidates(source, match['id'], system)
        return result
    except Exception as e:
        logger.info(f"Fill the gaps: {source} couldn't be asked about {system}/{rom_path}: {e}")
        return {'match': {'confidence': 'none', 'id': None, 'alternatives': [], 'error': str(e)}, 'candidates': None}


@app.route("/api/fill/look", methods=["POST"])
def fill_look():
    """Body: {system_name, rom_path, sources: [ids], rematch?: {source, query?, id?}}.
    -> {sources: {id: {match: {confidence, id, name, alternatives, remembered?, error?},
                       candidates: {media, fields} | null}}}"""
    data = _request_json()
    system = data.get("system_name")
    rom_path = strip_dot_slash(data.get("rom_path"))
    if not _system_path_or_none(system) or not rom_path:
        return jsonify(success=False, error="Missing or unknown system_name / rom_path"), 400
    usable = {s['id']: s['available'] for s in available_sources()}
    wanted = [s for s in (data.get("sources") or FILL_SOURCES) if s in FILL_SOURCES and usable.get(s)]
    rematch = data.get("rematch") or {}
    if rematch:
        wanted = [s for s in wanted if s == rematch.get('source')]
    remembered = match_memory.get(_key(system, rom_path))
    with ThreadPoolExecutor(max_workers=max(1, len(wanted))) as pool:
        jobs = {s: pool.submit(_look_one, s, system, rom_path, remembered.get(s), rematch if s == rematch.get('source') else None) for s in wanted}
        return jsonify(success=True, sources={s: job.result() for s, job in jobs.items()})


@app.route("/api/fill/picture", methods=["POST"])
def fill_picture():
    """The body is a picture pasted or dropped in (from a web search, say): kept a day,
    to choose and apply as "made:<token>". -> {token, url}"""
    if (request.content_length or 0) > PICTURE_LIMIT:
        return jsonify(success=False, error="That picture is too large (30 MB at most)"), 413
    try:
        token, url = keep_picture(request.get_data())
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, token=token, url=url)


@app.route("/api/fill/remembered", methods=["GET"])
def fill_remembered():
    """?system=: {rom path: [sources with a remembered match]}."""
    return jsonify(success=True, games={rom: sorted(matches) for rom, matches in match_memory.keys_for(request.args.get('system', '')).items()})


def _web_address(url):
    return isinstance(url, str) and urlparse(url).scheme in ('http', 'https') and bool(urlparse(url).netloc)


@app.route("/api/fill/apply", methods=["POST"])
def fill_apply():
    """Body: {system_name, rom_path, pictures: {folder: url}, fields: {field: value},
    remember: {source: {id, name, confidence}}}. Back the gamelist up first.
    -> {success, downloaded, replaced, filled, errors, kept}"""
    data = _request_json()
    system = data.get("system_name")
    rom_path = strip_dot_slash(data.get("rom_path"))
    if not _system_path_or_none(system) or not rom_path:
        return jsonify(success=False, error="Missing or unknown system_name / rom_path"), 400
    game = scanner.get_game_details(system, rom_path)
    if game is None:
        return jsonify(success=False, error="Game not found"), 404

    stem = Path(rom_path).stem
    index = scanner.media_index(system)
    downloaded, replaced, errors = [], [], []
    kept_at = REPLACED_MEDIA / time.strftime('%Y%m%d-%H%M%S')
    for folder, url in (data.get("pictures") or {}).items():
        # A spine or 3D box made here (backend/routes/boxes.py), or a picture pasted in: "made:<token>"
        made = made_file(url[5:]) if folder in FILL_PICTURES and isinstance(url, str) and url.startswith('made:') else None
        if folder not in FILL_MEDIA or not (made or _web_address(url)):
            errors.append(f"{folder}: not something RetroManager can fetch")
            continue
        had = index.find(folder, stem)
        if had:
            # Being replaced: the one it has is kept first
            try:
                (kept_at / had).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(MEDIA_BASE) / had, kept_at / had)
            except OSError as e:
                errors.append(f"{folder}: couldn't keep the old one, so it wasn't replaced ({e})")
                continue
        try:
            if made:
                target = Path(MEDIA_BASE) / index.media_system / folder / f"{stem}{made.suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(made, target)
                _remove_other_formats(target)
                media_sources.record(target, 'RetroManager (made)')
            else:
                _download_one(url, Path(MEDIA_BASE) / index.media_system / folder, stem)
        except (ValueError, OSError) as e:
            errors.append(f"{folder}: {e}")
            continue
        downloaded.append(folder)
        if had:
            replaced.append(folder)
        if folder == 'mix':
            mix_provenance.forget(system, rom_path)

    merged = game.to_dict()
    filled = []
    for field, value in (data.get("fields") or {}).items():
        if field in FILL_FIELDS and value not in (None, '') and str(value) != str(merged.get(field) or ''):
            merged[field] = str(value)
            filled.append(field)
    # Link what EmulationStation shows, where it's empty or points at a missing file
    for xml_field, media_path in scanner.media_index(system).suggest_links(stem).items():
        current = merged.get(xml_field)
        if not current or not (Path(MEDIA_BASE) / current).is_file():
            merged[xml_field] = media_path
    if not game.has_metadata and not merged.get('name'):
        merged['name'] = folder_game_name(system, rom_path) or stem
    merged['path'] = f"./{rom_path}"
    new_game = Game.from_dict(_saveable_fields(merged))
    ok = gamelist_mgr.update_game(system, rom_path, new_game, ROMS_BASE) if game.has_metadata else gamelist_mgr.save_game(system, new_game, ROMS_BASE)
    if not ok:
        return jsonify(success=False, error="Couldn't write gamelist.xml", downloaded=downloaded, errors=errors)

    key = _key(system, rom_path)
    for source, match in (data.get("remember") or {}).items():
        if source in FILL_SOURCES and match and match.get('id') and match.get('confidence') in ('exact', 'likely', 'chosen'):
            match_memory.remember(key, source, match['id'], match.get('name'), match['confidence'])
    return jsonify(success=True, downloaded=downloaded, replaced=replaced, filled=filled, errors=errors,
                   kept=str(kept_at.relative_to(DATA_DIR)) if replaced else None)
