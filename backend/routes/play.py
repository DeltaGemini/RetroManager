"""
Playing a game in the browser (EmulatorJS): the emulator's files (fetched once
and kept), the ROM itself, the BIOS a system needs, and reading and writing a
person's in-game save and save state.

Battery saves are the same files the Pi uses (RetroArch's .srm, or .sav on the
DS); the first time a play session overwrites one, the old file is copied to
the save backups folder. Save states are the browser emulator's own, kept
apart from RetroArch's in a "Browser" folder.
"""

import hashlib
from io import BytesIO
import mimetypes
import os
import re
import shutil
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from flask import jsonify, request, send_file

from backend.core import (
    ROMS_BASE,
    saves_beside_roms,
    _rom_exists,
    _system_path_or_none,
    app,
    DATA_DIR,
    logger,
    SAVE_BACKUP_BASE,
    save_finder,
    SAVE_PROFILES,
    SAVES_BASE,
    SAVESTATES_BASE,
    scanner,
    settings,
)
from backend.media_index import strip_dot_slash
from backend.saves import SHARED
from backend import pi_states
from backend.systems import bios_file, browser_playable, emulatorjs_system, normalize_system_name

# The largest save or save state accepted from the browser
MAX_SAVE_BYTES = 16 * 1024 * 1024
MAX_STATE_BYTES = 64 * 1024 * 1024
# Systems whose battery save isn't RetroArch's usual .srm
SAVE_EXTENSIONS = {'nds': '.sav', 'nintendods': '.sav'}

# EmulatorJS's files, fetched from its server the first time each is asked for
EMULATOR_CACHE = DATA_DIR / 'emulatorjs'
_SAFE_PATH_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.\-]*(/[A-Za-z0-9_][A-Za-z0-9_.\-]*)*$')
_fetch_locks = {}
_fetch_locks_guard = threading.Lock()

# Disc games zipped with their tracks for the browser: the newest few are kept
DISC_CACHE = DATA_DIR / 'play-cache'
KEEP_DISC_ZIPS = 2

# (save path, play session) pairs already backed up, so a session backs a save up once
_backed_up = set()
_backup_lock = threading.Lock()


# --- The emulator itself ---

STABLE_EMULATORJS = 'https://cdn.emulatorjs.org/stable/data'


def _emulator_cache():
    """Where the files fetched from the address in Settings are kept. Each
    address has its own folder, so changing it (to a newer build, say) doesn't
    mix one build's files with another's; the stable build keeps the original one."""
    source = settings.get('emulatorjs_url').rstrip('/')
    if source == STABLE_EMULATORJS:
        return EMULATOR_CACHE
    return EMULATOR_CACHE / 'sources' / hashlib.sha1(source.encode()).hexdigest()[:12]


@app.route("/emulatorjs/<path:asset>", methods=["GET"])
def emulatorjs_asset(asset):
    """One of EmulatorJS's files. Kept in DATA_PATH/emulatorjs once fetched, so
    it's only downloaded the first time."""
    if not _SAFE_PATH_RE.match(asset) or '..' in asset:
        return "Not found", 404
    cached = _emulator_cache() / asset
    if not cached.is_file():
        with _fetch_locks_guard:
            lock = _fetch_locks.setdefault(asset, threading.Lock())
        with lock:
            if not cached.is_file():
                upstream = settings.get('emulatorjs_url').rstrip('/') + '/' + asset
                try:
                    response = requests.get(upstream, timeout=(10, 300), stream=True)
                    if response.status_code != 200:
                        return "Not found", 404
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    tmp = cached.with_name(f".{cached.name}.part")
                    with open(tmp, 'wb') as out:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            out.write(chunk)
                    tmp.replace(cached)
                except (requests.RequestException, OSError) as e:
                    logger.warning(f"Couldn't fetch EmulatorJS's {asset}: {e}")
                    return "EmulatorJS couldn't be fetched, and this part of it hasn't been kept yet", 502
    mimetype = 'application/wasm' if asset.endswith('.wasm') else (mimetypes.guess_type(asset)[0] or 'application/octet-stream')
    return send_file(cached, mimetype=mimetype, max_age=86400)


# --- The game ---

