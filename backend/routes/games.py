"""
Games: listing, reading, saving and deleting gamelist entries, serving their media, and health and debug routes.
"""

from flask import jsonify, request, send_from_directory
import os
from pathlib import Path
from lxml import etree
from backend.models import Game
from backend.folder_games import is_game_folder
from backend.media_index import strip_dot_slash
from backend.systems import browser_playable, phone_players
from backend.routes.accounts import person
from backend.core import (
    media_sources,
    game_moved,
    library_state,
    _saveable_fields,
    _system_path_or_none,
    app,
    gamelist_mgr,
    logger,
    MEDIA_BASE,
    ROMS_BASE,
    scanner,
)

@app.route("/api/systems/<system_name>/games", methods=["GET"])
def get_games(system_name):
    try:
        games = scanner.get_games_for_system(system_name)
        return jsonify(success=True, games=[
            {**g.to_dict(), **library_state.for_game(f"{system_name}/{strip_dot_slash(g.path)}", person()),
             'playable': g.rom_exists and browser_playable(system_name, g.path),
             'phone_playable': g.rom_exists and bool(phone_players(system_name))} for g in games])
    except Exception as e:
        logger.exception("Error getting games")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/systems/<system_name>/games/<path:rom_path>", methods=["GET"])
def get_game(system_name, rom_path):
    try:
        game = scanner.get_game_details(system_name, rom_path)
        if not game:
            return jsonify(success=False, error="Game not found"), 404
        fields = game.to_dict()
        # Where each of its downloaded pictures came from: {media folder: {source, at}}
        came_from = media_sources.for_paths(v for v in fields.values() if isinstance(v, str) and '/' in v and not v.startswith(('.', '/')))
        folders = {k: came_from[v] for k, v in fields.items() if isinstance(v, str) and v in came_from and k not in ('image', 'thumbnail', 'video')}
        return jsonify(success=True, game={**fields, 'media_sources': folders, **library_state.for_game(f"{system_name}/{strip_dot_slash(rom_path)}", person()),
                                           'playable': game.rom_exists and browser_playable(system_name, rom_path),
                                           'phone_playable': game.rom_exists and bool(phone_players(system_name))})
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
            if is_game_folder(rom_file):
                # A whole game folder (PS3) is too much to delete from a web page
                errors.append(f"{rom_rel}: game folders aren't deleted here; remove the folder on the server")
            elif str(rom_file).startswith(str(system_path.resolve()) + os.sep) and rom_file.is_file():
                try:
                    rom_file.unlink()
                    deleted_files.append(rom_rel)
                    game_moved(system_name, rom_rel, None)
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
