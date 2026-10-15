"""
Downloading and uploading media, and choosing a PC game's launch file.
"""

from flask import jsonify, request
import os
from pathlib import Path
import time
from urllib.parse import urlparse
import requests
from backend.models import Game
from backend.name_style import style_name
from backend.folder_games import folder_game_name, game_folder, is_folder_game_system, launch_candidates
from backend.media_index import strip_dot_slash
from backend.media_sources import UPLOADED, source_of
from backend.core import (
    media_sources,
    game_moved,
    _rom_exists,
    _system_path_or_none,
    app,
    gamelist_mgr,
    logger,
    MEDIA_BASE,
    mix_provenance,
    ROMS_BASE,
    scanner,
)
from backend.routes.systems import _rename_media_for_relink

# Media folders the scanner reads; downloads may only target these
DOWNLOADABLE_MEDIA_FOLDERS = {
    'box2d', 'box3d', 'wheel', 'screenshot', 'screenshottitle', 'fanart',
    'posters', 'images', 'mix', 'thumbnail', 'manuals', 'videos', 'boxside', 'support',
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


def _download_one(url, target_dir, stem, source=None):
    """Download url to target_dir/stem.<ext>, replacing any existing file for that stem.
    Returns the saved Path. Raises ValueError with a readable message on failure.
    Where it came from (`source`, else the site in the address) is noted for the game's page."""
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
    media_sources.record(final_path, source or source_of(url))
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
        game_moved(system_name, old, new)
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
    media_sources.record(final_path, UPLOADED)
    if folder == 'mix':
        mix_provenance.forget(system_name, rom_path)  # no longer the one RetroManager generated
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
            if folder == 'mix' and rom_path:
                mix_provenance.forget(system_name, rom_path)
            logger.info(f"Saved {folder} to {saved}")
        except (ValueError, OSError) as e:
            logger.warning(f"Media download for {folder} failed: {e}")
            errors.append(f"{folder}: {e}")

    return jsonify(success=bool(saved_media) or not errors, saved_media=saved_media, errors=errors)