def _playable_rom(system_name, rom_path):
    """(rom file, EmulatorJS system) for a game the browser can play, else (None, None)."""
    system_path = _system_path_or_none(system_name)
    rom_path = strip_dot_slash(rom_path)
    core = emulatorjs_system(system_name)
    if not system_path or not core or not rom_path or not _rom_exists(system_path, rom_path):
        return None, None
    rom_file = system_path / rom_path
    if not rom_file.is_file() or not browser_playable(system_name, rom_path):
        return None, None
    return rom_file, core


def _in_library(system_name, rom_path):
    """Whether the game is there at all. Its battery save is kept whether or not
    the browser can play it: the phone app (backend/routes/phone.py) plays more."""
    system_path = _system_path_or_none(system_name)
    rom_path = strip_dot_slash(rom_path)
    return bool(system_path and rom_path and _rom_exists(system_path, rom_path) and (system_path / rom_path).is_file())


def _disc_files(system_name, rom_path):
    """A disc's .cue and the track files it names, as paths in the system's folder."""
    system_path = _system_path_or_none(system_name)
    parts = scanner.disc_parts(system_path)
    names = [rom_path] + [p for p, owner in parts.items() if owner.lower() == rom_path.lower()]
    files = []
    for rel in names:
        source = system_path / rel
        if not source.is_file():
            # parts are stored lowercase: find the real file name
            matches = [f for f in source.parent.glob('*') if f.name.lower() == Path(rel).name.lower()]
            if not matches:
                continue
            source = matches[0]
        files.append(source)
    return files


def _disc_zip(system_name, rom_path):
    """A .cue game zipped (not compressed) with its tracks, which is how the
    browser emulator takes a disc. Made once and kept while it's among the newest."""
    files = _disc_files(system_name, rom_path)
    stamp = 'v2|' + '|'.join(f"{f}:{f.stat().st_size}:{f.stat().st_mtime_ns}" for f in files)
    target = DISC_CACHE / f"{hashlib.sha1(stamp.encode()).hexdigest()[:16]}.zip"
    if not target.is_file():
        DISC_CACHE.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.part')
        # Each track goes in under the name the .cue gives it: the emulator's
        # disk tells capitals apart, and the file's own name may not match
        try:
            cue_names = re.findall(r'^\s*FILE\s+"([^"]+)"', files[0].read_text(errors='replace'), re.MULTILINE | re.IGNORECASE)
        except (OSError, IndexError):
            cue_names = []
        spelling = {Path(name.replace('\\', '/')).name.lower(): Path(name.replace('\\', '/')).name for name in cue_names}
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED, allowZip64=True) as archive:
            for f in files:
                archive.write(f, spelling.get(f.name.lower(), f.name))
        tmp.replace(target)
        for old in sorted(DISC_CACHE.glob('*.zip'), key=lambda f: f.stat().st_mtime, reverse=True)[KEEP_DISC_ZIPS:]:
            try:
                old.unlink()
            except OSError:
                pass
    else:
        target.touch()
    return target


def _whose(profile):
    """The saves a person's request is about. Where saves are kept beside the
    games (Settings > Saves) everyone's are the same: SHARED, for anyone."""
    return SHARED if profile and saves_beside_roms() else profile


def _owner(profile):
    """Whose saves a request is about: a person, or SHARED (the saves that are
    nobody's in particular, where RetroArch keeps them when it isn't set up for
    people). None for anyone else."""
    profile = _whose(profile)
    return profile if profile == SHARED or profile in SAVE_PROFILES else None


def _game_folder(system_name, rom_path):
    """The folder a game is in, where its saves go when they're kept beside the games."""
    return Path(ROMS_BASE) / system_name / Path(strip_dot_slash(rom_path)).parent


# Where a person's battery saves and RetroArch save states for a game go when
# there are none to go beside yet. The one place that knows the two layouts
# (Settings > Saves): folders of their own, a person's inside them, or beside
# the game, everyone's. (The browser's own states are apart: _state_file.)

def _saves_folder(system_name, rom_path, profile):
    if saves_beside_roms():
        return _game_folder(system_name, rom_path)
    profile = _whose(profile)
    return Path(SAVES_BASE) / system_name if profile == SHARED else Path(SAVES_BASE) / profile / system_name


def _states_folder(system_name, rom_path, profile):
    if saves_beside_roms():
        return _game_folder(system_name, rom_path)
    profile = _whose(profile)
    return Path(SAVESTATES_BASE) / system_name if profile == SHARED else Path(SAVESTATES_BASE) / profile / system_name


