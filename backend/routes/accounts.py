"""
Signing in, switching profile, and what each role may do (backend/accounts.py).

With login on, every /api/ request needs a signed-in profile, and a player's
may only read, plus the few changes that are theirs to make (their own play
status, saves and want list, and the shared favourites).
"""

import json
import re
import time
from pathlib import Path

from flask import g, jsonify, request, send_file

from backend.accounts import Accounts, NAME_RE
from backend.core import _request_json, app, DATA_DIR, library_state, logger, save_finder, SAVE_PROFILES, SAVES_BASE, SAVESTATES_BASE, saves_beside_roms
from backend.saves import SHARED

accounts = Accounts(DATA_DIR, SAVE_PROFILES)

COOKIE = 'rm_profile'
COOKIE_AGE = 400 * 86400
ONLY_ADMIN = "Only an admin can do that."
# What a player may change: (method, path pattern)
PLAYER_WRITES = [(method, re.compile(pattern)) for method, pattern in (
    ('PUT', r'^/api/play-status$'), ('PUT', r'^/api/favorite$'),
    ('PUT', r'^/api/play/(save|state|pi-state|phone-state)$'),
    ('PUT', r'^/api/series/(mark|platform)$'), ('POST', r'^/api/phone/played$'),
)]
# ...and what they may not even read
ADMIN_READS = re.compile(r'^/api/(settings|data-backups)\b')


def signed_in():
    """The profile this request is from, or None (also None with login off)."""
    if 'rm_profile' not in g:
        g.rm_profile = accounts.who(request.cookies.get(COOKIE)) if accounts.enabled else None
    return g.rm_profile


def person():
    """Whose play status, want list and so on this request works with: the
    signed-in profile, or None with login off (the one shared set)."""
    return signed_in()


def is_admin():
    """Whether this request may change the library: anyone with login off."""
    return not accounts.enabled or (signed_in() is not None and accounts.role(signed_in()) == 'admin')


@app.before_request
def guard():
    if not accounts.enabled:
        return None
    path = request.path
    if not path.startswith('/api/') or path.startswith('/api/accounts/') or path == '/api/health':
        return None
    me = signed_in()
    if me is None:
        return jsonify(success=False, error="Sign in first.", sign_in=True), 401
    if accounts.role(me) == 'admin':
        return None
    # A player's saves and save states are their own
    if path.startswith('/api/play/') and request.args.get('profile') not in (None, '', me):
        return jsonify(success=False, error="That's someone else's save."), 403
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        if ADMIN_READS.match(path):
            return jsonify(success=False, error=ONLY_ADMIN), 403
        return None
    if any(method == request.method and pattern.match(path) for method, pattern in PLAYER_WRITES):
        return None
    return jsonify(success=False, error=ONLY_ADMIN), 403


def _me():
    me = signed_in()
    return {
        'success': True, 'enabled': accounts.enabled, 'profile': me, 'role': accounts.role(me) if me else None,
        'admin': is_admin(), 'profiles': accounts.describe(),
        **(accounts.prefs(me) if me else {'prefs': {}, 'prefs_at': 0}),
    }


def _with_cookie(response, name):
    if name:
        response.set_cookie(COOKIE, accounts.token_for(name), max_age=COOKIE_AGE, httponly=True, samesite='Lax')
    else:
        response.delete_cookie(COOKIE)
    return response


@app.route("/api/accounts/me", methods=["GET"])
def accounts_me():
    """Whether login is on, who this device is signed in as, and the profiles
    (name, role, whether they have a PIN, photo) for the picker."""
    return jsonify(**_me())


@app.route("/api/accounts/login", methods=["POST"])
def accounts_login():
    """{profile, pin}: sign this device in as a profile. A player needs no PIN;
    an admin's is asked for every time."""
    data = _request_json()
    name = data.get("profile")
    if name not in accounts.people():
        return jsonify(success=False, error="Unknown profile"), 404
    if accounts.role(name) == 'admin':
        problem = accounts.check_pin(name, str(data.get("pin") or ''))
        if problem:
            return jsonify(success=False, error=problem, pin_needed=True), 403
    g.rm_profile = name
    return _with_cookie(jsonify(**_me()), name)


@app.route("/api/accounts/logout", methods=["POST"])
def accounts_logout():
    g.rm_profile = None
    return _with_cookie(jsonify(success=True), None)


@app.route("/api/accounts/prefs", methods=["PUT"])
def accounts_prefs():
    """{prefs: {key: value}}: the signed-in person's preferences (theme, sort
    orders, which picture...), so they follow them to another device."""
    me = signed_in()
    if not me:
        return jsonify(success=False, error="Sign in first."), 401
    try:
        return jsonify(success=True, prefs_at=accounts.set_prefs(me, _request_json().get("prefs") or {}))
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400


# --- Managing profiles (admins; anyone while login is off) ---

def _admin_only():
    return None if is_admin() else (jsonify(success=False, error=ONLY_ADMIN), 403)


def _make_folders(name):
    """A new person's saves folders."""
    for base in (SAVES_BASE, SAVESTATES_BASE):
        try:
            if base and Path(base).is_dir():
                (Path(base) / name).mkdir(exist_ok=True)
        except OSError as e:
            logger.warning(f"Couldn't make {base}/{name}: {e}")


def _shared_saves():
    """The saves and save states that are nobody's in particular (not in a
    person's folder): the save finder's records."""
    try:
        return [r for r in save_finder.scan_all() if r['profile'] == SHARED]
    except OSError:
        return []


