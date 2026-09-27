"""
RetroManager Backend API
Flask application providing REST API for EmulationStation metadata management
"""

from flask import Flask, jsonify, redirect, request, send_from_directory, send_file
from datetime import datetime
import shutil
from flask_cors import CORS
import os
import logging
from pathlib import Path
from io import BytesIO
import mimetypes
mimetypes.add_type('application/manifest+json', '.webmanifest')
import time
from urllib.parse import urlparse
import re
import requests
from lxml import etree

from backend.scanner import DISC_TAG_RE, SystemScanner
from backend.gamelist_manager import GamelistManager
from backend.models import System, Game
from backend.name_style import style_name
from backend.scrape_queue import ScrapeQueue
from backend.importer import Importer, md5_of
from backend.folder_games import folder_game_name, game_folder, is_folder_game_system, launch_candidates
from backend.scraper import ScreenscraperAPI, ScreenscraperError
from backend.igdb_scraper import IGDBAPI, IGDBError
from backend.systems import screenscraper_system_id
from backend.media_index import ORPHANED_FOLDER, strip_dot_slash
from backend.saves import SaveFinder
from backend.bulk_scrape import BulkMatcher, JeuCache
from backend.media_index import title_key
import threading
import zipfile

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

ROMS_BASE = os.environ.get("ROMS_PATH", "/roms")
MEDIA_BASE = os.environ.get("MEDIA_PATH", "/media")

# In-game saves and save states (mounted read-only; viewed, never changed)
SAVES_BASE = os.environ.get("SAVES_PATH", "/saves")
SAVESTATES_BASE = os.environ.get("SAVESTATES_PATH", "/savestates")
# Per-person folders inside them
INBOX_BASE = os.environ.get("INBOX_PATH", "/inbox")


def _data_dir():
    """RetroManager's own files (library-scrape memory, moved duplicates): DATA_PATH,
    kept out of the ROM folders so they don't sync to other devices. Falls back to
    ROMS_PATH/.retromanager when DATA_PATH isn't mounted."""
    configured = Path(os.environ.get("DATA_PATH", "/data"))
    try:
        if configured.is_dir() and os.access(configured, os.W_OK):
            return configured
    except OSError:
        pass
    return Path(os.environ.get("ROMS_PATH", "/roms")) / ".retromanager"


DATA_DIR = _data_dir()
SAVE_BACKUP_BASE = Path(os.environ.get("SAVE_BACKUP_PATH", "/save-backups"))
SAVE_PROFILES = [p.strip() for p in os.environ.get("SAVE_PROFILES", "").split(",") if p.strip()]

# ScreenScraper developer credentials (request your own at screenscraper.fr)
SCREENSCRAPER_LOGIN = os.environ.get("SCREENSCRAPER_LOGIN", "")
SCREENSCRAPER_PASSWORD = os.environ.get("SCREENSCRAPER_PASSWORD", "")
SCREENSCRAPER_DEBUG_PASSWORD = os.environ.get("SCREENSCRAPER_DEBUG_PASSWORD", "")
# Optional user account: bigger quota, and still works when the API is closed to non-members
SCREENSCRAPER_USER = os.environ.get("SCREENSCRAPER_USER", "")
SCREENSCRAPER_USER_PASSWORD = os.environ.get("SCREENSCRAPER_USER_PASSWORD", "")

# IGDB API credentials (a Twitch application: dev.twitch.tv/console)
IGDB_CLIENT_ID = os.environ.get("IGDB_CLIENT_ID", "")
IGDB_CLIENT_SECRET = os.environ.get("IGDB_CLIENT_SECRET", "")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


app = Flask(__name__)
CORS(app)

# The app icon (browser tab, header, installed app) is drawn here rather than
# kept as image files
_ICON_CACHE = {}