def _kept_as(path, states=False):
    """Where a copy of a save or state goes inside a backup: its place in its own
    folder (saves under their path in saves/, states under savestates/...),
    and roms/... for one kept beside a game."""
    path = Path(path)
    for name, base in (('savestates', SAVESTATES_BASE), ('saves', SAVES_BASE), ('roms', ROMS_BASE)):
        try:
            rel = path.relative_to(base)
        except ValueError:
            continue
        return rel if name == 'saves' and not states else Path(name) / rel
    return Path(path.name)


def _save_name(system_name, rom_path):
    """The battery save's file name: "<rom>.srm" (.sav on the DS)."""
    return f"{Path(strip_dot_slash(rom_path)).stem}{SAVE_EXTENSIONS.get(normalize_system_name(system_name), '.srm')}"


def _save_file(system_name, rom_path, profile):
    """Where a battery save for this game lives. A person's:
    saves/<person>/<system>/<rom>.srm. The shared one: where it already is
    (RetroArch may sort them by system or by core), else saves/<system>/.
    None if the profile isn't a person or SHARED."""
    name, profile = _save_name(system_name, rom_path), _whose(profile)
    if profile == SHARED:
        for record in save_finder.find(system_name, rom_path):
            if record['root'] in ('saves', 'roms') and record['profile'] == SHARED and record['file'].lower() == name.lower() and not record['conflict']:
                found = save_finder.resolve_path(record['root'], record['path'])
                if found:
                    return found
        return _saves_folder(system_name, rom_path, SHARED) / name
    if profile not in SAVE_PROFILES:
        return None
    return _saves_folder(system_name, rom_path, profile) / name


def _state_file(system_name, rom_path, profile, auto=False):
    """Where a browser save state for this game lives:
    savestates/<person>/<system>/Browser/<rom>.state (the shared one without the person);
    with auto, the one made on leaving the game, <rom>.state.auto beside it."""
    if not _owner(profile):
        return None
    # (the browser's own states stay in savestates/ even where RetroArch's are beside the games:
    # "<rom>.state" there is RetroArch's slot 0)
    profile = _whose(profile)
    base = Path(SAVESTATES_BASE) if profile == SHARED else Path(SAVESTATES_BASE) / profile
    return base / system_name / 'Browser' / f"{Path(strip_dot_slash(rom_path)).stem}.state{'.auto' if auto else ''}"


def _usable(folder):
    try:
        return Path(folder).is_dir()
    except OSError:
        return False


def _modified(path):
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds') if path.is_file() else None


@app.route("/api/play/info", methods=["GET"])
def play_info():
    """?system=&rom=. Whether the game can be played in the browser, and what
    the player needs: {playable, core, name, rom_url, rom_version, bios_url, emulatorjs_url,
    states, profiles: [{name, has_save, modified, has_state, stopped}]}. rom_version changes when the
    file does: EmulatorJS keeps ROMs in the browser by name and only fetches one again when
    its size differs, so a ROM replaced by one the same size (most are) would play the old."""
    system_name, rom_path = request.args.get("system", ""), strip_dot_slash(request.args.get("rom", ""))
    rom_file, core = _playable_rom(system_name, rom_path)
    if not rom_file:
        return jsonify(success=True, playable=False)
    game = scanner.get_game_details(system_name, rom_path)
    profiles = []
    if _usable(SAVES_BASE) or saves_beside_roms():
        # (the shared set first: it's the only one until people are added, or where saves are beside the games)
        for profile in [SHARED] + ([] if saves_beside_roms() else SAVE_PROFILES):
            save, state = _save_file(system_name, rom_path, profile), _state_file(system_name, rom_path, profile)
            auto = _state_file(system_name, rom_path, profile, auto=True)
            profiles.append({'name': profile, 'has_save': save.is_file(), 'modified': _modified(save), 'has_state': state.is_file(),
                             # (where they stopped: the state made on leaving the game)
                             'stopped': _modified(auto) if auto and auto.is_file() else None})
    is_disc = rom_file.suffix.lower() == '.cue'
    try:
        stat = rom_file.stat()
        version = f"{stat.st_mtime_ns:x}-{stat.st_size:x}"
    except OSError:
        version = None
    return jsonify(
        success=True, playable=True, core=core, name=(game.name if game else rom_file.stem),
        rom_url=f"/api/rom-disc/{system_name}/{rom_path}.zip" if is_disc else f"/api/rom/{system_name}/{rom_path}", rom_version=version,
        bios_url=f"/api/play/bios/{system_name}/{bios_file(system_name).name}" if bios_file(system_name) else None,
        emulatorjs_url="/emulatorjs/", states=_usable(SAVESTATES_BASE), profiles=profiles)


