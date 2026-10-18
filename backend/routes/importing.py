"""
Adding games: uploads, the inbox, and filing them into roms/.
"""

from flask import jsonify, request
from pathlib import Path
from backend.scanner import DISC_TAG_RE
from backend.models import Game
from backend.name_style import style_name
from backend.importer import Importer, md5_of
from backend.scraper import ScreenscraperError
from backend.media_index import strip_dot_slash
from backend.media_index import title_key
from backend.core import (
    _request_json,
    _rom_system_folders,
    _system_path_or_none,
    app,
    bulk_matcher,
    DATA_DIR,
    gamelist_mgr,
    INBOX_BASE,
    logger,
    ROMS_BASE,
    scanner,
)
from backend.routes.fill import FILL_MEDIA, fill_from_match

# -----------------------------------------------------------------------------
# Adding games: uploads, the inbox, and filing them into roms/
# -----------------------------------------------------------------------------
importer = Importer(ROMS_BASE, INBOX_BASE, _rom_system_folders, DATA_DIR)


@app.route("/api/uploads", methods=["POST"])
def start_upload():
    """Body: {name, size, key}. Starts an upload, or finds the one with the same key
    (so an interrupted upload resumes). Returns {id, received, complete}."""
    data = _request_json()
    try:
        size = int(data.get("size"))
    except (TypeError, ValueError):
        return jsonify(success=False, error="Missing size"), 400
    if not data.get("name"):
        return jsonify(success=False, error="Missing name"), 400
    return jsonify(success=True, **importer.start_upload(data["name"], size, str(data.get("key") or "")))


@app.route("/api/uploads/<upload_id>", methods=["GET"])
def upload_status(upload_id):
    status = importer.upload_status(upload_id)
    if not status:
        return jsonify(success=False, error="Unknown upload"), 404
    return jsonify(success=True, **status)


@app.route("/api/uploads/<upload_id>", methods=["PUT"])
def upload_chunk(upload_id):
    """?offset=<byte>; the body is the raw chunk."""
    try:
        offset = int(request.args.get("offset", "0"))
        status = importer.write_chunk(upload_id, offset, request.stream, request.content_length or 0)
        return jsonify(success=True, **status)
    except KeyError:
        return jsonify(success=False, error="Unknown upload"), 404
    except ValueError as e:
        current = importer.upload_status(upload_id) or {}
        return jsonify(success=False, error=str(e), received=current.get("received", 0)), 409
    except OSError as e:
        logger.exception("Upload failed")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/uploads/<upload_id>", methods=["DELETE"])
def discard_upload(upload_id):
    return jsonify(success=importer.discard_upload(upload_id))


@app.route("/api/import/pending", methods=["GET"])
def import_pending():
    """Uploads (finished or not) and inbox files waiting to be added."""
    uploads = [{'ref': f"upload:{u['id']}", **u} for u in importer.uploads()]
    return jsonify(success=True, uploads=uploads, inbox=importer.inbox_files(),
                   inbox_available=importer.inbox_available(), inbox_path=INBOX_BASE)


def _import_games(refs):
    files = [f for f in (importer.resolve(r) for r in refs or []) if f]
    return importer.group(files)


def _suggest_name(game):
    base = game.get('base') or Path(game['main']['name']).stem
    return style_name(DISC_TAG_RE.sub('', base).strip()) or base


def _identify_file(game):
    """The file ScreenScraper knows the game by: a .cue's first track, disc 1..."""
    main = game['main']
    if Path(main['name']).suffix.lower() == '.cue' and len(game['files']) > 1:
        return game['files'][1]
    return main


def _library_matches(system, names, file_name):
    """Games already in the library that look like this one (by any of `names`,
    or the file name)."""
    keys = {title_key(style_name(n or '')) for n in names}
    keys |= {title_key(Path(file_name).stem), title_key(style_name(Path(file_name).stem))}
    keys.discard('')
    found = []
    try:
        for g in scanner.get_games_for_system(system):
            if title_key(style_name(g.name or '')) in keys or title_key(Path(g.path).stem) in keys:
                found.append({'name': (g.name or '').strip(), 'path': strip_dot_slash(g.path)})
    except Exception:
        pass
    return found[:3]


def _target_path(system, game):
    main = game['main']
    name = f"{DISC_TAG_RE.sub('', game['base']).strip()}.m3u" if game.get('discs') else main['name']
    return Path(ROMS_BASE) / system / name