def _app_icon_png(size):
    if size not in _ICON_CACHE:
        from io import BytesIO
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (size, size), (15, 21, 53))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default(size=int(size * 0.38))
        except TypeError:   # Pillow without scalable default font
            font = ImageFont.load_default()
        left, top, right, bottom = draw.textbbox((0, 0), 'RM', font=font)
        draw.text(((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top), 'RM',
                  font=font, fill=(255, 110, 199))
        buf = BytesIO()
        img.save(buf, 'PNG')
        _ICON_CACHE[size] = buf.getvalue()
    return _ICON_CACHE[size]


@app.route('/favicon.ico')
def favicon():
    return _app_icon_png(64), 200, {'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400'}


@app.route('/icons/icon-<int:size>.png')
def app_icon(size):
    if size not in (192, 512):
        return jsonify({"error": "Not Found"}), 404
    return _app_icon_png(size), 200, {'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400'}

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

scanner = SystemScanner(ROMS_BASE, MEDIA_BASE)
gamelist_mgr = GamelistManager(MEDIA_BASE)
scraper = ScreenscraperAPI(SCREENSCRAPER_LOGIN, SCREENSCRAPER_PASSWORD, SCREENSCRAPER_DEBUG_PASSWORD,
                           SCREENSCRAPER_USER, SCREENSCRAPER_USER_PASSWORD)
igdb_scraper = IGDBAPI(IGDB_CLIENT_ID, IGDB_CLIENT_SECRET)


def _rom_system_folders():
    try:
        return {p.name for p in Path(ROMS_BASE).iterdir() if p.is_dir()}
    except OSError:
        return set()


jeu_cache = JeuCache()
bulk_matcher = BulkMatcher(scraper, jeu_cache)
save_finder = SaveFinder({"saves": SAVES_BASE, "savestates": SAVESTATES_BASE}, SAVE_PROFILES, _rom_system_folders)

# -----------------------------------------------------------------------------
# Frontend (SPA)
# -----------------------------------------------------------------------------

@app.route("/shelf")
def serve_shelf():
    shelf_path = FRONTEND_DIR / "shelf.html"
    if shelf_path.exists():
        return send_from_directory(FRONTEND_DIR, "shelf.html")
    return "shelf.html not found", 404


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


@app.route("/")
def serve_frontend_root():
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

# -----------------------------------------------------------------------------
# API Routes
# -----------------------------------------------------------------------------

@app.route("/api/systems", methods=["GET"])
def get_systems():
    try:
        systems = scanner.discover_systems()
        return jsonify(success=True, systems=[s.to_dict() for s in systems])
    except Exception as e:
        logger.exception("Error discovering systems")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/scan", methods=["POST"])
def scan_system(system_name):
    try:
        result = scanner.scan_system(system_name)
        return jsonify(success=True, result=result)
    except Exception as e:
        logger.exception("Error scanning system")
        return jsonify(success=False, error=str(e)), 500

# -----------------------------------------------------------------------------
# Scan panel actions. Each gamelist change makes a dated backup first.
# -----------------------------------------------------------------------------

def _system_path_or_none(system_name):
    """The system's ROM folder, or None if the name isn't a real system folder."""
    if not system_name or '/' in system_name or '\\' in system_name or system_name.startswith('.'):
        return None
    path = Path(ROMS_BASE) / system_name
    return path if path.is_dir() else None


def _rom_exists(system_path, rom_path):
    rom_rel = strip_dot_slash(rom_path)
    full = (system_path / rom_rel).resolve()
    return rom_rel and str(full).startswith(str(system_path.resolve()) + os.sep) and full.is_file()


def _bulk_result(changed, backup):
    return jsonify(success=True, changed=changed, backup=backup)


@app.route("/api/systems/<system_name>/relink", methods=["POST"])
def relink_entries(system_name):
    """Body: {pairs: [{from: old rom path, to: existing rom path}]}"""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    pairs = (request.get_json(silent=True) or {}).get("pairs") or []
    mapping = {p["from"]: p["to"] for p in pairs
               if p.get("from") and p.get("to") and _rom_exists(system_path, p["to"])}
    if not mapping:
        return jsonify(success=False, error="No valid pairs to relink"), 400
    try:
        changed, backup = gamelist_mgr.relink_paths(system_name, ROMS_BASE, mapping)
        renamed, errors = _rename_media_for_relink(system_name, mapping)
        return jsonify(success=True, changed=changed, backup=backup, renamed_media=renamed, errors=errors)
    except Exception as e:
        logger.exception("Error relinking entries")
        return jsonify(success=False, error=str(e)), 500


def _rename_media_for_relink(system_name, mapping):
    """Media saved under the old (wrong) ROM name is renamed to the new one, so it
    still matches. Files are never overwritten."""
    index = scanner.media_index(system_name)
    system_media = Path(MEDIA_BASE) / index.media_system
    renamed, errors = 0, []
    for old, new in mapping.items():
        old_stem, new_stem = Path(old).stem, Path(new).stem
        for folder, (by_stem, _, _) in index.folders.items():
            name = by_stem.get(old_stem.lower())
            if not name:
                continue
            source = system_media / folder / name
            target = source.with_name(new_stem + source.suffix)
            if target.exists():
                continue
            try:
                source.rename(target)
                renamed += 1
            except OSError as e:
                errors.append(f"{folder}/{name}: {e}")
    return renamed, errors


@app.route("/api/systems/<system_name>/entries/create", methods=["POST"])
def create_entries(system_name):
    """Body: {rom_paths: [...]}. Adds a basic entry (name from the file name,
    media linked from matching files) for each ROM that has none."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    rom_paths = (request.get_json(silent=True) or {}).get("rom_paths") or []
    index = scanner.media_index(system_name)
    games = []
    for rom_path in rom_paths:
        if not _rom_exists(system_path, rom_path):
            continue
        game = Game.from_filename(strip_dot_slash(rom_path))
        game.name = style_name(folder_game_name(system_name, rom_path) or game.name)
        for field, media_path in index.suggest_links(Path(rom_path).stem).items():
            setattr(game, field, media_path)
        games.append(game)
    if not games:
        return jsonify(success=False, error="No valid ROM paths"), 400
    try:
        return _bulk_result(*gamelist_mgr.add_entries(system_name, ROMS_BASE, games))
    except Exception as e:
        logger.exception("Error creating entries")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/entries/remove", methods=["POST"])
def remove_entries(system_name):
    """Body: {paths: [...]}. Removes gamelist entries only; no files are deleted."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    paths = (request.get_json(silent=True) or {}).get("paths") or []
    if not paths:
        return jsonify(success=False, error="No paths given"), 400
    try:
        return _bulk_result(*gamelist_mgr.remove_entries(system_name, ROMS_BASE, paths))
    except Exception as e:
        logger.exception("Error removing entries")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/library-scan", methods=["GET"])
def library_scan():
    """Scan every system and return how many of each problem it has (the same
    checks as each system's Scan panel), for the Library health page."""
    systems = []
    for system in scanner.discover_systems():
        if not system.rom_count and not system.game_count:
            continue
        try:
            result = scanner.scan_system(system.name)
        except Exception as e:
            logger.warning(f"Library scan: {system.name} failed: {e}")
            systems.append({'system': system.name, 'full_name': system.get_full_name(), 'error': str(e), 'counts': {}})
            continue
        counts = {k: len(v) for k, v in result.items() if isinstance(v, list)}
        systems.append({
            'system': system.name,
            'full_name': system.get_full_name(),
            'rom_count': system.rom_count,
            'counts': counts,
        })
    return jsonify(success=True, systems=systems)


@app.route("/api/systems/<system_name>/names/fix", methods=["POST"])
def fix_truncated_names(system_name):
    """Body: {paths: [...]} (optional; default all). Puts back the first letters
    Skraper cut off names, taken from each ROM's file name."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("paths")
    try:
        # Recompute on the server rather than trusting names from the client
        names = scanner.scan_system(system_name)["truncated_names"]
        if only is not None:
            wanted = {strip_dot_slash(p).lower() for p in only}
            names = [n for n in names if n["path"].lower() in wanted]
        if not names:
            return _bulk_result(0, None)
        return _bulk_result(*gamelist_mgr.set_names(system_name, ROMS_BASE, {n["path"]: n["fixed"] for n in names}))
    except Exception as e:
        logger.exception("Error fixing names")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/names/style", methods=["POST"])
def style_names(system_name):
    """Body: {paths: [...]} (optional; default all). Renames entries to the house
    style ("Star Wars: Rogue Leader - Rogue Squadron II"); see name_style.py."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("paths")
    try:
        names = scanner.scan_system(system_name)["name_style"]
        if only is not None:
            wanted = {strip_dot_slash(p).lower() for p in only}
            names = [n for n in names if n["path"].lower() in wanted]
        if not names:
            return _bulk_result(0, None)
        return _bulk_result(*gamelist_mgr.set_names(system_name, ROMS_BASE, {n["path"]: n["styled"] for n in names}))
    except Exception as e:
        logger.exception("Error styling names")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/disc-tracks/merge", methods=["POST"])
def merge_disc_tracks(system_name):
    """Body: {paths: [...]} (optional; default all). Folds gamelist entries for disc
    tracks into their .cue's entry. No files are touched."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("paths")
    try:
        # Recompute on the server rather than trusting paths from the client
        tracks = scanner.scan_system(system_name)["disc_tracks"]
        if only is not None:
            wanted = {strip_dot_slash(p).lower() for p in only}
            tracks = [t for t in tracks if t["path"].lower() in wanted]
        if not tracks:
            return _bulk_result(0, None)
        return _bulk_result(*gamelist_mgr.merge_disc_parts(system_name, ROMS_BASE, {t["path"]: t["disc"] for t in tracks}))
    except Exception as e:
        logger.exception("Error merging disc track entries")
        return jsonify(success=False, error=str(e)), 500


DUPLICATES_DIR = DATA_DIR / 'duplicates'


@app.route("/api/systems/<system_name>/duplicates/resolve", methods=["POST"])
def resolve_duplicates(system_name):
    """Body: {groups: [{keep: path, remove: [paths]}]}. Moves the removed copies (and
    a .cue's track files) to DATA_PATH/duplicates/<system>/, folds their
    gamelist details into the kept copy's entry, and gives the kept copy any media
    only the removed one had. Nothing is deleted."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    wanted = (request.get_json(silent=True) or {}).get("groups") or []
    try:
        found = {g['id']: g for g in scanner.scan_system(system_name)['duplicates']}
        members = {}
        for g in found.values():
            for c in g['copies']:
                members[c['path'].lower()] = g['id']
        mapping = {}
        for g in wanted:
            keep = strip_dot_slash(g.get('keep', ''))
            group = members.get(keep.lower())
            for rem in g.get('remove') or []:
                rem = strip_dot_slash(rem)
                if group and rem.lower() != keep.lower() and members.get(rem.lower()) == group:
                    mapping[rem] = keep
        if not mapping:
            return jsonify(success=False, error="Nothing to move"), 400

        changed, backup = gamelist_mgr.merge_disc_parts(system_name, ROMS_BASE, mapping)
        renamed, errors = _rename_media_for_relink(system_name, mapping)
        parts = scanner.disc_parts(system_path)
        target_root = DUPLICATES_DIR / system_name
        moved = []
        for rem in mapping:
            files = [rem] + [p for p, owner in parts.items() if owner.lower() == rem.lower()]
            for rel in files:
                source = system_path / rel
                if not source.is_file():
                    # parts are stored lowercase: find the real file name
                    matches = [f for f in source.parent.glob('*') if f.name.lower() == Path(rel).name.lower()]
                    if not matches:
                        continue
                    source = matches[0]
                target = target_root / source.relative_to(system_path)
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
                    moved.append(source.relative_to(system_path).as_posix())
                except OSError as e:
                    errors.append(f"{rel}: {e}")
        try:
            with open(DUPLICATES_DIR / 'moved.log', 'a', encoding='utf-8') as log:
                for rel in moved:
                    log.write(f"{datetime.now().isoformat(timespec='seconds')}\t{system_name}\t{rel}\n")
        except OSError:
            pass
        return jsonify(success=True, changed=len(mapping), backup=backup, moved=moved,
                       renamed_media=renamed, errors=errors,
                       moved_to=str(DUPLICATES_DIR / system_name))
    except Exception as e:
        logger.exception("Error resolving duplicates")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/saves-in-roms/move", methods=["POST"])
def move_saves_out_of_roms(system_name):
    """Body: {paths?: [...]} (default all). Saves and save states belong only in the
    top-level saves/ and savestates/ folders; ones found in a ROM folder move to
    SAVE_BACKUP_PATH/in-rom-folders/<time>/<system>/ (kept, not deleted)."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    if not _backup_folder_ok():
        return jsonify(success=False, error=f"Can't write to {SAVE_BACKUP_BASE}"), 400
    only = (request.get_json(silent=True) or {}).get("paths")
    found = scanner.saves_in_roms(Path(system_path))
    if only is not None:
        wanted = {strip_dot_slash(p).lower() for p in only}
        found = [f for f in found if f.lower() in wanted]
    target_root = SAVE_BACKUP_BASE / 'in-rom-folders' / datetime.now().strftime('%Y%m%d_%H%M%S') / system_name
    moved, errors = [], []
    for rel in found:
        try:
            target = target_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(Path(system_path) / rel), str(target))
            moved.append(rel)
        except OSError as e:
            errors.append(f"{rel}: {e}")
    return jsonify(success=True, changed=len(moved), moved=moved, errors=errors,
                   moved_to=str(target_root))


@app.route("/api/systems/<system_name>/multi-disc/create", methods=["POST"])
def create_multi_disc(system_name):
    """Body: {m3us: [paths]} (optional; default all). Writes an .m3u playlist for each
    multi-disc game and makes it the game's one gamelist entry (details from the
    disc entries are kept; disc 1's media is renamed to match)."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("m3us")
    try:
        sets = scanner.scan_system(system_name)['multi_disc']
        if only is not None:
            wanted = {strip_dot_slash(p).lower() for p in only}
            sets = [s for s in sets if s['m3u'].lower() in wanted]
        if not sets:
            return _bulk_result(0, None)
        mapping, names, errors = {}, {}, []
        for disc_set in sets:
            m3u_path = system_path / disc_set['m3u']
            folder = m3u_path.parent
            lines = [(system_path / d).relative_to(folder).as_posix() for d in disc_set['discs']]
            try:
                m3u_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            except OSError as e:
                errors.append(f"{disc_set['m3u']}: {e}")
                continue
            for disc in disc_set['discs']:
                mapping[disc] = disc_set['m3u']
            names[disc_set['m3u']] = DISC_TAG_RE.sub('', disc_set['name']).strip()
        changed, backup = gamelist_mgr.merge_disc_parts(system_name, ROMS_BASE, mapping) if mapping else (0, None)
        # Entries renamed "… (Disc 1)" lose the disc tag; games with no entry get one
        existing = {strip_dot_slash(g.path).lower() for g in scanner.get_games_for_system(system_name) if g.has_metadata}
        new_games, renames = [], {}
        for m3u, name in names.items():
            if m3u.lower() in existing:
                renames[m3u] = name
            else:
                game = Game.from_filename(m3u)
                game.name = style_name(name)
                new_games.append(game)
        if renames:
            gamelist_mgr.set_names(system_name, ROMS_BASE, renames)
        if new_games:
            gamelist_mgr.add_entries(system_name, ROMS_BASE, new_games)
        first_discs = {s['discs'][0]: s['m3u'] for s in sets if s['m3u'] in names}
        renamed, rename_errors = _rename_media_for_relink(system_name, first_discs)
        return jsonify(success=True, changed=len(names), backup=backup, renamed_media=renamed,
                       errors=errors + rename_errors)
    except Exception as e:
        logger.exception("Error creating multi-disc playlists")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/link-media", methods=["POST"])
def link_media(system_name):
    """Body: {paths: [...]} (optional; default all). Fills empty or broken
    <image>/<thumbnail>/<video> from matching media files."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    only = (request.get_json(silent=True) or {}).get("paths")
    try:
        # Recompute on the server rather than trusting paths from the client
        links = scanner.scan_system(system_name)["media_links"]
        if only is not None:
            wanted = {strip_dot_slash(p) for p in only}
            links = [l for l in links if l["path"] in wanted]
        if not links:
            return _bulk_result(0, None)
        updates = {l["path"]: l["fields"] for l in links}
        return _bulk_result(*gamelist_mgr.set_media_fields(system_name, ROMS_BASE, updates))
    except Exception as e:
        logger.exception("Error linking media")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/orphaned-media/move", methods=["POST"])
def move_orphaned_media(system_name):
    """Body: {files: ["<media system>/<folder>/<file>", ...]}. Moves each file to
    <media system>/_orphaned/<folder>/ so it can be restored by hand."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    files = (request.get_json(silent=True) or {}).get("files") or []
    media_system = scanner._resolve_media_system(system_name)
    system_media = (Path(MEDIA_BASE) / media_system).resolve()
    moved, errors = 0, []
    for rel in files:
        parts = rel.replace('\\', '/').split('/')
        if len(parts) != 3 or parts[0] != media_system or parts[1] in ('', '.', '..', ORPHANED_FOLDER):
            errors.append(f"{rel}: not a media file of this system")
            continue
        source = (system_media / parts[1] / parts[2]).resolve()
        if source.parent.parent != system_media or not source.is_file():
            errors.append(f"{rel}: file not found")
            continue
        target_dir = system_media / ORPHANED_FOLDER / parts[1]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        counter = 1
        while target.exists():
            target = target_dir / f"{source.stem}_{counter}{source.suffix}"
            counter += 1
        try:
            shutil.move(str(source), str(target))
            moved += 1
        except OSError as e:
            errors.append(f"{rel}: {e}")
    return jsonify(success=moved > 0 or not errors, changed=moved, errors=errors)



@app.route("/api/systems/<system_name>/games", methods=["GET"])
def get_games(system_name):
    try:
        games = scanner.get_games_for_system(system_name)
        return jsonify(success=True, games=[g.to_dict() for g in games])
    except Exception as e:
        logger.exception("Error getting games")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/games/<path:rom_path>", methods=["GET"])
def get_game(system_name, rom_path):
    try:
        game = scanner.get_game_details(system_name, rom_path)
        if not game:
            return jsonify(success=False, error="Game not found"), 404
        return jsonify(success=True, game=game.to_dict())
    except Exception as e:
        logger.exception("Error getting game")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/games", methods=["POST"])
def create_game(system_name):
    try:
            logger.debug(f"create_game() called for system: {system_name}")
            logger.debug(f"Request content-type: {request.content_type}")
            logger.debug(f"Request form keys: {list(request.form.keys())}")
            logger.debug(f"Request files keys: {list(request.files.keys())}")
            
            # Try JSON first (for existing ROMs already on disk)
            if request.is_json:
                logger.debug("Handling as JSON request")
                game_data = request.get_json()
                logger.debug(f"Received game data: {game_data}")
                
                # Create game from JSON data
                game = Game.from_dict(game_data)
                if gamelist_mgr.save_game(system_name, game, ROMS_BASE):
                    logger.info(f"Successfully saved game via JSON: {game.name}")
                    return jsonify(success=True, game=game.to_dict())
                logger.warning(f"Failed to save game via JSON")
                return jsonify(success=False, error="Failed to save game"), 500
            
            # Otherwise handle as multipart/form-data (for file uploads)
            logger.debug("Handling as multipart/form-data request")
            # Accept multipart/form-data for file uploads and text fields
            form = request.form
            files = request.files
            # Extract fields from form
            name = form.get('name')
            desc = form.get('desc')
            genre = form.get('genre')
            developer = form.get('developer')
            publisher = form.get('publisher')
            releasedate = form.get('releasedate')
            players = form.get('players')
            rating = form.get('rating')
            # Extract files
            rom = files.get('rom')
            wheel = files.get('wheel')
            screenshot = files.get('screenshot')
            screenshottitle = files.get('screenshottitle')
            box2d = files.get('box2d')
            box3d = files.get('box3d')
            fanart = files.get('fanart')
            images = files.get('images')
            posters = files.get('posters')
            manuals = files.get('manuals')
            videos = files.get('videos')
            import os
            from werkzeug.utils import secure_filename
            # Define base paths
            system_roms_dir = os.path.join(ROMS_BASE, system_name)
            system_media_dir = os.path.join(MEDIA_BASE, system_name)
            os.makedirs(system_roms_dir, exist_ok=True)
            os.makedirs(system_media_dir, exist_ok=True)

            # Save ROM file (mandatory)
            rom_path = None
            if not rom:
                logger.warning(f"ROM file is required but not provided for system: {system_name}")
                return jsonify(success=False, error="ROM file is required"), 400
            rom_filename = secure_filename(rom.filename)
            rom_path = os.path.join(system_roms_dir, rom_filename)
            rom.save(rom_path)

            # Helper to save media files
            def save_media(file, subfolder):
                if not file:
                    return None
                folder = os.path.join(system_media_dir, subfolder)
                os.makedirs(folder, exist_ok=True)
                filename = secure_filename(file.filename)
                path = os.path.join(folder, filename)
                file.save(path)
                # Return relative path for gamelist/media reference (relative to MEDIA_BASE)
                return os.path.relpath(path, MEDIA_BASE).replace('\\', '/')

            # Save all media files
            media_paths = {}
            media_types = [
                ('wheel', wheel),
                ('screenshot', screenshot),
                ('screenshottitle', screenshottitle),
                ('box2d', box2d),
                ('box3d', box3d),
                ('fanart', fanart),
                ('images', images),
                ('posters', posters),
                ('manuals', manuals),
                ('videos', videos),
            ]
            for key, file in media_types:
                if file:
                    # Use subfolder per media type
                    media_paths[key] = save_media(file, key)

            # Build a dict for Game.from_dict
            game_dict = {
                'name': name,
                'desc': desc,
                'genre': genre,
                'developer': developer,
                'publisher': publisher,
                'releasedate': releasedate,
                'players': players,
                'rating': rating,
                'path': os.path.relpath(rom_path, ROMS_BASE).replace('\\', '/') if rom_path else '',
            }
            # Only add media paths for image, thumbnail, and video (the three XML fields we use)
            # Do NOT add screenshot, screenshottitle, wheel, box2d, box3d, fanart, images, posters, manuals, videos fields
            # to the game dict - these are only for display/upload, not for XML storage
            for key, file in media_types:
                if file:
                    media_paths[key] = save_media(file, key)
            # Only set image, thumbnail, video in the game dict if they were provided via media upload
            if media_paths.get('box2d'):
                game_dict['image'] = media_paths['box2d']
            if media_paths.get('fanart'):
                game_dict['thumbnail'] = media_paths['fanart']
            if media_paths.get('videos'):
                game_dict['video'] = media_paths['videos']
            game = Game.from_dict(game_dict)
            if gamelist_mgr.save_game(system_name, game, ROMS_BASE):
                return jsonify(success=True, game=game.to_dict())
            return jsonify(success=False, error="Failed to save game"), 500
    except Exception as e:
        logger.exception("Error saving game")
        return jsonify(success=False, error=str(e)), 500


# Fields a save writes to gamelist.xml. Media folder fields (box2d, wheel, ...)
# are display-only; only image, thumbnail and video go in the XML. favorite,
# playcount and lastplayed are passed through so a save doesn't drop them.
SAVEABLE_FIELDS = (
    'path', 'name', 'desc', 'genre', 'developer', 'publisher', 'releasedate',
    'players', 'rating', 'image', 'thumbnail', 'video', 'favorite', 'playcount', 'lastplayed',
)


def _saveable_fields(data):
    return {k: data[k] for k in SAVEABLE_FIELDS if data.get(k) is not None}


@app.route("/api/systems/<system_name>/games/<path:rom_path>", methods=["PUT"])
def update_game(system_name, rom_path):
    try:
        logger.debug(f"Attempting to update game - System: {system_name}, ROM path: {rom_path}")
        logger.debug(f"Request JSON: {request.json}")
        
        # Ensure path and name exist in request
        data = request.json
        if not data.get('path'):
            data['path'] = rom_path
        if not data.get('name'):
            return jsonify(success=False, error="Missing required field: name"), 400
        
        game = Game.from_dict(_saveable_fields(data))
        logger.debug(f"Game object created: {game.name}, path: {game.path}")
        if gamelist_mgr.update_game(system_name, rom_path, game, ROMS_BASE):
            logger.info(f"Successfully updated game: {game.name}")
            return jsonify(success=True, game=game.to_dict())
        logger.warning(f"Failed to update game - gamelist_mgr returned False")
        return jsonify(success=False, error="Failed to update game"), 500
    except Exception as e:
        logger.exception("Error updating game")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/games/preview", methods=["POST"])
def preview_game_xml(system_name):
    """Body: the game as the detail panel would save it. Returns the <game> XML
    a save would write, without writing anything."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    data = request.get_json(silent=True) or {}
    if not data.get("path"):
        return jsonify(success=False, error="Missing path"), 400
    try:
        game = Game.from_dict({**_saveable_fields(data), 'name': data.get('name') or ''})
        xml = gamelist_mgr.preview_entry(system_name, data["path"], game, ROMS_BASE)
        return jsonify(success=True, xml=xml, exists=bool(data.get("has_metadata")))
    except Exception as e:
        logger.exception("Error previewing game XML")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/games/<path:rom_path>", methods=["DELETE"])
def delete_game(system_name, rom_path):
    """Remove a game. By default only the gamelist entry goes.
    ?delete_rom=1 also deletes the ROM file; ?delete_media=1 also deletes its media files."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    delete_rom = request.args.get("delete_rom") == "1"
    delete_media = request.args.get("delete_media") == "1"
    rom_rel = strip_dot_slash(rom_path)

    try:
        removed_entry = gamelist_mgr.delete_game(system_name, rom_rel, ROMS_BASE)
        deleted_files, errors = [], []

        if delete_rom:
            rom_file = (system_path / rom_rel).resolve()
            if str(rom_file).startswith(str(system_path.resolve()) + os.sep) and rom_file.is_file():
                try:
                    rom_file.unlink()
                    deleted_files.append(rom_rel)
                except OSError as e:
                    errors.append(f"{rom_rel}: {e}")

        if delete_media:
            index = scanner.media_index(system_name)
            for media_rel in index.discover(Path(rom_rel).stem, exact=True).values():
                media_file = Path(MEDIA_BASE) / media_rel
                try:
                    media_file.unlink()
                    deleted_files.append(media_rel)
                except OSError as e:
                    errors.append(f"{media_rel}: {e}")

        if not removed_entry and not deleted_files:
            return jsonify(success=False, error="Nothing was deleted: no gamelist entry or files found", errors=errors), 404
        return jsonify(success=True, removed_entry=removed_entry, deleted_files=deleted_files, errors=errors)
    except Exception as e:
        logger.exception("Error deleting game")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/media/<path:media_path>")
def serve_media(media_path):
    try:
        # media_path is URL-decoded by Flask, format: "system_name/media_type/filename"
        # Example: "Game Boy Advance/images/Batman Begins.png"
        parts = media_path.split('/')
        
        if len(parts) < 3:
            logger.warning(f"Invalid media path format: {media_path}")
            return jsonify(error="Invalid media path format"), 400
        
        system_name = parts[0]
        media_type = parts[1]
        filename = '/'.join(parts[2:])  # Handle filenames with slashes
        
        logger.debug(f"Serving media - System: {system_name}, Type: {media_type}, File: {filename}")
        
        # Prevent path traversal on system_name and media_type
        if '..' in system_name or system_name.startswith('/'):
            logger.warning(f"Invalid system name: {system_name}")
            return jsonify(error="Invalid system name"), 400
        
        if '..' in media_type or media_type.startswith('/'):
            logger.warning(f"Invalid media type: {media_type}")
            return jsonify(error="Invalid media type"), 400
        
        # Build the full path
        full_path = Path(MEDIA_BASE) / system_name / media_type / filename
        full_path = full_path.resolve()
        
        # Ensure the resolved path is within the media directory
        media_base_resolved = Path(MEDIA_BASE).resolve()
        if not str(full_path).startswith(str(media_base_resolved)):
            logger.warning(f"Path traversal attempt: {media_path}")
            return jsonify(error="Path traversal not allowed"), 403
        
        # Try exact match first
        if full_path.exists():
            logger.debug(f"Found exact match: {full_path}")
            return send_from_directory(full_path.parent, full_path.name)
        
        # Try to find by filename stem in case of punctuation differences
        media_dir = Path(MEDIA_BASE) / system_name / media_type
        if media_dir.exists():
            file_stem = Path(filename).stem
            for file_in_dir in media_dir.iterdir():
                if file_in_dir.is_file() and file_in_dir.stem.lower() == file_stem.lower():
                    logger.debug(f"Found media by stem: {file_in_dir.name}")
                    return send_from_directory(media_dir, file_in_dir.name)
        
        logger.warning(f"Media not found - System: {system_name}, Type: {media_type}, File: {filename}, Full path: {full_path}")
        return jsonify(error="Media not found"), 404
    except Exception as e:
        logger.exception("Error serving media")
        return jsonify(error=str(e)), 500


@app.route("/api/debug/media-list/<system_name>/<media_type>")
def debug_media_list(system_name, media_type):
    """Debug endpoint: list files in a media directory for a system
    Returns JSON list of filenames and whether each file exists.
    Useful to verify what the backend can see on disk without requesting individual files.
    """
    try:
        # Prevent path traversal
        if '..' in system_name or system_name.startswith('/'):
            return jsonify(error="Invalid system name"), 400
        if '..' in media_type or media_type.startswith('/'):
            return jsonify(error="Invalid media type"), 400

        media_dir = Path(MEDIA_BASE) / system_name / media_type
        if not media_dir.exists():
            return jsonify(success=True, files=[])

        files = []
        for f in sorted(media_dir.iterdir()):
            if f.is_file():
                files.append({
                    'name': f.name,
                    'stem': f.stem,
                    'suffix': f.suffix,
                    'path': str(f.resolve())
                })

        logger.debug(f"Debug media list for {system_name}/{media_type}: {files}")
        return jsonify(success=True, files=files)
    except Exception as e:
        logger.exception("Error listing media directory")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/debug/gamelist-paths/<system>", methods=["GET"])
def debug_gamelist_paths(system):
    """Debug endpoint to list all paths in a gamelist.xml"""
    try:
        from lxml import etree
        gamelist_path = Path(ROMS_BASE) / system / 'gamelist.xml'
        if not gamelist_path.exists():
            return jsonify(error=f"Gamelist not found: {gamelist_path}"), 404
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        
        paths = []
        for game_elem in root.findall('.//game'):
            path_elem = game_elem.find('path')
            name_elem = game_elem.find('name')
            if path_elem is not None:
                paths.append({
                    'path': path_elem.text,
                    'name': name_elem.text if name_elem is not None else 'N/A'
                })
        
        return jsonify(system=system, total=len(paths), paths=paths)
    except Exception as e:
        logger.exception("Error reading gamelist paths")
        return jsonify(error=str(e)), 500


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify(
        status="healthy",
        roms_path=ROMS_BASE,
        media_path=MEDIA_BASE,
        roms_accessible=os.path.exists(ROMS_BASE),
        media_accessible=os.path.exists(MEDIA_BASE),
    )


# Stats for the Homepage widget and the header. Walking every system is slow on
# the NAS, so results are cached until something changes (any non-GET API call)
# or STATS_MAX_AGE passes (for changes made outside RetroManager).
STATS_MAX_AGE = 600
_stats_cache = {"value": None, "time": 0.0}


@app.after_request
def _invalidate_stats_on_change(response):
    if request.method != "GET" and request.path.startswith("/api/") and not request.path.startswith(
            ("/api/scraper/search", "/api/scraper/game-info", "/api/igdb/search", "/api/igdb/game-info")):
        _stats_cache["value"] = None
        _shelf_cache["value"] = None
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


# -----------------------------------------------------------------------------
# Shelf view
# -----------------------------------------------------------------------------

_shelf_cache = {"value": None, "time": 0.0}
SHELF_FIELDS = ('path', 'name', 'genre', 'developer', 'publisher', 'players', 'rating',
                'has_metadata', 'rom_exists', 'box2d', 'box3d', 'boxside', 'wheel', 'posters', 'images', 'mix')
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


REPORT_MEDIA_FOLDERS = ('box2d', 'box3d', 'boxside', 'screenshot', 'screenshottitle', 'wheel',
                        'fanart', 'mix', 'manuals', 'videos')


@app.route("/api/missing-media", methods=["GET"])
def missing_media_report():
    """Without ?system: per system, how many games lack each media type.
    With ?system=snes: each game and which media it has."""
    only = request.args.get("system")
    try:
        systems = []
        for system in scanner.discover_systems():
            if only and system.name != only:
                continue
            games = [g for g in scanner.get_games_for_system(system.name) if g.rom_exists]
            entry = {'system': system.name, 'full_name': system.get_full_name(), 'total': len(games),
                     'missing': {f: sum(1 for g in games if not getattr(g, f, None)) for f in REPORT_MEDIA_FOLDERS}}
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


# Backup gamelist.xml endpoint
@app.route("/api/backup_gamelist", methods=["POST"])
def backup_gamelist():
    try:
        data = request.get_json()
        system = data.get("system")
        if not system:
            return jsonify(error="Missing system name"), 400

        gamelist_path = Path(ROMS_BASE) / system / "gamelist.xml"
        if not gamelist_path.exists():
            return jsonify(error=f"gamelist.xml not found for system: {system}"), 404

        # Create dated backup filename
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = gamelist_path.parent / f"gamelist_{now}.xml"
        shutil.copy2(gamelist_path, backup_path)

        return jsonify(success=True, backup=str(backup_path.name))
    except Exception as e:
        logger.exception("Error backing up gamelist.xml")
        return jsonify(error=str(e)), 500

# List gamelist.xml backups for a system
@app.route("/api/list_gamelist_backups", methods=["POST"])
def list_gamelist_backups():
    try:
        data = request.get_json()
        system = data.get("system")
        if not system:
            return jsonify(error="Missing system name"), 400
        system_dir = Path(ROMS_BASE) / system
        if not system_dir.exists():
            return jsonify(error=f"System directory not found: {system}"), 404
        backups = []
        for f in system_dir.glob("gamelist_*.xml"):
            backups.append(f.name)
        backups.sort(reverse=True)
        return jsonify(success=True, backups=backups)
    except Exception as e:
        logger.exception("Error listing gamelist backups")
        return jsonify(error=str(e)), 500

# Restore gamelist.xml from a backup
@app.route("/api/restore_gamelist_backup", methods=["POST"])
def restore_gamelist_backup():
    try:
        data = request.get_json()
        system = data.get("system")
        backup_file = data.get("backup")
        if not system or not backup_file:
            return jsonify(error="Missing system name or backup file"), 400
        backup_path = _gamelist_backup_path(system, backup_file)
        if not backup_path:
            return jsonify(error=f"Backup file not found: {backup_file}"), 404
        current_backup = gamelist_mgr.backup(system, ROMS_BASE)
        shutil.copy2(backup_path, backup_path.parent / "gamelist.xml")
        return jsonify(success=True, backup=current_backup)
    except Exception as e:
        logger.exception("Error restoring gamelist backup")
        return jsonify(error=str(e)), 500

def _gamelist_backup_path(system, name):
    """A gamelist copy in a system folder (gamelist_<date>.xml, gamelist.backup.xml,
    Syncthing conflict copies...), never gamelist.xml itself or anything outside."""
    system_dir = _system_path_or_none(system)
    if (not system_dir or not name or '/' in name or '\\' in name or name == 'gamelist.xml'
            or not name.lower().startswith('gamelist') or not name.lower().endswith('.xml')):
        return None
    path = system_dir / name
    return path if path.is_file() else None


def _backup_kind(name):
    if 'sync-conflict' in name:
        return 'Sync conflict copy'
    if re.match(r'^gamelist_\d{8}_\d{6}\.xml$', name):
        return 'Backup'
    return 'Other copy'


def _read_entries(path):
    """{rom path (lowercase): {'path', field: text}} for a gamelist file."""
    entries = {}
    root = etree.parse(str(path)).getroot()
    for game in root.iter('game'):
        rom = strip_dot_slash(game.findtext('path') or '')
        if not rom:
            continue
        fields = {child.tag: (child.text or '').strip() for child in game if isinstance(child.tag, str)}
        fields['path'] = rom
        entries[rom.lower()] = fields
    return entries


@app.route("/api/systems/<system_name>/gamelist-backups", methods=["GET"])
def gamelist_backups(system_name):
    """Every saved copy of a system's gamelist, newest first, with its entry count."""
    system_dir = _system_path_or_none(system_name)
    if not system_dir:
        return jsonify(success=False, error="Unknown system"), 404
    items = []
    for f in system_dir.glob('gamelist*.xml'):
        if f.name == 'gamelist.xml' or not _gamelist_backup_path(system_name, f.name):
            continue
        st = f.stat()
        try:
            count = sum(1 for _ in etree.parse(str(f)).getroot().iter('game'))
        except Exception:
            count = None
        # Dated backups are copied with the gamelist's own file time, so their
        # name says when they were made
        made = re.match(r'^gamelist_(\d{8}_\d{6})\.xml$', f.name)
        when = datetime.strptime(made.group(1), '%Y%m%d_%H%M%S') if made else datetime.fromtimestamp(st.st_mtime)
        items.append({'name': f.name, 'kind': _backup_kind(f.name), 'size': st.st_size, 'entries': count,
                      'modified': when.isoformat()})
    items.sort(key=lambda i: i['modified'], reverse=True)
    current = system_dir / 'gamelist.xml'
    current_count = sum(1 for _ in etree.parse(str(current)).getroot().iter('game')) if current.exists() else 0
    return jsonify(success=True, backups=items, current_entries=current_count)


@app.route("/api/systems/<system_name>/gamelist-backups/<name>/diff", methods=["GET"])
def gamelist_backup_diff(system_name, name):
    """What restoring this copy would change, entry by entry: games it would bring back,
    games it would remove, and fields that differ (before = now, after = the copy)."""
    path = _gamelist_backup_path(system_name, name)
    if not path:
        return jsonify(success=False, error="Backup not found"), 404
    try:
        backup = _read_entries(path)
        current_path = path.parent / 'gamelist.xml'
        current = _read_entries(current_path) if current_path.exists() else {}
    except Exception as e:
        return jsonify(success=False, error=f"Couldn't read the gamelist: {e}"), 400
    added = [{'path': e['path'], 'name': e.get('name')} for k, e in backup.items() if k not in current]
    removed = [{'path': e['path'], 'name': e.get('name')} for k, e in current.items() if k not in backup]
    changed = []
    for key in backup.keys() & current.keys():
        now, then = current[key], backup[key]
        fields = [{'field': f, 'now': now.get(f, ''), 'then': then.get(f, '')}
                  for f in sorted(set(now) | set(then)) if f != 'path' and now.get(f, '') != then.get(f, '')]
        if fields:
            changed.append({'path': then['path'], 'name': now.get('name') or then.get('name'), 'fields': fields})
    changed.sort(key=lambda c: (c['name'] or '').lower())
    return jsonify(success=True, added=added, removed=removed, changed=changed)


@app.route("/api/systems/<system_name>/gamelist-backups/<name>/restore", methods=["POST"])
def gamelist_backup_restore(system_name, name):
    """Replace gamelist.xml with this copy (the current one is backed up first)."""
    path = _gamelist_backup_path(system_name, name)
    if not path:
        return jsonify(success=False, error="Backup not found"), 404
    try:
        etree.parse(str(path))
    except Exception as e:
        return jsonify(success=False, error=f"That copy isn't valid XML: {e}"), 400
    current_backup = gamelist_mgr.backup(system_name, ROMS_BASE)
    shutil.copy2(path, path.parent / 'gamelist.xml')
    return jsonify(success=True, backup=current_backup)


@app.route("/api/systems/<system_name>/gamelist-backups/<name>", methods=["DELETE"])
def gamelist_backup_delete(system_name, name):
    path = _gamelist_backup_path(system_name, name)
    if not path:
        return jsonify(success=False, error="Backup not found"), 404
    path.unlink()
    return jsonify(success=True)


@app.route("/api/systems/<system_name>/gamelist-backups/prune", methods=["POST"])
def gamelist_backup_prune(system_name):
    """Body: {keep: n}. Deletes all but the newest n dated backups (gamelist_<date>.xml).
    Sync conflict copies and other copies are left alone."""
    system_dir = _system_path_or_none(system_name)
    if not system_dir:
        return jsonify(success=False, error="Unknown system"), 404
    keep = max(1, int((request.get_json(silent=True) or {}).get('keep', 10)))
    dated = sorted((f for f in system_dir.glob('gamelist_*.xml') if _backup_kind(f.name) == 'Backup'),
                   key=lambda f: f.name, reverse=True)
    removed = []
    for f in dated[keep:]:
        f.unlink()
        removed.append(f.name)
    return jsonify(success=True, removed=removed)


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
            media = [m for m in (data.get("media") or []) if m in BULK_MEDIA_FOLDERS]
            try:
                applied = apply_scrape(system, rom_path, data["game_id"], media)
                result.update({k: applied.get(k, []) for k in ('filled', 'downloaded', 'errors')})
                if not applied.get('success'):
                    result['errors'].append(applied.get('error') or 'Scraping failed')
            except ScreenscraperError as e:
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


# -----------------------------------------------------------------------------
# Saves and save states
# -----------------------------------------------------------------------------

@app.route("/api/systems/<system_name>/saves", methods=["GET"])
def get_game_saves(system_name):
    """?rom=<rom path>. In-game saves and save states for one game, newest first,
    each with the person ("profile") it belongs to, or "shared"."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    rom_path = request.args.get("rom")
    if not rom_path:
        return jsonify(success=False, error="Missing rom"), 400
    try:
        return jsonify(
            success=True,
            saves=save_finder.find(system_name, strip_dot_slash(rom_path)),
            profiles=SAVE_PROFILES,
            available=save_finder.available(),
        )
    except Exception as e:
        logger.exception("Error listing saves")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/save-screenshot/<root_name>/<path:rel_path>", methods=["GET"])
def get_save_screenshot(root_name, rel_path):
    """The .png screenshot RetroArch stores next to a save state."""
    path = save_finder.screenshot_path(root_name, rel_path)
    if not path:
        return jsonify(error="Not found"), 404
    return send_file(path, mimetype="image/png", max_age=3600)


def _match_save_records(records):
    """Attach the game each save belongs to ('game': {system, full_name, rom_path,
    name, box2d, playcount, lastplayed}). Files in a system folder match that
    system's games; files in emulator-named folders match any system, if only one."""
    lookups = {}
    for system in scanner.discover_systems():
        try:
            games = scanner.get_games_for_system(system.name)
        except Exception:
            continue
        table = {}
        for g in games:
            info = {'system': system.name, 'full_name': system.get_full_name(), 'rom_path': strip_dot_slash(g.path),
                    'name': (g.name or '').strip(), 'box2d': g.box2d or g.screenshot, 'playcount': g.playcount,
                    'lastplayed': g.lastplayed}
            stem = Path(g.path).stem
            table.setdefault(stem.lower(), info)
            table.setdefault(title_key(stem), info)
            # "Legend of Zelda - X, The" and "The Legend of Zelda - X" alike
            table.setdefault(title_key(style_name(stem)), info)
        lookups[system.name] = table
    for r in records:
        base = re.sub(r'\.\d+$', '', r['base'])  # "Croc.1" (a numbered copy)
        keys = (base.lower(), title_key(base), title_key(style_name(base)))
        if r['system'] in lookups:
            r['game'] = next((lookups[r['system']][k] for k in keys if k in lookups[r['system']]), None)
        else:
            hits = {id(t[k]): t[k] for t in lookups.values() for k in keys if k in t}
            r['game'] = next(iter(hits.values())) if len(hits) == 1 else None
    return records


@app.route("/api/play-history", methods=["GET"])
def play_history():
    """Per game: when it was last saved and by whom, from the saves and savestates
    folders (and play counts if EmulationStation writes them)."""
    try:
        records = _match_save_records(save_finder.scan_all())
        games = {}
        unmatched = 0
        for r in records:
            if not r.get('game'):
                unmatched += 1
                continue
            g = r['game']
            key = (g['system'], g['rom_path'])
            entry = games.setdefault(key, {**g, 'last': 0, 'last_by': None, 'profiles': {}, 'files': 0})
            entry['files'] += 1
            if r['mtime'] > entry['last']:
                entry['last'], entry['last_by'] = r['mtime'], r['profile']
            entry['profiles'][r['profile']] = max(entry['profiles'].get(r['profile'], 0), r['mtime'])
        # Games EmulationStation counted but that have no saves
        for system in scanner.discover_systems():
            for g in scanner.get_games_for_system(system.name):
                if g.playcount and (system.name, strip_dot_slash(g.path)) not in games:
                    games[(system.name, strip_dot_slash(g.path))] = {
                        'system': system.name, 'full_name': system.get_full_name(), 'rom_path': strip_dot_slash(g.path),
                        'name': (g.name or '').strip(), 'box2d': g.box2d or g.screenshot, 'playcount': g.playcount,
                        'lastplayed': g.lastplayed, 'last': 0, 'last_by': None, 'profiles': {}, 'files': 0}
        items = sorted(games.values(), key=lambda e: e['last'], reverse=True)
        return jsonify(success=True, people=SAVE_PROFILES, games=items, unmatched=unmatched,
                       available=save_finder.available())
    except Exception as e:
        logger.exception("Error building play history")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/save-conflicts", methods=["GET"])
def save_conflicts():
    """Saves Syncthing kept more than one version of, with each version's details."""
    try:
        records = save_finder.scan_all()
        groups = save_finder.conflicts(records)
        _match_save_records([v for g in groups for v in g['versions']])
        for g in groups:
            g['game'] = next((v['game'] for v in g['versions'] if v.get('game')), None)
        return jsonify(success=True, conflicts=groups, writable=_saves_writable())
    except Exception as e:
        logger.exception("Error listing save conflicts")
        return jsonify(success=False, error=str(e)), 500


def _saves_writable():
    return all(os.access(p, os.W_OK) for p in save_finder.roots.values() if p.is_dir())


def _move_to_backup(source: Path, root_name: str, rel: str, stamp: str):
    target = SAVE_BACKUP_BASE / 'conflicts' / stamp / root_name / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))