@app.route("/api/rom/<system_name>/<path:rom_path>", methods=["GET"])
def serve_rom(system_name, rom_path):
    """The ROM file itself, for the browser emulator."""
    rom_file, _ = _playable_rom(system_name, rom_path)
    if not rom_file:
        return jsonify(success=False, error="Not a game that can be played in the browser"), 404
    return send_file(rom_file, mimetype='application/octet-stream', conditional=True, download_name=rom_file.name)


@app.route("/api/rom-disc/<system_name>/<path:rom_path>.zip", methods=["GET"])
def serve_disc(system_name, rom_path):
    """A disc game (.cue) with its track files, as one zip for the browser emulator."""
    rom_file, _ = _playable_rom(system_name, rom_path)
    if not rom_file or rom_file.suffix.lower() != '.cue':
        return jsonify(success=False, error="Not a disc game that can be played in the browser"), 404
    try:
        return send_file(_disc_zip(system_name, strip_dot_slash(rom_path)), mimetype='application/zip', conditional=True,
                         download_name=f"{rom_file.stem}.zip")
    except OSError as e:
        logger.exception("Couldn't put a disc together for the browser")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/play/bios/<system_name>/<name>", methods=["GET"])
def serve_bios(system_name, name):
    """The BIOS file the system plays with, from BIOS_PATH."""
    bios = bios_file(system_name) if emulatorjs_system(system_name) else None
    if not bios or bios.name != name:
        return jsonify(success=False, error="No BIOS for that system"), 404
    return send_file(bios, mimetype='application/octet-stream', download_name=bios.name)


# --- Saves ---

@app.route("/api/play/save", methods=["GET"])
def get_play_save():
    """?system=&rom=&profile=. The person's battery save for the game (404 if they have none)."""
    system_name, rom_path = request.args.get("system", ""), request.args.get("rom", "")
    save = _save_file(system_name, rom_path, request.args.get("profile", "")) if _in_library(system_name, rom_path) else None
    if not save or not save.is_file():
        return jsonify(success=False, error="No save"), 404
    return send_file(save, mimetype='application/octet-stream', max_age=0)


@app.route("/api/play/save", methods=["PUT"])
def put_play_save():
    """?system=&rom=&profile=&session=. Body: the save file. Writes the person's
    battery save; the first write of a play session copies the old one to the
    save backups folder (browser-play/...). The phone app's saves come here too."""
    system_name, rom_path = request.args.get("system", ""), request.args.get("rom", "")
    save = _save_file(system_name, rom_path, request.args.get("profile", "")) if _in_library(system_name, rom_path) else None
    if not save:
        return jsonify(success=False, error="Unknown game or person"), 404
    data = request.get_data(cache=False)
    if not data or len(data) > MAX_SAVE_BYTES:
        return jsonify(success=False, error="The save is empty or too large"), 400
    # A save that's nothing but empty cells means the emulator hasn't loaded one yet
    if save.is_file() and not data.strip(b'\x00').strip(b'\xff'):
        return jsonify(success=False, error="Not replacing a save with an empty one"), 409
    session = request.args.get("session", "") or "none"
    backup = None
    try:
        if save.is_file():
            if save.read_bytes() == data:
                return jsonify(success=True, unchanged=True)
            with _backup_lock:
                first = (str(save), session) not in _backed_up
                _backed_up.add((str(save), session))
            if first:
                target = SAVE_BACKUP_BASE / 'browser-play' / time.strftime('%Y%m%d-%H%M%S') / _kept_as(save)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(save, target)
                backup = str(target.relative_to(SAVE_BACKUP_BASE))
        save.parent.mkdir(parents=True, exist_ok=True)
        tmp = save.with_name(f".{save.name}.part")
        tmp.write_bytes(data)
        tmp.replace(save)
    except OSError as e:
        logger.exception("Couldn't write a browser-play save")
        return jsonify(success=False, error=f"Couldn't write the save: {e}"), 500
    return jsonify(success=True, backup=backup, size=len(data))


