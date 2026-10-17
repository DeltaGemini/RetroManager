"""
Playing a game on a phone, in the RetroArch that's installed there (the Android
app in android/, which shows the Console page and starts RetroArch itself):
which core plays the game, the files it needs on the phone, and those files.

The app keeps them in the phone's own roms folder, under the same system folder
and name as here, so a game that's already there (copied, or synced) isn't
fetched again. Battery saves are the ones the browser player uses
(/api/play/save): RetroArch's own .srm files, per person.
"""

import json
import threading
import time
from pathlib import Path

from flask import jsonify, request, send_file

from backend.core import _request_json, _rom_exists, _system_path_or_none, app, DATA_DIR, logger, MEDIA_BASE, SAVE_PROFILES, SAVES_BASE, scanner, saves_beside_roms
from backend.folder_games import game_folder, is_folder_game_system
from backend.media_index import strip_dot_slash
from backend.routes.accounts import person
from backend.routes.play import _save_name, _usable
from backend.systems import bios_files, phone_players, retroarch_cores


_PHONE_MEDIA = ('mix', 'box2d', 'box3d', 'boxside', 'wheel', 'marquee', 'image', 'images', 'thumbnail', 'screenshot',
                'screenshottitle', 'fanart', 'posters', 'support', 'manuals')


def _game_files(system_path, rom_path):
    """Everything the game needs beside its own file, as paths in the system's
    folder: a disc's tracks, a playlist's discs (and their tracks), or the
    whole of an installed game's folder."""
    if is_folder_game_system(system_path.name) and game_folder(rom_path):
        folder = system_path / game_folder(rom_path)
        return sorted(f for f in folder.rglob('*') if f.is_file())
    files = [system_path / rom_path]
    if rom_path.lower().endswith(('.cue', '.m3u')):
        parts = scanner.disc_parts(system_path)
        owners = {rom_path.lower()}
        # A playlist owns its discs, and a disc its tracks
        while True:
            more = {part for part, owner in parts.items() if owner.lower() in owners} - owners
            if not more:
                break
            owners |= more
        wanted = owners - {rom_path.lower()}
        if wanted:
            # parts are stored lowercase: find the real file names
            folders = {(system_path / part).parent for part in wanted}
            for folder in folders:
                if folder.is_dir():
                    files += [f for f in folder.iterdir() if f.is_file() and f.relative_to(system_path).as_posix().lower() in wanted]
    return files


@app.route("/api/phone/info", methods=["GET"])
def phone_info():
    """?system=&rom=. What the phone app needs to start a game in RetroArch:
    {playable, name, system, rom, players, cores, files: [{path, size, stamp, modified}], media, save, me, profiles, shared_saves}.
    `media` is its pictures and manual, as paths for /api/media/ (`media_stamps`:
    each one's date and size), and `bios` the system's BIOS files ([{name, size}]),
    which RetroArch keeps in its system folder.
    `players` is what can play it (backend/systems.py: phone_players), `cores`
    RetroArch's alone, likeliest first; `files` are paths in the system's
    folder; `save` is the battery save's file name."""
    system_name, rom_path = request.args.get("system", ""), strip_dot_slash(request.args.get("rom", ""))
    system_path = _system_path_or_none(system_name)
    cores, players = retroarch_cores(system_name), phone_players(system_name)
    if not system_path or not rom_path or not _rom_exists(system_path, rom_path) or not (system_path / rom_path).is_file():
        return jsonify(success=True, playable=False, error="That game isn't in the library.")
    if not players:
        return jsonify(success=True, playable=False, error=f"No emulator the app knows of plays {system_name}.")
    try:
        # (each with its date and size as `stamp`, and its date in ms as `modified`: the phone fetches it
        # again when it's been replaced, as an updated ROM, even one the same size)
        files = []
        for f in _game_files(system_path, rom_path):
            stat = f.stat()
            files.append({'path': f.relative_to(system_path).as_posix(), 'size': stat.st_size,
                          'stamp': f"{int(stat.st_mtime)}-{stat.st_size}", 'modified': int(stat.st_mtime * 1000)})
    except OSError as e:
        logger.exception("Couldn't list a game's files for the phone")
        return jsonify(success=False, error=str(e)), 500
    game = scanner.get_game_details(system_name, rom_path)
    # Its pictures and manual, to have on the phone with it (not its videos, which are large)
    described = game.to_dict() if game else {}
    media = sorted({described[field] for field in _PHONE_MEDIA if isinstance(described.get(field), str) and described[field]})
    # (each with its date and size, so the phone can tell when one has been replaced)
    stamps = {}
    for path in media:
        try:
            stat = (Path(MEDIA_BASE) / path).stat()
            stamps[path] = f"{int(stat.st_mtime)}-{stat.st_size}"
        except OSError:
            pass
    bios = [{'name': f.name, 'size': f.stat().st_size} for f in bios_files(system_name)]
    return jsonify(
        success=True, playable=True, name=(game.name if game else Path(rom_path).stem), system=system_name, rom=rom_path,
        cores=list(cores), players=players, files=files, media=media, media_stamps=stamps, bios=bios,
        save=_save_name(system_name, rom_path),
        # Whose save: the signed-in person's; else one of `profiles`, or the shared set (`shared_saves`)
        # (where saves are kept beside the games, there's only the shared set: whoever's signed in plays with it)
        me=None if saves_beside_roms() else person(), profiles=SAVE_PROFILES if _usable(SAVES_BASE) and not saves_beside_roms() else [],
        shared_saves=_usable(SAVES_BASE) or saves_beside_roms())