@app.route("/api/save-conflicts/resolve", methods=["POST"])
def resolve_save_conflict():
    """Body: {id, keep: path of the version to keep}. The other versions move to
    SAVE_BACKUP_PATH/conflicts/<time>/; a kept conflict copy takes the original's
    name so the emulator loads it. Screenshots move with their states."""
    data = request.get_json(silent=True) or {}
    group = next((g for g in save_finder.conflicts() if g['id'] == data.get('id')), None)
    if not group:
        return jsonify(success=False, error="That conflict is gone. Reload the list."), 404
    keep = next((v for v in group['versions'] if v['path'] == data.get('keep')), None)
    if not keep:
        return jsonify(success=False, error="Pick one of the versions"), 400
    if not _saves_writable():
        return jsonify(success=False, error="The saves folders are mounted read-only. Remove :ro from them in docker-compose.yml."), 400
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    root = group['root']
    moved = []
    try:
        for v in group['versions']:
            if v['path'] == keep['path']:
                continue
            for rel in filter(None, (v['path'], v.get('screenshot'))):
                source = save_finder.resolve_path(root, rel)
                if source and source.is_file():
                    _move_to_backup(source, root, rel, stamp)
                    moved.append(rel)
        if keep['path'] != group['path']:
            for rel, target_rel in ((keep['path'], group['path']),
                                    (keep.get('screenshot'), group['path'] + '.png' if keep.get('screenshot') else None)):
                if not rel:
                    continue
                source, target = save_finder.resolve_path(root, rel), save_finder.resolve_path(root, target_rel)
                if source and target and source.is_file() and not target.exists():
                    source.rename(target)
        # The kept version becomes the newest, so "newer wins" syncs (the RetroPie's
        # rsync) don't bring back a copy you chose against
        kept = save_finder.resolve_path(root, group['path'])
        if kept and kept.is_file():
            os.utime(kept, None)
        return jsonify(success=True, moved=moved, backup=f"conflicts/{stamp}")
    except OSError as e:
        logger.exception("Error resolving save conflict")
        return jsonify(success=False, error=str(e), moved=moved), 500