# --- Save states (the browser emulator's own; RetroArch can't load them) ---

@app.route("/api/play/state", methods=["GET"])
def get_play_state():
    """?system=&rom=&profile=[&auto=1]. The person's browser save state for the game (404 if none);
    with auto, the one made when they last left it."""
    system_name, rom_path = request.args.get("system", ""), request.args.get("rom", "")
    rom_file, _ = _playable_rom(system_name, rom_path)
    state = _state_file(system_name, rom_path, request.args.get("profile", ""), auto=request.args.get("auto") == "1") if rom_file else None
    if not state or not state.is_file():
        return jsonify(success=False, error="No save state"), 404
    return send_file(state, mimetype='application/octet-stream', max_age=0)


@app.route("/api/play/state", methods=["PUT"])
def put_play_state():
    """?system=&rom=&profile=[&auto=1]. Body: the save state. Keeps the person's one
    browser save state for the game (with auto, the one made on leaving it, apart from the
    one they saved); the one before it is kept beside it as .bak."""
    system_name, rom_path = request.args.get("system", ""), request.args.get("rom", "")
    rom_file, _ = _playable_rom(system_name, rom_path)
    state = _state_file(system_name, rom_path, request.args.get("profile", ""), auto=request.args.get("auto") == "1") if rom_file else None
    if not state:
        return jsonify(success=False, error="Unknown game or person"), 404
    data = request.get_data(cache=False)
    if not data or len(data) > MAX_STATE_BYTES:
        return jsonify(success=False, error="The save state is empty or too large"), 400
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        if state.is_file():
            shutil.copy2(state, state.with_name(state.name + '.bak'))
        tmp = state.with_name(f".{state.name}.part")
        tmp.write_bytes(data)
        tmp.replace(state)
    except OSError as e:
        logger.exception("Couldn't write a browser-play save state")
        return jsonify(success=False, error=f"Couldn't write the save state: {e}"), 500
    return jsonify(success=True, size=len(data))


# --- RetroArch's save states (made on the Pi), loaded into the browser emulator ---

def _retroarch_states(system_name, rom_path):
    """The game's RetroArch save states, newest first: the save finder's
    records, without the browser emulator's own."""
    return [s for s in save_finder.find(system_name, rom_path)
            if s['root'] in ('savestates', 'roms') and s['kind'] in ('state', 'auto') and s['folder'] != 'Browser' and not s['conflict']]


@app.route("/api/play/pi-states", methods=["GET"])
def list_pi_states():
    """?system=&rom=. The game's RetroArch save states, each with the core that
    made it and the EmulatorJS core that can load it (null if none can):
    [{path, profile, label, modified, size, screenshot, made_by, core}]."""
    system_name, rom_path = request.args.get("system", ""), strip_dot_slash(request.args.get("rom", ""))
    rom_file, _ = _playable_rom(system_name, rom_path)
    if not rom_file:
        return jsonify(success=False, error="Unknown game"), 404
    states = []
    for record in _retroarch_states(system_name, rom_path):
        path = save_finder.resolve_path(record['root'], record['path'])
        made_by, core = pi_states.describe(path) if path else (None, None)
        states.append({**{k: record[k] for k in ('path', 'profile', 'label', 'modified', 'size', 'screenshot')}, 'made_by': made_by, 'core': core})
    return jsonify(success=True, states=states)


@app.route("/api/play/pi-state", methods=["GET"])
def get_pi_state():
    """?system=&rom=&path=. One of the game's RetroArch save states, unpacked
    to what the emulator core loads. The file itself is only read."""
    system_name, rom_path = request.args.get("system", ""), strip_dot_slash(request.args.get("rom", ""))
    rom_file, _ = _playable_rom(system_name, rom_path)
    wanted = request.args.get("path", "")
    record = next((s for s in _retroarch_states(system_name, rom_path) if s['path'] == wanted), None) if rom_file else None
    if not record:
        return jsonify(success=False, error="No such save state"), 404
    path = save_finder.resolve_path(record['root'], wanted)
    try:
        data = pi_states.snapshot(path)
    except (OSError, ValueError) as e:
        return jsonify(success=False, error=str(e)), 400
    return send_file(BytesIO(data), mimetype='application/octet-stream', max_age=0)


