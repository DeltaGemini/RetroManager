"""
Stats, the Bookcase and Timeline data, the missing-media report and scaled-down pictures.
"""

from flask import jsonify, request, send_from_directory, send_file
import os
from pathlib import Path
import time
from backend.systems import browser_playable, phone_players
from backend.core import _shelf_cache, _stats_cache, app, logger, MEDIA_BASE, media_sources, scanner
from backend.media_sources import MADE

# Stats for the Homepage widget and the header. Walking every system is slow on
# the NAS, so results are cached until something changes (any non-GET API call)
# or STATS_MAX_AGE passes (for changes made outside RetroManager).
STATS_MAX_AGE = 600


@app.after_request
def _invalidate_stats_on_change(response):
    if request.method != "GET" and request.path.startswith("/api/") and not request.path.startswith(
            ("/api/scraper/search", "/api/scraper/game-info", "/api/igdb/search", "/api/igdb/game-info")):
        _stats_cache["value"] = None
        _shelf_cache["value"] = None
        _viewer_cache["value"] = None
    return response


def _compute_stats():
    systems_with_roms = total_games = games_missing_metadata = 0
    for system in scanner.discover_systems():
        try:
            games = scanner.get_games_for_system(system.name)
        except Exception as e:
            logger.warning(f"Error getting games for system {system.name}: {e}")
            continue
        if games:
            systems_with_roms += 1
            total_games += len(games)
            games_missing_metadata += sum(1 for g in games if not g.has_metadata)
    return {
        "systems_with_roms": systems_with_roms,
        "total_games": total_games,
        "games_missing_metadata": games_missing_metadata,
    }


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """{systems_with_roms, total_games, games_missing_metadata}. Add ?refresh=1 to skip the cache."""
    try:
        fresh = request.args.get("refresh") == "1"
        if fresh or _stats_cache["value"] is None or time.time() - _stats_cache["time"] > STATS_MAX_AGE:
            _stats_cache["value"] = _compute_stats()
            _stats_cache["time"] = time.time()
        return jsonify(**_stats_cache["value"])
    except Exception as e:
        logger.exception("Error fetching stats")
        return jsonify(error=str(e)), 500
SHELF_FIELDS = ('path', 'name', 'genre', 'developer', 'publisher', 'players', 'rating', 'favorite',
                'has_metadata', 'rom_exists', 'box2d', 'box3d', 'boxside', 'wheel', 'posters', 'images', 'mix', 'mix_generated', 'manuals')
# Pictures the Bookcase shows; each gets a version (its file's change time) so
# the browser can keep the scaled copy for a long time and still see new art
SHELF_PICTURES = ('box2d', 'box3d', 'boxside', 'posters', 'images', 'mix')
_cover_ratios = {}   # (path, mtime) -> width / height, so each image is read once


def _cover_ratio(media_path, mtime):
    """A cover's width/height, from the image header (no full decode)."""
    key = (media_path, mtime)
    if key not in _cover_ratios:
        try:
            from PIL import Image
            with Image.open(Path(MEDIA_BASE) / media_path) as img:
                w, h = img.size
            _cover_ratios[key] = round(w / h, 4) if w and h else None
        except Exception:
            _cover_ratios[key] = None
    return _cover_ratios[key]


def _compute_shelf():
    shelves = []
    for system in scanner.discover_systems():
        try:
            games = scanner.get_games_for_system(system.name)
        except Exception as e:
            logger.warning(f"Shelf: skipping {system.name}: {e}")
            continue
        if not games:
            continue
        items = []
        for g in games:
            d = g.to_dict()
            item = {k: d.get(k) for k in SHELF_FIELDS}
            item['year'] = (d.get('releasedate') or '')[:4] or None
            item['playable'] = bool(d.get('rom_exists')) and browser_playable(system.name, d.get('path') or '')
            item['phone_playable'] = bool(d.get('rom_exists')) and bool(phone_players(system.name))
            item['v'] = {}
            for field in SHELF_PICTURES:
                if item.get(field):
                    try:
                        item['v'][field] = int((Path(MEDIA_BASE) / item[field]).stat().st_mtime)
                    except OSError:
                        pass
            # The Bookcase widens a hovered box to its cover's shape; knowing it
            # up front stops the box snapping to size once the picture loads
            if item.get('box2d') and 'box2d' in item['v']:
                item['box2d_ratio'] = _cover_ratio(item['box2d'], item['v']['box2d'])
            desc = d.get('desc') or ''
            item['desc'] = desc[:400] + ('…' if len(desc) > 400 else '')
            items.append(item)
        shelves.append({'system': system.name, 'full_name': system.get_full_name(), 'games': items})
    return shelves


@app.route("/api/shelf", methods=["GET"])
def get_shelf():
    """Every system's games with what the Shelf page draws. Cached like /api/stats."""
    try:
        if _shelf_cache["value"] is None or time.time() - _shelf_cache["time"] > STATS_MAX_AGE:
            _shelf_cache["value"] = _compute_shelf()
            _shelf_cache["time"] = time.time()
        return jsonify(success=True, shelves=_shelf_cache["value"])
    except Exception as e:
        logger.exception("Error building shelf")
        return jsonify(success=False, error=str(e)), 500
REPORT_MEDIA_FOLDERS = ('box2d', 'box3d', 'boxside', 'support', 'screenshot', 'screenshottitle', 'wheel',
                        'fanart', 'mix', 'manuals', 'videos')