def _zip_name(text):
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in text).strip("-")[:80] or "saves"


@app.route("/api/systems/<system_name>/saves/download", methods=["GET"])
def download_game_saves(system_name):
    """?rom=<path>. A zip of one game's saves and states (all people)."""
    rom = strip_dot_slash(request.args.get("rom", ""))
    if not _system_path_or_none(system_name) or not rom:
        return jsonify(success=False, error="Unknown system or ROM"), 404
    files = save_finder.find(system_name, rom)
    if not files:
        return jsonify(success=False, error="No saves for this game"), 404
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            for rel in filter(None, (f['path'], f.get('screenshot'))):
                path = save_finder.resolve_path(f['root'], rel)
                if path and path.is_file():
                    zf.write(path, f"{f['root']}/{rel}")
    buffer.seek(0)
    name = f"{_zip_name(Path(rom).stem)}-saves-{datetime.now().strftime('%Y%m%d')}.zip"
    return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=name)


_save_backup_job = {"running": False, "scope": None, "done": 0, "total": 0, "error": None, "file": None}
_save_backup_lock = threading.Lock()


def _run_save_backup(system, include_states, target):
    try:
        records = save_finder.scan_all()
        if system:
            _match_save_records(records)
            records = [r for r in records if r['system'] == system or (r.get('game') or {}).get('system') == system]
        if not include_states:
            records = [r for r in records if r['kind'] == 'save']
        files = [(r['root'], rel) for r in records for rel in filter(None, (r['path'], r.get('screenshot')))]
        _save_backup_job.update(total=len(files))
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.part')
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, (root, rel) in enumerate(files):
                path = save_finder.resolve_path(root, rel)
                if path and path.is_file():
                    zf.write(path, f"{root}/{rel}")
                _save_backup_job['done'] = i + 1
        tmp.replace(target)
        _save_backup_job.update(file=target.name)
    except Exception as e:
        logger.exception("Save backup failed")
        _save_backup_job.update(error=str(e))
    finally:
        _save_backup_job['running'] = False