@app.route("/api/phone/rom/<system_name>/<path:rom_path>", methods=["GET"])
def phone_rom(system_name, rom_path):
    """One of a game's files (the paths /api/phone/info gives). Takes a Range,
    so a download that stopped can carry on."""
    system_path = _system_path_or_none(system_name)
    rom_path = strip_dot_slash(rom_path)
    if not system_path or not phone_players(system_name) or any(part.startswith('.') for part in Path(rom_path).parts):
        return jsonify(success=False, error="Not a game file"), 404
    target = (system_path / rom_path).resolve()
    if not target.is_file() or system_path.resolve() not in target.parents:
        return jsonify(success=False, error="Not a game file"), 404
    return send_file(target, mimetype='application/octet-stream', conditional=True, download_name=target.name)


@app.route("/api/phone/bios/<system_name>/<name>", methods=["GET"])
def phone_bios(system_name, name):
    """One of a system's BIOS files (the names /api/phone/info gives)."""
    found = next((f for f in bios_files(system_name) if f.name == name), None)
    if not found:
        return jsonify(success=False, error="No such BIOS file"), 404
    return send_file(found, mimetype='application/octet-stream', conditional=True, download_name=found.name)


# --- What's been played on a phone ---
# RetroArch on a phone says nothing of what it played, and a game needn't write
# a save, so the app says when it starts one. The Console page's "Continue
# playing" counts it with the saves.
_PLAYS_FILE = DATA_DIR / 'phone-plays.json'
_plays_lock = threading.Lock()