@app.route("/api/missing-media", methods=["GET"])
def missing_media_report():
    """Without ?system: per system, how many games lack each media type.
    With ?system=snes: each game and which media it has."""
    only = request.args.get("system")
    try:
        made = media_sources.paths_from(MADE)
        systems = []
        for system in scanner.discover_systems():
            if only and system.name != only:
                continue
            games = [g for g in scanner.get_games_for_system(system.name) if g.rom_exists]
            entry = {'system': system.name, 'full_name': system.get_full_name(), 'total': len(games),
                     'missing': {f: sum(1 for g in games if not getattr(g, f, None)) for f in REPORT_MEDIA_FOLDERS},
                     # Mix pictures RetroManager generated, and 3D boxes and spines it made, which it can make again
                     'mix_generated': sum(1 for g in games if g.mix_generated),
                     'made': {f: sum(1 for g in games if getattr(g, f, None) in made) for f in ('box3d', 'boxside')}}
            if only:
                entry['games'] = [{'path': g.path, 'name': g.name, 'has_metadata': g.has_metadata,
                                   'media': {f: getattr(g, f, None) for f in REPORT_MEDIA_FOLDERS}}
                                  for g in sorted(games, key=lambda g: (g.name or '').lower())]
            if games:
                systems.append(entry)
        systems.sort(key=lambda s: s['full_name'].lower())
        return jsonify(success=True, folders=REPORT_MEDIA_FOLDERS, systems=systems)
    except Exception as e:
        logger.exception("Error building missing media report")
        return jsonify(success=False, error=str(e)), 500
# The kinds of media the Media viewer shows (manuals and videos as a tile saying there's one)
VIEWER_MEDIA_FOLDERS = ('box2d', 'box3d', 'boxside', 'support', 'screenshot', 'screenshottitle', 'wheel',
                        'fanart', 'mix', 'manuals', 'videos')
# Every game with all those pictures, kept like the Shelf's (walking every
# system's folders takes a while on a NAS), so changing kind is quick
_viewer_cache = {"value": None, "time": 0}


def _compute_viewer():
    games = []
    made = media_sources.paths_from(MADE)
    for system in scanner.discover_systems():
        for g in scanner.get_games_for_system(system.name):
            if g.rom_exists:
                games.append({'system': system.name, 'system_name': system.get_full_name(), 'path': g.path,
                              'name': g.name, 'has_metadata': g.has_metadata,
                              'pictures': {f: getattr(g, f, None) or None for f in VIEWER_MEDIA_FOLDERS},
                              # (the kinds of picture RetroManager made for it: a 3D box, a spine)
                              'made': [f for f in ('box3d', 'boxside') if getattr(g, f, None) in made]})
    games.sort(key=lambda g: ((g['name'] or '').lower(), g['system_name'].lower()))
    return games


@app.route("/api/media-viewer", methods=["GET"])
def media_viewer():
    """Every game of every system with its picture of one kind (?folder=box2d),
    or none. The files aren't checked (on a NAS that takes a while for a big
    library): the page shows the game's name where one won't load."""
    folder = request.args.get("folder", "box2d")
    if folder not in VIEWER_MEDIA_FOLDERS:
        return jsonify(success=False, error="Unknown kind of picture"), 400
    try:
        if _viewer_cache["value"] is None or time.time() - _viewer_cache["time"] > STATS_MAX_AGE:
            _viewer_cache["value"] = _compute_viewer()
            _viewer_cache["time"] = time.time()
        games = [{**{k: v for k, v in g.items() if k != 'pictures'}, 'picture': g['pictures'][folder]}
                 for g in _viewer_cache["value"]]
        return jsonify(success=True, folder=folder, folders=VIEWER_MEDIA_FOLDERS, games=games)
    except Exception as e:
        logger.exception("Error listing media for the viewer")
        return jsonify(success=False, error=str(e)), 500


# Small versions of media for the shelf, made once and kept in THUMB_DIR
THUMB_DIR = Path(os.environ.get("THUMB_DIR", "/tmp/retromanager-thumbs"))
THUMB_HEIGHTS = {160, 320, 480}


@app.route("/api/thumb/<int:height>/<path:media_path>", methods=["GET"])
def get_thumbnail(height, media_path):
    """A media image scaled to `height` px, as WebP. ?spine=1 turns landscape
    spine images upright (title reading top to bottom)."""
    if height not in THUMB_HEIGHTS:
        return jsonify(error="Unsupported size"), 400
    source = (Path(MEDIA_BASE) / media_path).resolve()
    if not str(source).startswith(str(Path(MEDIA_BASE).resolve()) + os.sep) or not source.is_file():
        return jsonify(error="Not found"), 404
    spine = request.args.get("spine") == "1"
    stat = source.stat()
    import hashlib
    key = hashlib.sha1(f"{source}|{stat.st_mtime_ns}|{stat.st_size}|{height}|{spine}".encode()).hexdigest()
    cached = THUMB_DIR / key[:2] / f"{key}.webp"
    if not cached.is_file():
        try:
            from PIL import Image
            with Image.open(source) as img:
                img.load()
                if spine and img.width > img.height:
                    img = img.rotate(-90, expand=True)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                if img.height > height:
                    img = img.resize((max(1, round(img.width * height / img.height)), height), Image.LANCZOS)
                cached.parent.mkdir(parents=True, exist_ok=True)
                tmp = cached.with_suffix(".part")
                img.save(tmp, "WEBP", quality=82, method=4)
                os.replace(tmp, cached)
        except Exception as e:
            logger.warning(f"Thumbnail failed for {media_path}: {e}")
            return send_from_directory(source.parent, source.name)
    # With ?v= (the source's version) the address changes whenever the picture
    # does, so browsers may keep it for a year
    max_age = 31536000 if request.args.get("v") else 86400
    response = send_file(cached, mimetype="image/webp", max_age=max_age)
    if request.args.get("v"):
        response.headers["Cache-Control"] = f"public, max-age={max_age}, immutable"
    return response