@app.route("/api/play/pi-state", methods=["PUT"])
def put_pi_state():
    """?system=&rom=&profile=&slot=auto|0-99. Body: the browser emulator's state.
    Writes it where RetroArch on the Pi looks for the person's save state for
    this game (the auto state, or a numbered slot), so the game can be carried
    on there; RetroArch loads it if it runs the same core. A state already in
    that place is copied to the save backups folder first."""
    system_name, rom_path = request.args.get("system", ""), strip_dot_slash(request.args.get("rom", ""))
    profile, slot = request.args.get("profile", ""), request.args.get("slot", "auto")
    rom_file, _ = _playable_rom(system_name, rom_path)
    if not rom_file or not _owner(profile):
        return jsonify(success=False, error="Unknown game or person"), 404
    if slot != 'auto' and not (slot.isdigit() and int(slot) < 100):
        return jsonify(success=False, error="The slot is auto, or a number up to 99"), 400
    data = request.get_data(cache=False)
    if not data or len(data) > MAX_STATE_BYTES:
        return jsonify(success=False, error="The save state is empty or too large"), 400
    made_by, _ = pi_states.identify(pi_states._core_block(data)[:16])
    stem = Path(rom_path).stem
    name = f"{stem}.state.auto" if slot == 'auto' else f"{stem}.state{int(slot) or ''}"
    # Beside the person's other states for the game, wherever those are kept
    profile = _whose(profile)
    existing = [s for s in _retroarch_states(system_name, rom_path) if s['profile'] == profile]
    folder = (save_finder.resolve_path(existing[0]['root'], existing[0]['path']).parent if existing
              else _states_folder(system_name, rom_path, profile))
    target = folder / name
    backup = None
    try:
        if target.is_file():
            kept = SAVE_BACKUP_BASE / 'browser-play' / time.strftime('%Y%m%d-%H%M%S') / _kept_as(target, states=True)
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, kept)
            backup = str(kept.relative_to(SAVE_BACKUP_BASE))
        folder.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.part")
        tmp.write_bytes(data)
        tmp.replace(target)
        # A screenshot from before would show the wrong moment
        (target.with_name(target.name + '.png')).unlink(missing_ok=True)
    except OSError as e:
        logger.exception("Couldn't write a save state for the Pi")
        return jsonify(success=False, error=f"Couldn't write the save state: {e}"), 500
    # Which core the person's other states for this game were made with, to warn about a mismatch
    others = {pi_states.describe(save_finder.resolve_path(s['root'], s['path']))[0] for s in existing
              if save_finder.resolve_path(s['root'], s['path']) != target.resolve()}
    others.discard(None)
    return jsonify(success=True, file=name, made_by=made_by, backup=backup, pi_cores=sorted(others))



# --- RetroArch's save states, carried between the Pi and a phone (android/) ---
# The phone app keeps a person's states for a game the same on both: these are
# the files as RetroArch wrote them, not unpacked.

# How a state says which core made it (backend/pi_states.py) -> the RetroArch
# cores, by their file names, that load it (a name ending "_": any that start with it)
_STATE_CORES = {
    'Genesis Plus GX': ('genesis_plus_gx',), 'Nestopia': ('nestopia',), 'Snes9x': ('snes9x',), 'PCSX ReARMed': ('pcsx_rearmed',),
    'Mupen64Plus': ('mupen64plus_next', 'mupen64plus_next_gles2', 'mupen64plus_next_gles3'), 'DeSmuME': ('desmume',),
    'mGBA': ('mgba',), 'Beetle (Mednafen)': ('mednafen_',),
}
_state_sums = {}   # (path, modified, size) -> sha1


def _state_name(rom_path, record):
    """The name RetroArch gives a game's state: "<rom>.state.auto", "<rom>.state" (slot 0), "<rom>.state3"."""
    stem = Path(strip_dot_slash(rom_path)).stem
    return f"{stem}.state.auto" if record['kind'] == 'auto' else f"{stem}.state{record['slot'] or ''}"


def _phone_states(system_name, rom_path, profile):
    """A person's RetroArch states for a game, by the name RetroArch gives each
    (the newest, if two folders hold the same slot): {name: (record, file)}."""
    states = {}
    for record in _retroarch_states(system_name, rom_path):   # newest first
        path = save_finder.resolve_path(record['root'], record['path']) if record['profile'] == _whose(profile) else None
        if path and path.is_file():
            states.setdefault(_state_name(rom_path, record), (record, path))
    return states