def _read_plays():
    try:
        return json.loads(_PLAYS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def played_on_phones(who):
    """{"system/rom path": when (seconds)} for a person (None: with login off)."""
    with _plays_lock:
        return dict(_read_plays().get(who or '', {}))


@app.route("/api/phone/played", methods=["POST"])
def phone_played():
    """{system, rom, at}: the signed-in person started this game on a phone (`at`: when, in seconds; now if left out)."""
    data = _request_json()
    system_name, rom_path = data.get("system") or "", strip_dot_slash(data.get("rom") or "")
    system_path = _system_path_or_none(system_name)
    if not system_path or not rom_path or not _rom_exists(system_path, rom_path):
        return jsonify(success=False, error="That game isn't in the library."), 404
    try:
        when = min(float(data.get("at") or time.time()), time.time())
    except (TypeError, ValueError):
        when = time.time()
    with _plays_lock:
        plays = _read_plays()
        mine = plays.setdefault(person() or '', {})
        mine[f"{system_name}/{rom_path}"] = max(when, mine.get(f"{system_name}/{rom_path}", 0))
        try:
            tmp = _PLAYS_FILE.with_name(_PLAYS_FILE.name + '.part')
            tmp.write_text(json.dumps(plays))
            tmp.replace(_PLAYS_FILE)
        except OSError as e:
            logger.warning(f"Couldn't keep what was played on the phone: {e}")
            return jsonify(success=False, error=str(e)), 500
    # The Console page's recent games are worked out again
    from backend.routes import console
    console.refresh_in_background(person())
    return jsonify(success=True)


@app.route("/api/phone/cores", methods=["GET"])
def phone_cores():
    """The library's systems a phone can play, each with what plays it, for the
    app's own choice: {systems: [{name, label, players, cores}]}."""
    systems = [{'name': s.name, 'label': s.get_full_name(), 'players': phone_players(s.name), 'cores': list(retroarch_cores(s.name))}
               for s in scanner.discover_systems() if phone_players(s.name)]
    return jsonify(success=True, systems=sorted(systems, key=lambda s: s['label'].lower()))


# --- A phone's RetroArch setup, to give another phone the same ---
# RetroArch keeps each core's overrides, options, remaps and shader presets in
# its config folder, and overlays beside it: the files that make a core look
# and behave as it's been set up. The app sends one phone's here and fetches
# them on another (RetroArch's main settings file is out of any app's reach,
# so this is as much of a setup as can be carried).
SETUP_DIR = DATA_DIR / 'retroarch-setup'
SETUP_FOLDERS = ('config', 'overlays', 'overlay', 'layouts', 'shaders', 'cheats')
MAX_SETUP_FILE = 32 * 1024 * 1024
MAX_SETUP_FILES = 5000


def _setup_path(rel):
    """Where a file of the setup is kept, or None for a path that isn't one of its folders'."""
    parts = Path(str(rel or '').replace('\\', '/')).parts
    if len(parts) < 2 or parts[0] not in SETUP_FOLDERS or any(p in ('..', '.') or p.startswith('/') for p in parts):
        return None
    return SETUP_DIR / 'files' / Path(*parts)


def _setup_manifest():
    try:
        return json.loads((SETUP_DIR / 'setup.json').read_text())
    except (OSError, ValueError):
        return None


@app.route("/api/phone/setup", methods=["GET"])
def phone_setup():
    """The saved setup: {saved: true, device, base, package, at, files: [{path, size}]}, or {saved: false}."""
    manifest = _setup_manifest()
    return jsonify(success=True, saved=bool(manifest), **(manifest or {}))


@app.route("/api/phone/setup/file", methods=["GET", "PUT"])
def phone_setup_file():
    """?path=. One file of the setup, by its path in the RetroArch folder
    ("config/mGBA/mGBA.cfg"). PUT keeps it (for a save in progress: see below)."""
    target = _setup_path(request.args.get("path"))
    if not target:
        return jsonify(success=False, error="Not a file of a RetroArch setup"), 400
    if request.method == "GET":
        if not target.is_file():
            return jsonify(success=False, error="Not in the saved setup"), 404
        return send_file(target, mimetype='application/octet-stream', max_age=0)
    data = request.get_data(cache=False)
    if len(data) > MAX_SETUP_FILE:
        return jsonify(success=False, error="Too large for a setup file"), 400
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.part")
        tmp.write_bytes(data)
        tmp.replace(target)
    except OSError as e:
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True, size=len(data))


@app.route("/api/phone/setup", methods=["POST"])
def phone_setup_save():
    """{device, base, package, files: [paths]}: the setup is now these files
    (sent with PUT just before), from this phone. Files of an earlier setup
    that aren't among them are removed."""
    data = _request_json()
    wanted = [str(p) for p in (data.get("files") or [])][:MAX_SETUP_FILES]
    kept = {}
    for rel in wanted:
        target = _setup_path(rel)
        if target and target.is_file():
            kept[target] = {'path': Path(rel.replace('\\', '/')).as_posix(), 'size': target.stat().st_size}
    files = SETUP_DIR / 'files'
    try:
        for old in sorted(files.rglob('*'), reverse=True) if files.is_dir() else []:
            if old.is_file() and old not in kept:
                old.unlink()
            elif old.is_dir() and not any(old.iterdir()):
                old.rmdir()
        manifest = {'device': str(data.get("device") or 'a phone')[:80], 'base': str(data.get("base") or '')[:300],
                    'package': str(data.get("package") or '')[:80], 'at': int(time.time()),
                    'files': sorted(kept.values(), key=lambda f: f['path'])}
        SETUP_DIR.mkdir(parents=True, exist_ok=True)
        (SETUP_DIR / 'setup.json').write_text(json.dumps(manifest))
    except OSError as e:
        logger.exception("Couldn't keep the RetroArch setup")
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True, saved=True, **manifest)