@app.route("/api/save-backups", methods=["GET"])
def list_save_backups():
    """Zipped save backups in SAVE_BACKUP_PATH/zips, newest first, and the current job."""
    folder = SAVE_BACKUP_BASE / 'zips'
    zips = []
    if folder.is_dir():
        for z in folder.glob('*.zip'):
            st = z.stat()
            zips.append({'name': z.name, 'size': st.st_size, 'modified': datetime.fromtimestamp(st.st_mtime).isoformat()})
    zips.sort(key=lambda z: z['modified'], reverse=True)
    return jsonify(success=True, backups=zips, job=_save_backup_job, folder_ok=_backup_folder_ok(),
                   saves_writable=_saves_writable())


def _backup_folder_ok():
    try:
        SAVE_BACKUP_BASE.mkdir(parents=True, exist_ok=True)
        return os.access(SAVE_BACKUP_BASE, os.W_OK)
    except OSError:
        return False


@app.route("/api/save-backups", methods=["POST"])
def create_save_backup():
    """Body: {system?: name (default everything), include_states?: bool}. Zips in the background."""
    data = request.get_json(silent=True) or {}
    system = data.get("system") or None
    if system and not _system_path_or_none(system):
        return jsonify(success=False, error="Unknown system"), 404
    if not _backup_folder_ok():
        return jsonify(success=False, error=f"Can't write to {SAVE_BACKUP_BASE}. Mount a folder there (see docker-compose.yml)."), 400
    with _save_backup_lock:
        if _save_backup_job['running']:
            return jsonify(success=False, error="A backup is already running"), 409
        include_states = bool(data.get("include_states", True))
        name = f"saves-{_zip_name(system or 'everything')}{'' if include_states else '-no-states'}-{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        _save_backup_job.update(running=True, scope=system or 'everything', done=0, total=0, error=None, file=None)
        threading.Thread(target=_run_save_backup, args=(system, include_states, SAVE_BACKUP_BASE / 'zips' / name),
                         daemon=True).start()
    return jsonify(success=True, name=name)