def _fits(made_by, core):
    """Whether a core loads a state: True, False, or None when the state doesn't say what made it."""
    cores = _STATE_CORES.get(made_by)
    if not cores or not core:
        return None
    return any(core.startswith(c) if c.endswith('_') else core == c for c in cores)


@app.route("/api/play/phone-states", methods=["GET"])
def list_phone_states():
    """?system=&rom=&profile=&core=. The person's RetroArch save states for the
    game: [{name, label, modified (seconds), size, sha1, made_by, fits}].
    `fits` is whether `core` (RetroArch's name for it) loads the state."""
    system_name, rom_path = request.args.get("system", ""), strip_dot_slash(request.args.get("rom", ""))
    profile = request.args.get("profile", "")
    if not _in_library(system_name, rom_path) or not _owner(profile):
        return jsonify(success=False, error="Unknown game or person"), 404
    states = []
    for name, (record, path) in sorted(_phone_states(system_name, rom_path, profile).items()):
        try:
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            if key not in _state_sums:
                digest = hashlib.sha1()
                with open(path, 'rb') as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b''):
                        digest.update(chunk)
                _state_sums[key] = digest.hexdigest()
        except OSError:
            continue
        made_by, _ = pi_states.describe(path)
        states.append({'name': name, 'label': record['label'], 'modified': int(stat.st_mtime), 'size': stat.st_size,
                       'sha1': _state_sums[key], 'made_by': made_by, 'fits': _fits(made_by, request.args.get("core", ""))})
    return jsonify(success=True, states=states)


@app.route("/api/play/phone-state", methods=["GET"])
def get_phone_state():
    """?system=&rom=&profile=&name=. One of those states, as RetroArch wrote it."""
    system_name, rom_path = request.args.get("system", ""), strip_dot_slash(request.args.get("rom", ""))
    found = _phone_states(system_name, rom_path, request.args.get("profile", "")).get(request.args.get("name", "")) if _in_library(system_name, rom_path) else None
    if not found:
        return jsonify(success=False, error="No such save state"), 404
    return send_file(found[1], mimetype='application/octet-stream', max_age=0)


@app.route("/api/play/phone-state", methods=["PUT"])
def put_phone_state():
    """?system=&rom=&profile=&name=&modified=. Body: a state as RetroArch wrote
    it on the phone, kept as the person's state of that name (and given the
    phone's date for it). The one it replaces is copied to the save backups folder."""
    system_name, rom_path = request.args.get("system", ""), strip_dot_slash(request.args.get("rom", ""))
    profile, name = request.args.get("profile", ""), request.args.get("name", "")
    if not _in_library(system_name, rom_path) or not _owner(profile):
        return jsonify(success=False, error="Unknown game or person"), 404
    stem = Path(rom_path).stem
    if not name.startswith(stem + '.state') or not re.fullmatch(r'\.state(\d{0,2}|\.auto)', name[len(stem):]):
        return jsonify(success=False, error="Not a save state's name for this game"), 400
    data = request.get_data(cache=False)
    if not data or len(data) > MAX_STATE_BYTES:
        return jsonify(success=False, error="The save state is empty or too large"), 400
    states = _phone_states(system_name, rom_path, profile)
    # Where the person's state of that name is; else beside their others; else their folder
    # for the system (or beside the game, where saves are kept there)
    profile = _whose(profile)
    target = (states[name][1] if name in states
              else (next(iter(states.values()))[1].parent if states else _states_folder(system_name, rom_path, profile)) / name)
    backup = None
    try:
        if target.is_file():
            kept = SAVE_BACKUP_BASE / 'phone-play' / time.strftime('%Y%m%d-%H%M%S') / _kept_as(target, states=True)
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, kept)
            backup = str(kept.relative_to(SAVE_BACKUP_BASE))
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.part")
        tmp.write_bytes(data)
        tmp.replace(target)
        modified = request.args.get("modified", "")
        if modified.isdigit():
            os.utime(target, (int(modified), int(modified)))
        # A screenshot from before would show the wrong moment
        (target.with_name(target.name + '.png')).unlink(missing_ok=True)
    except OSError as e:
        logger.exception("Couldn't write a save state from the phone")
        return jsonify(success=False, error=f"Couldn't write the save state: {e}"), 500
    return jsonify(success=True, backup=backup, sha1=hashlib.sha1(data).hexdigest())
