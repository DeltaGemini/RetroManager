"""
The pages themselves: the library, Bookcase, Timeline and Add games, and the files they load.
"""

import os
import re

from flask import jsonify, redirect, request, send_from_directory
import mimetypes
from backend.systems import _PRIMARY, normalize_system_name
from backend.core import app, FRONTEND_DIR, settings
from backend.routes.importing import importer

# The systems' pictures are asked for as /imgs/<folder>.jpg. RetroManager has a
# tile of its own for every system in frontend/tiles/ (drawn by
# tools/make_system_tiles.py: shapes and the system's name, nobody's logo or
# art), and that is what's served unless the other kind is chosen: the pictures
# in frontend/imgs/, from an EmulationStation theme (CC BY-NC-SA, see
# frontend/imgs/README.md), which a copy of RetroManager may not have at all.
# Which is the "System pictures" setting; a browser can ask for either with
# ?drawn=1 or ?theme=1 (the Console's settings), and a system with no picture
# in imgs/ gets its tile whatever is asked. SYSTEM_TILES=1 allows only tiles.
SYSTEM_TILES = any(os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on") for name in ("SYSTEM_TILES", "OPEN_ARTWORK"))
# The other pictures that aren't ours to pass on, and what stands in for each
# in the same way (frontend/open/, and the app's own icon): the header's logo in
# the Switch themes, lettered in a Sega logo font, those themes' background (a
# photograph whose source isn't recorded), and an old tab icon.
OPEN_ARTWORK = {
    'themes/switch/retromanager-logo.svg': 'open/retromanager-logo.svg',
    'themes/switch/background.jpg': 'open/background.svg',
    'imgs/favicon.png': 'icons/icon-512.png',
}


def _open_artwork(path):
    """The stand-in to serve for a path, if it has one and it's wanted: the
    picture itself isn't there, or stand-ins are asked for throughout."""
    stand_in = OPEN_ARTWORK.get(path)
    if stand_in and (SYSTEM_TILES or not (FRONTEND_DIR / path).is_file()) and (FRONTEND_DIR / stand_in).is_file():
        return stand_in
    return None
_SYSTEM_PICTURE = re.compile(r'^imgs/([^/.][^/]*)\.jpg$')
_TILE_NAME = re.compile(r'^[a-z0-9][a-z0-9_.+-]*$')


def _system_tile(name):
    """The drawn tile for a system folder: its own, or the one for the system
    the folder's name is another name for, or the plain one. None for a name
    that couldn't be a folder's."""
    name = name.lower()
    if not _TILE_NAME.match(name):
        return None
    tiles = FRONTEND_DIR / 'tiles'
    for candidate in (name, _PRIMARY.get(normalize_system_name(name)), '_default'):
        if candidate and (tiles / f'{candidate}.svg').is_file():
            return tiles / f'{candidate}.svg'
    return None


def _wanted_pictures():
    """'drawn' or 'theme' for this request: what it asks for, else the setting."""
    if SYSTEM_TILES or request.args.get('drawn'):
        return 'drawn'
    return 'theme' if request.args.get('theme') or settings.get('system_pictures') == 'theme' else 'drawn'


@app.route("/api/system-pictures", methods=["GET"])
def system_pictures():
    """{default: 'drawn' | 'theme', theme: whether the theme's pictures are
    installed (and allowed), credit}: for the Console's settings."""
    installed = not SYSTEM_TILES and any(_SYSTEM_PICTURE.match(f'imgs/{f.name}') and not f.name.startswith('auto-')
                                         for f in (FRONTEND_DIR / 'imgs').glob('*.jpg'))
    return jsonify(success=True, default='theme' if installed and settings.get('system_pictures') == 'theme' else 'drawn', theme=installed,
                   credit="From Lilbud's Switch theme for EmulationStation, based on Grila's for LaunchBox. CC BY-NC-SA.")


# Serve favicon.ico from the frontend directory
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(FRONTEND_DIR, 'favicon.ico')


# -----------------------------------------------------------------------------
# Frontend (SPA)
# -----------------------------------------------------------------------------
@app.route("/shelf")
def serve_shelf():
    shelf_path = FRONTEND_DIR / "shelf.html"
    if shelf_path.exists():
        return send_from_directory(FRONTEND_DIR, "shelf.html")
    return "shelf.html not found", 404


@app.route("/console")
def serve_console():
    if _first_run():
        return redirect("/setup")
    return send_from_directory(FRONTEND_DIR, "console.html")


@app.route("/setup")
def serve_setup():
    return send_from_directory(FRONTEND_DIR, "setup.html")


def _first_run():
    """Whether this is a new copy that hasn't been through its first steps (routes/setup.py)."""
    from backend.routes.setup import needed
    return needed()


@app.route("/import")
def serve_import():
    return send_from_directory(FRONTEND_DIR, "import.html")


@app.route("/share", methods=["POST"])
def receive_share():
    """Files shared to RetroManager from another app (the phone's share menu, once
    RetroManager is installed as an app). They're staged, then the import wizard opens."""
    count = 0
    for upload in request.files.getlist("roms"):
        if upload and upload.filename:
            importer.save_whole(upload.filename, upload.stream)
            count += 1
    return redirect(f"/import?shared={count}", code=303)


@app.route("/timeline")
def serve_timeline():
    return send_from_directory(FRONTEND_DIR, "timeline.html")


@app.route("/login")
def serve_login():
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/play")
def serve_play():
    return send_from_directory(FRONTEND_DIR, "play.html")


@app.route("/stats")
def serve_stats():
    return send_from_directory(FRONTEND_DIR, "stats.html")


@app.route("/")
def serve_frontend_root():
    if _first_run():
        return redirect("/setup")
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        with open(index_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return "index.html not found", 404


@app.route("/<path:path>")
def serve_frontend(path):
    # Block API routes - they should be handled by API endpoints
    if path.startswith("api/"):
        return jsonify({"error": "Not Found"}), 404
    
    # A system's picture: its drawn tile, unless the theme's is wanted and there is one
    picture = _SYSTEM_PICTURE.match(path)
    if picture and (_wanted_pictures() == 'drawn' or not (FRONTEND_DIR / path).is_file()):
        tile = _system_tile(picture.group(1))
        if tile:
            return tile.read_bytes(), 200, {'Content-Type': 'image/svg+xml', 'Cache-Control': 'no-cache'}

    path = _open_artwork(path) or path
    file_path = FRONTEND_DIR / path
    
    # Security: prevent directory traversal
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
            return "Forbidden", 403
    except:
        return "Forbidden", 403
    
    # If it's a file that exists, serve it
    if file_path.exists() and file_path.is_file():
        with open(file_path, 'rb') as f:
            content = f.read()
        mime_type, _ = mimetypes.guess_type(str(file_path))
        return content, 200, {'Content-Type': mime_type or 'application/octet-stream'}
    
    # Otherwise serve index.html for SPA routing
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        with open(index_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return "index.html not found", 404