def _save_backup_file(name):
    path = (SAVE_BACKUP_BASE / 'zips' / name)
    if '/' in name or '\\' in name or not name.endswith('.zip') or not path.is_file():
        return None
    return path


@app.route("/api/save-backups/<name>", methods=["GET"])
def download_save_backup(name):
    path = _save_backup_file(name)
    if not path:
        return jsonify(success=False, error="Not found"), 404
    return send_file(path, mimetype="application/zip", as_attachment=True, download_name=name)


@app.route("/api/save-backups/<name>", methods=["DELETE"])
def delete_save_backup(name):
    path = _save_backup_file(name)
    if not path:
        return jsonify(success=False, error="Not found"), 404
    path.unlink()
    return jsonify(success=True)


# -----------------------------------------------------------------------------
# Scraping (ScreenScraper and IGDB)
# -----------------------------------------------------------------------------

# Media folders the scanner reads; downloads may only target these
DOWNLOADABLE_MEDIA_FOLDERS = {
    'box2d', 'box3d', 'wheel', 'screenshot', 'screenshottitle', 'fanart',
    'posters', 'images', 'mix', 'thumbnail', 'manuals', 'videos', 'boxside',
}

_CONTENT_TYPE_EXTENSIONS = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'video/mp4': '.mp4',
    'video/webm': '.webm',
    'video/x-msvideo': '.avi',
    'video/x-matroska': '.mkv',
    'application/pdf': '.pdf',
}
_KNOWN_EXTENSIONS = set(_CONTENT_TYPE_EXTENSIONS.values()) | {'.jpeg'}