def _hand_over(name):
    """Moves the shared saves and save states into a person's folders, each
    under the same path it had (saves/snes/Game.srm -> saves/<name>/snes/Game.srm),
    with a state's screenshot beside it. One the person already has is left where
    it is. What moved is listed in DATA_PATH/moved-saves/, to put it back by hand.
    Returns how many files moved."""
    moved = []
    for record in _shared_saves():
        root = Path(SAVES_BASE if record['root'] == 'saves' else SAVESTATES_BASE)
        for rel in (record['path'], record.get('screenshot')):
            if not rel:
                continue
            source, target = root / rel, root / name / rel
            try:
                if not source.is_file() or target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                moved.append({'root': record['root'], 'from': rel, 'to': f"{name}/{rel}"})
            except OSError as e:
                logger.warning(f"Couldn't move {source} to {name}: {e}")
    if moved:
        try:
            listed = DATA_DIR / 'moved-saves' / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}.json"
            listed.parent.mkdir(parents=True, exist_ok=True)
            listed.write_text(json.dumps(moved, indent=1))
        except OSError as e:
            logger.warning(f"Couldn't list the saves moved to {name}: {e}")
    return len(moved)


@app.route("/api/accounts/shared-saves", methods=["GET"])
def accounts_shared_saves():
    """How many saves and save states are nobody's in particular: {saves, states}.
    A new person can be given them (see below)."""
    # (kept beside the games, they're everyone's and stay so: there's nowhere for a person's own)
    if saves_beside_roms():
        return jsonify(success=True, saves=0, states=0, beside_roms=True)
    records = _shared_saves()
    return jsonify(success=True, saves=sum(1 for r in records if r['root'] == 'saves'),
                   states=sum(1 for r in records if r['root'] == 'savestates'), beside_roms=False)


@app.route("/api/accounts/people", methods=["POST"])
def accounts_add_person():
    """{name, take_shared}: a new profile, with its folders in saves/ and
    savestates/. With take_shared, the saves and save states that were shared
    until now are moved into them (`moved`: how many files); without it they
    stay shared."""
    refused = _admin_only()
    if refused:
        return refused
    data = _request_json()
    name = str(data.get("name") or '').strip()
    try:
        accounts.add_person(name)
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    _make_folders(name)
    moved = _hand_over(name) if data.get("take_shared") and not saves_beside_roms() else 0
    return jsonify(**_me(), moved=moved)


@app.route("/api/accounts/profile", methods=["PUT"])
def accounts_profile():
    """{name, role, pin}: change a profile's role, or its PIN (null removes it).
    Only what's given is changed."""
    refused = _admin_only()
    if refused:
        return refused
    data = _request_json()
    name = data.get("name")
    try:
        if "pin" in data:
            accounts.set_pin(name, None if data["pin"] in (None, '') else str(data["pin"]))
        if data.get("role"):
            accounts.set_role(name, data["role"])
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    # Changing your own PIN shouldn't sign you out of the device you did it on
    return _with_cookie(jsonify(**_me()), signed_in()) if signed_in() == name else jsonify(**_me())


@app.route("/api/accounts/enabled", methods=["PUT"])
def accounts_enabled():
    """{enabled, profile, pin}: switch login on or off. Switching it on signs
    this device in as the admin named (their PIN is checked), and what was
    shared until now (play statuses, the want list) becomes theirs."""
    refused = _admin_only()
    if refused:
        return refused
    data = _request_json()
    if not data.get("enabled"):
        accounts.set_enabled(False)
        return _with_cookie(jsonify(**_me()), None)
    name = data.get("profile")
    if name not in accounts.people() or accounts.role(name) != 'admin':
        return jsonify(success=False, error="Say which admin you are."), 400
    problem = accounts.check_pin(name, str(data.get("pin") or ''))
    if problem:
        return jsonify(success=False, error=problem), 403
    try:
        accounts.set_enabled(True)
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    library_state.adopt(name)
    try:
        from backend.routes.series import series_index
        series_index.adopt(name)
    except Exception:
        logger.exception("Couldn't hand the want list over")
    g.rm_profile = name
    return _with_cookie(jsonify(**_me()), name)


@app.route("/api/accounts/photo", methods=["POST"])
def accounts_set_photo():
    """A profile's photo (form: name, and file; no file removes it). Kept
    square and small in DATA_PATH/profiles/."""
    refused = _admin_only()
    if refused:
        return refused
    name = request.form.get("name", "")
    if name not in accounts.people() or not NAME_RE.match(name):
        return jsonify(success=False, error="Unknown profile"), 404
    upload = request.files.get("file")
    if not upload:
        accounts.set_photo(name, None)
        return jsonify(**_me())
    try:
        from PIL import Image, ImageOps
        with Image.open(upload.stream) as picture:
            picture = ImageOps.exif_transpose(picture).convert('RGB')
            picture = ImageOps.fit(picture, (256, 256))
            accounts.photo_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{name}-{int(time.time())}.jpg"
            picture.save(accounts.photo_dir / filename, 'JPEG', quality=88)
    except Exception as e:
        return jsonify(success=False, error=f"That picture couldn't be read: {e}"), 400
    for old in accounts.photo_dir.glob(f"{name}-*.jpg"):
        if old.name != filename:
            old.unlink(missing_ok=True)
    accounts.set_photo(name, filename)
    return jsonify(**_me())


@app.route("/api/accounts/photo/<filename>", methods=["GET"])
def accounts_photo(filename):
    if not re.match(r'^[A-Za-z0-9_\-]+\.jpg$', filename) or not (accounts.photo_dir / filename).is_file():
        return "Not found", 404
    return send_file(accounts.photo_dir / filename, mimetype='image/jpeg', max_age=30 * 86400)