@app.route("/api/import/analyze", methods=["POST"])
def import_analyze():
    """Body: {refs: [...]}. Groups the files into games and suggests a system and name."""
    games = []
    folders = {s.name: s.get_full_name() for s in scanner.discover_systems()}
    for game in _import_games(_request_json().get("refs")):
        guess = importer.systems_for(game)
        games.append({
            'refs': [f['ref'] for f in game['files']],
            'files': [{'ref': f['ref'], 'name': f['name'], 'size': f['size']} for f in game['files']],
            'main': game['main']['name'],
            'discs': [d['name'] for d in game['discs']] if game.get('discs') else None,
            'missing': game['missing'],
            'size': sum(f['size'] for f in game['files']),
            'systems': [{'system': s, 'full_name': folders.get(s, s)} for s in guess['systems']],
            'reason': guess['reason'],
            'name': _suggest_name(game),
        })
    return jsonify(success=True, games=games,
                   all_systems=[{'system': k, 'full_name': v} for k, v in sorted(folders.items(), key=lambda kv: kv[1].lower())])


@app.route("/api/import/identify", methods=["POST"])
def import_identify():
    """Body: {refs, system, query?}. ScreenScraper's best match (by file name, size and
    checksum, or a title search with `query`), games already in the library that look
    the same, and whether a file of that name is already there."""
    data = _request_json()
    system = data.get("system")
    if not _system_path_or_none(system):
        return jsonify(success=False, error="Pick a system"), 400
    games = _import_games(data.get("refs"))
    if len(games) != 1:
        return jsonify(success=False, error="These files aren't one game"), 400
    game = games[0]
    query = (data.get("query") or "").strip() or None
    ident = _identify_file(game)
    try:
        result = bulk_matcher.match(system, ident['name'], ident['path'], query,
                                    md5=None if query else md5_of(ident['path']))
    except ScreenscraperError as e:
        return jsonify(success=False, error=str(e), fatal=True)
    except Exception as e:
        logger.exception("Error identifying upload")
        return jsonify(success=False, error=str(e)), 500
    target = _target_path(system, game)
    best = next((a for a in result.get('alternatives', []) if str(a.get('id')) == str(result.get('match_id'))), None)
    names = [data.get("name") or _suggest_name(game)] + ([best['nom']] if best and result.get('confidence') in ('exact', 'likely') else [])
    return jsonify(success=True, **result,
                   in_library=_library_matches(system, names, game['main']['name']),
                   file_exists=target.exists(), target=f"{system}/{target.name}")


@app.route("/api/import/commit", methods=["POST"])
def import_commit():
    """Body: {refs, system, name, game_id?, media: [folders]}. Moves the files into
    roms/<system>/ (with an .m3u for several discs), adds the gamelist entry, and
    fills it from ScreenScraper when a game is picked."""
    data = _request_json()
    system = data.get("system")
    system_path = _system_path_or_none(system)
    if not system_path:
        return jsonify(success=False, error="Pick a system"), 400
    games = _import_games(data.get("refs"))
    if len(games) != 1:
        return jsonify(success=False, error="These files aren't one game (or they've been added already)"), 400
    game = games[0]
    targets = [(f, Path(system_path) / f['name']) for f in game['files']]
    main_target = _target_path(system, game)
    clashes = [t.name for _, t in targets if t.exists()] + ([main_target.name] if game.get('discs') and main_target.exists() else [])
    if clashes:
        return jsonify(success=False, error=f"Already in {system}: {', '.join(clashes)}"), 409
    try:
        for f, target in targets:
            importer.move_into(f, target)
        if game.get('discs'):
            main_target.write_text('\n'.join(d['name'] for d in game['discs']) + '\n', encoding='utf-8')
        rom_path = main_target.relative_to(system_path).as_posix()
        # A name you typed is kept; otherwise the entry takes ScreenScraper's name
        # (in house style), or failing that one made from the file name
        typed = (data.get("name") or "").strip()
        result = {'success': True, 'system': system, 'rom_path': rom_path, 'filled': [], 'downloaded': [], 'errors': []}
        if typed or not data.get("game_id"):
            entry = Game.from_filename(rom_path)
            entry.name = typed or _suggest_name(game)
            gamelist_mgr.add_entries(system, ROMS_BASE, [entry])
        if data.get("game_id"):
            media = [m for m in (data.get("media") or []) if m in FILL_MEDIA]
            try:
                # (as Fill the gaps would: the game picked, then the other sources in its order)
                applied, _ = fill_from_match(system, rom_path, data["game_id"], media, keep_name=bool(typed))
                result.update({k: applied.get(k, []) or [] for k in ('filled', 'downloaded', 'errors')})
                if not applied.get('success'):
                    result['errors'].append(applied.get('error') or 'Scraping failed')
            except Exception as e:
                logger.warning(f"Adding {system}/{rom_path}: scraping failed: {e}")
                result['errors'].append(f"Added, but scraping failed: {e}")
            added = scanner.get_game_details(system, rom_path)
            if not typed and not (added and added.has_metadata):
                entry = Game.from_filename(rom_path)
                entry.name = _suggest_name(game)
                gamelist_mgr.add_entries(system, ROMS_BASE, [entry])
        return jsonify(**result)
    except OSError as e:
        logger.exception("Error adding game")
        return jsonify(success=False, error=str(e)), 500