def _request_json():
    """Parse the JSON body even when the Content-Type header is missing."""
    return request.get_json(force=True, silent=True) or {}


def _media_file_stem(rom_path, game_name):
    """Downloaded media is named after the ROM file so the scanner can match it."""
    if rom_path:
        stem = Path(rom_path.replace('\\', '/')).stem
        if stem:
            return stem
    safe = "".join(c for c in (game_name or '') if c.isalnum() or c in " -_()[]'.,&!").strip()
    return safe[:200]


def _sniff_extension(head: bytes):
    """File type from the first bytes, for servers that send a generic content type
    (ScreenScraper sends manuals as application/force-download)."""
    if head.startswith(b'%PDF'):
        return '.pdf'
    if head.startswith(b'\x89PNG'):
        return '.png'
    if head.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return '.webp'
    if head[4:8] == b'ftyp':
        return '.mp4'
    if head.startswith(b'\x1a\x45\xdf\xa3'):
        return '.mkv'
    return None


def _download_one(url, target_dir, stem):
    """Download url to target_dir/stem.<ext>, replacing any existing file for that stem.
    Returns the saved Path. Raises ValueError with a readable message on failure."""
    response = None
    for attempt in range(2):
        try:
            response = requests.get(url, timeout=(10, 120), stream=True)
        except requests.RequestException as e:
            if attempt == 0:
                continue
            raise ValueError(f"download failed: {e}")
        if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
            response.close()
            time.sleep(2)
            continue
        break

    with response:
        if response.status_code != 200:
            raise ValueError(f"source returned HTTP {response.status_code}")

        content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
        if content_type.startswith('text/') or content_type in ('application/json', ''):
            # ScreenScraper answers "NOMEDIA" (or an error message) as text
            body = response.text.strip()[:120]
            if body.upper().startswith('NOMEDIA'):
                raise ValueError("the source has no file for this media type")
            raise ValueError(f"the source didn't return a media file ({body or 'empty response'})")

        chunks = response.iter_content(chunk_size=65536)
        first = next(chunks, b'')

        ext = _CONTENT_TYPE_EXTENSIONS.get(content_type)
        if not ext:
            url_ext = Path(urlparse(url).path).suffix.lower()
            ext = '.jpg' if url_ext == '.jpeg' else url_ext
        if ext not in _KNOWN_EXTENSIONS:
            ext = _sniff_extension(first)
        if ext not in _KNOWN_EXTENSIONS:
            raise ValueError(f"unsupported file type ({content_type or 'unknown'})")

        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / f"{stem}{ext}"
        tmp_path = target_dir / f".{stem}{ext}.part"
        try:
            with open(tmp_path, 'wb') as f:
                f.write(first)
                for chunk in chunks:
                    f.write(chunk)
            os.replace(tmp_path, final_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    _remove_other_formats(final_path)
    return final_path


def _remove_other_formats(final_path: Path):
    """Remove the same game's file in other formats (box2d/x.png after saving
    box2d/x.jpg), which would otherwise be picked up ahead of the new one."""
    stem = final_path.stem.lower()
    for other in final_path.parent.iterdir():
        if other.is_file() and other != final_path and other.stem.lower() == stem:
            try:
                other.unlink()
                logger.info(f"Replaced {other.name} with {final_path.name}")
            except OSError as e:
                logger.warning(f"Couldn't remove old media {other}: {e}")


@app.route("/api/systems/<system_name>/launch-files", methods=["GET"])
def list_launch_files(system_name):
    """?rom=<path>. For PC-style systems: every program in the game's folder that
    could launch it, likeliest first."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    folder = game_folder(request.args.get("rom", ""))
    if not is_folder_game_system(system_name) or not folder:
        return jsonify(success=True, files=[])
    return jsonify(success=True, files=launch_candidates(scanner.all_rom_files(Path(system_path)), folder))


@app.route("/api/systems/<system_name>/launch-file", methods=["POST"])
def set_launch_file(system_name):
    """Body: {from, to}. Points a PC game at a different program in its folder:
    relinks its gamelist entry, or creates one when it has none."""
    system_path = _system_path_or_none(system_name)
    if not system_path:
        return jsonify(success=False, error="Unknown system"), 404
    data = request.get_json(silent=True) or {}
    old, new = strip_dot_slash(data.get("from", "")), strip_dot_slash(data.get("to", ""))
    if not old or not new or game_folder(old) != game_folder(new) or not _rom_exists(system_path, new):
        return jsonify(success=False, error="Pick a file in the same game folder"), 400
    try:
        changed, backup = 0, None
        if (Path(system_path) / 'gamelist.xml').exists():
            changed, backup = gamelist_mgr.relink_paths(system_name, ROMS_BASE, {old: new})
        if not changed:
            game = Game.from_filename(new)
            game.name = style_name(folder_game_name(system_name, new) or game.name)
            changed, backup = gamelist_mgr.add_entries(system_name, ROMS_BASE, [game])
        renamed, errors = _rename_media_for_relink(system_name, {old: new})
        return jsonify(success=True, changed=changed, backup=backup, renamed_media=renamed, errors=errors)
    except Exception as e:
        logger.exception("Error changing launch file")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/media/upload", methods=["POST"])
def upload_media(system_name):
    """Multipart: rom_path, folder (box2d, wheel, ...), file. Saves the file as
    <media system>/<folder>/<ROM name>.<ext>, like scraped media."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    folder = request.form.get("folder", "")
    rom_path = request.form.get("rom_path", "")
    upload = request.files.get("file")
    if folder not in DOWNLOADABLE_MEDIA_FOLDERS:
        return jsonify(success=False, error=f"{folder or 'folder'} isn't a media folder RetroManager reads"), 400
    stem = _media_file_stem(rom_path, None)
    if not stem or not upload:
        return jsonify(success=False, error="Missing rom_path or file"), 400
    head = upload.stream.read(16)
    upload.stream.seek(0)
    ext = Path(upload.filename or '').suffix.lower()
    ext = '.jpg' if ext == '.jpeg' else ext
    if ext not in _KNOWN_EXTENSIONS:
        ext = _sniff_extension(head)
    if ext not in _KNOWN_EXTENSIONS:
        return jsonify(success=False, error="Unsupported file type"), 400
    media_system = scanner._resolve_media_system(system_name)
    target_dir = Path(MEDIA_BASE) / media_system / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / f"{stem}{ext}"
    tmp_path = target_dir / f".{stem}{ext}.part"
    try:
        upload.save(str(tmp_path))
        os.replace(tmp_path, final_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    _remove_other_formats(final_path)
    return jsonify(success=True, path=f"{media_system}/{folder}/{final_path.name}")


def _download_media(data):
    """Shared body of both download-media routes."""
    system_name = data.get("system_name")
    rom_path = data.get("rom_path")
    game_name = data.get("game_name")
    media_types = data.get("media_types") or {}

    if not system_name or not media_types:
        return jsonify(success=False, error="Missing system_name or media_types"), 400
    if '/' in system_name or '\\' in system_name or '..' in system_name:
        return jsonify(success=False, error="Invalid system_name"), 400

    stem = _media_file_stem(rom_path, game_name)
    if not stem:
        return jsonify(success=False, error="Missing rom_path or game_name"), 400

    media_system = scanner._resolve_media_system(system_name)
    saved_media, errors = {}, []

    for folder, url in media_types.items():
        if not url:
            continue
        if folder not in DOWNLOADABLE_MEDIA_FOLDERS:
            errors.append(f"{folder}: not a media folder RetroManager reads")
            continue
        try:
            saved = _download_one(url, Path(MEDIA_BASE) / media_system / folder, stem)
            saved_media[folder] = f"{media_system}/{folder}/{saved.name}"
            logger.info(f"Saved {folder} to {saved}")
        except (ValueError, OSError) as e:
            logger.warning(f"Media download for {folder} failed: {e}")
            errors.append(f"{folder}: {e}")

    return jsonify(success=bool(saved_media) or not errors, saved_media=saved_media, errors=errors)


@app.route("/api/scraper/search", methods=["POST"])
def scraper_search():
    data = _request_json()
    game_name = (data.get("name") or '').strip()
    if not game_name:
        return jsonify(success=False, error="Missing game name"), 400

    system_id = data.get("system_id") or screenscraper_system_id(data.get("system_name"))
    try:
        jeux = scraper.search_game(game_name, system_id)
        if not jeux and system_id:
            # Retry across all systems in case the folder maps to the wrong one
            jeux = scraper.search_game(game_name)
    except ScreenscraperError as e:
        return jsonify(success=False, error=str(e), results=[])

    # Stable sort: hacks go after originals, otherwise ScreenScraper's order is kept
    results = sorted((scraper.summarize_search_result(j) for j in jeux), key=lambda r: r['is_hack'])
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


# -----------------------------------------------------------------------------
# Bulk scrape: match many games, review, then apply (ScreenScraper only)
# -----------------------------------------------------------------------------

# Text fields bulk scraping may fill; existing values are never replaced
BULK_TEXT_FIELDS = ('name', 'desc', 'genre', 'developer', 'publisher', 'releasedate', 'players', 'rating')
# Media bulk scraping may download (videos are left out: large and slow)
BULK_MEDIA_FOLDERS = ('box2d', 'box3d', 'boxside', 'screenshot', 'screenshottitle', 'wheel', 'fanart', 'mix', 'manuals')


@app.route("/api/bulk-scrape/match", methods=["POST"])
def bulk_scrape_match():
    """Body: {system_name, rom_path, query?}. Best ScreenScraper match with a confidence and
    alternatives. `query` replaces the automatic lookup with a title search."""
    data = _request_json()
    system_path = _system_path_or_none(data.get("system_name"))
    rom_path = strip_dot_slash(data.get("rom_path"))
    if not system_path or not rom_path:
        return jsonify(success=False, error="Missing or unknown system_name / rom_path"), 400
    try:
        result = bulk_matcher.match(data["system_name"], rom_path, system_path / rom_path, (data.get("query") or "").strip() or None,
                                    title=folder_game_name(data["system_name"], rom_path))
        return jsonify(success=True, **result)
    except ScreenscraperError as e:
        # Quota, overload, bad credentials...: the UI stops and shows this
        return jsonify(success=False, error=str(e), fatal=True)
    except Exception as e:
        logger.exception("Error matching game")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/bulk-scrape/apply", methods=["POST"])
def bulk_scrape_apply():
    """Body: {system_name, rom_path, game_id, media: [folders]}. Fills the game's empty
    fields from the match, downloads media it doesn't have yet, links <image>,
    <thumbnail> and <video>, and saves the entry. Back up the gamelist first."""
    data = _request_json()
    system_name = data.get("system_name")
    system_path = _system_path_or_none(system_name)
    rom_path = strip_dot_slash(data.get("rom_path"))
    game_id = data.get("game_id")
    if not system_path or not rom_path or not game_id:
        return jsonify(success=False, error="Missing system_name, rom_path or game_id"), 400
    wanted_media = [m for m in (data.get("media") or []) if m in BULK_MEDIA_FOLDERS]

    try:
        result = apply_scrape(system_name, rom_path, game_id, wanted_media)
        if not result.get('success'):
            return jsonify(**result), 404 if result.get('error') == "Game not found" else 500
        return jsonify(**result)
    except ScreenscraperError as e:
        return jsonify(success=False, error=str(e), fatal=True)
    except Exception as e:
        logger.exception("Error applying bulk scrape")
        return jsonify(success=False, error=str(e)), 500


def apply_scrape(system_name, rom_path, game_id, wanted_media):
    """Fill a game's empty fields from a ScreenScraper game, download the media it
    doesn't have yet, link <image>/<thumbnail>/<video> and save the entry.
    Raises ScreenscraperError on quota/credential problems."""
    game = scanner.get_game_details(system_name, rom_path)
    if game is None:
        return dict(success=False, error="Game not found")
    jeu = jeu_cache.get(game_id) or scraper.get_game_info(game_id)
    scraped = scraper.extract_game_data(jeu)

    current = game.to_dict()
    merged = dict(current)
    filled = []
    for field in BULK_TEXT_FIELDS:
        value = scraped.get(field)
        # A game without an entry only has a name made from its file name, so it's replaced too
        has_value = current.get(field) not in (None, '') and (game.has_metadata or field != 'name')
        if value not in (None, '') and not has_value:
            merged[field] = value
            filled.append(field)

    stem = Path(rom_path).stem
    index = scanner.media_index(system_name)
    downloaded, skipped, errors = [], [], []
    for folder in wanted_media:
        url = scraped.get('media', {}).get(folder)
        if not url:
            continue
        if index.find(folder, stem):
            skipped.append(folder)
            continue
        try:
            _download_one(url, Path(MEDIA_BASE) / index.media_system / folder, stem)
            downloaded.append(folder)
        except (ValueError, OSError) as e:
            errors.append(f"{folder}: {e}")

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
    return dict(success=True, filled=filled, downloaded=downloaded, already_had=skipped, errors=errors)


def _scrape_targets(systems, include_media, media):
    """Games for the library scrape: missing metadata first, then (optionally)
    games missing any of the chosen media."""
    wanted = set(systems or [])
    metadata, missing_media = [], []
    for system in scanner.discover_systems():
        if wanted and system.name not in wanted:
            continue
        if not screenscraper_system_id(system.name):
            continue
        try:
            games = scanner.get_games_for_system(system.name)
        except Exception as e:
            logger.warning(f"Library scrape: couldn't list {system.name}: {e}")
            continue
        for game in games:
            if not game.rom_exists:
                continue
            target = {'system': system.name, 'system_name': system.get_full_name(),
                      'rom_path': strip_dot_slash(game.path), 'name': game.name}
            if not game.has_metadata:
                metadata.append({**target, 'reason': 'metadata'})
            elif include_media:
                lacking = [f for f in media if not getattr(game, f, None)]
                if lacking:
                    missing_media.append({**target, 'reason': 'media: ' + ', '.join(lacking)})
    return metadata + missing_media


def _invalidate_caches():
    _stats_cache["value"] = None
    _shelf_cache["value"] = None


scrape_queue = ScrapeQueue(
    state_dir=DATA_DIR,
    list_targets=_scrape_targets,
    match=lambda system, rom_path: bulk_matcher.match(
        system, rom_path, Path(ROMS_BASE) / system / rom_path, None, title=folder_game_name(system, rom_path)),
    apply=apply_scrape,
    backup=lambda system: gamelist_mgr.backup(system, ROMS_BASE),
    on_change=_invalidate_caches,
    fatal_errors=(ScreenscraperError,),
)


@app.route("/api/scrape-queue", methods=["GET"])
def scrape_queue_status():
    """Progress of the library scrape: running, total, done, current, applied,
    review (matches too uncertain to apply), failed."""
    return jsonify(success=True, **scrape_queue.snapshot())


@app.route("/api/scrape-queue/start", methods=["POST"])
def scrape_queue_start():
    """Body: {systems?: [...], include_media?: bool, media?: [folders], recheck?: bool}."""
    data = _request_json()
    media = [m for m in (data.get("media") or BULK_MEDIA_FOLDERS) if m in BULK_MEDIA_FOLDERS]
    result = scrape_queue.start(data.get("systems") or None, bool(data.get("include_media")), media,
                                bool(data.get("recheck")))
    return jsonify(**result), 200 if result.get('success') else 409


@app.route("/api/scrape-queue/stop", methods=["POST"])
def scrape_queue_stop():
    scrape_queue.stop()
    return jsonify(success=True)


@app.route("/api/igdb/search", methods=["POST"])
def igdb_search():
    data = _request_json()
    game_name = (data.get("name") or '').strip()
    if not game_name:
        return jsonify(success=False, error="Missing game name"), 400

    try:
        games = igdb_scraper.search_game(game_name, data.get("system_name"))
    except IGDBError as e:
        return jsonify(success=False, error=str(e), results=[])

    results = sorted((igdb_scraper.summarize_search_result(g) for g in games), key=lambda r: r['is_hack'])
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
