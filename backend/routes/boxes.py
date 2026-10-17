"""
Spines and 3D boxes made from a game's own pictures (backend/box_generator.py),
for Fill the gaps to offer beside the sources'.

/api/boxes/make          {system_name, rom_path, kind: box3d | boxside}: one made and
                         kept for a day in DATA_PATH/box-staging, to show and choose
/api/boxes/made/<token>  the made picture
Fill the gaps puts a chosen one in with /api/fill/apply ({kind: "made:<token>"}).
"""

import re
import time
import uuid
from pathlib import Path

from flask import jsonify, send_file
from PIL import Image

from backend.box_generator import BoxError, make_box3d, make_spine
from backend.core import _request_json, _system_path_or_none, app, DATA_DIR, logger, MEDIA_BASE, scanner
from backend.media_index import strip_dot_slash

STAGING = Path(DATA_DIR) / 'box-staging'
KEEP_HOURS = 24
MADE_KINDS = ('box3d', 'boxside')
_TOKEN = re.compile(r'^[0-9a-f]{32}$')
# Pillow's name for a picture's format -> the file extension it's kept with
PICTURE_TYPES = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp', 'GIF': '.gif'}


def made_file(token):
    """The made (or pasted, see fill.py's /api/fill/picture) picture a token names, or None."""
    if not isinstance(token, str) or not _TOKEN.match(token):
        return None
    return next((p for p in STAGING.glob(f'{token}.*') if p.suffix in PICTURE_TYPES.values()), None)


def clear_old():
    """Made and pasted pictures older than KEEP_HOURS (each time one is made, and nightly)."""
    cutoff = time.time() - KEEP_HOURS * 3600
    if not STAGING.is_dir():
        return
    for old in STAGING.glob('*.*'):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def _picture(rel):
    if not rel:
        return None
    try:
        return Image.open(Path(MEDIA_BASE) / rel).convert('RGBA')
    except (OSError, ValueError):
        return None


@app.route("/api/boxes/make", methods=["POST"])
def make_box():
    data = _request_json()
    system = data.get("system_name")
    rom_path = strip_dot_slash(data.get("rom_path"))
    kind = data.get("kind")
    if not _system_path_or_none(system) or not rom_path or kind not in MADE_KINDS:
        return jsonify(success=False, error="Missing or unknown system_name / rom_path / kind"), 400
    game = scanner.get_game_details(system, rom_path)
    if game is None:
        return jsonify(success=False, error="Game not found"), 404
    cover = _picture(game.box2d)
    title = game.name or Path(rom_path).stem
    try:
        if cover is None:
            raise BoxError("It needs a cover (Box 2D) to make one from")
        spine = _picture(game.boxside) if kind == 'box3d' else None
        made_spine = spine is None
        if spine is None:
            spine = make_spine(cover, _picture(game.wheel), title, system)
        picture = spine if kind == 'boxside' else make_box3d(cover, spine, system)
    except BoxError as e:
        return jsonify(success=False, error=str(e))
    except Exception as e:
        logger.exception(f"Couldn't make a {kind} for {system}/{rom_path}")
        return jsonify(success=False, error=f"It couldn't be made ({e})")
    STAGING.mkdir(parents=True, exist_ok=True)
    clear_old()
    token = uuid.uuid4().hex
    picture.save(STAGING / f'{token}.png', optimize=True)
    return jsonify(success=True, token=token, url=f"/api/boxes/made/{token}", made_spine=made_spine and kind == 'box3d')


@app.route("/api/boxes/made/<token>", methods=["GET"])
def made_box(token):
    path = made_file(token)
    if not path:
        return jsonify(success=False, error="That picture is gone: make or paste it again"), 404
    return send_file(path, max_age=3600)


def keep_picture(data: bytes):
    """A picture pasted or dropped in Fill the gaps, kept a day like a made one: (token, url).
    Raises ValueError if it isn't a picture."""
    import io
    try:
        with Image.open(io.BytesIO(data)) as picture:
            picture.verify()
            kind = picture.format
    except Exception:
        raise ValueError("That isn't a picture RetroManager can use (PNG, JPEG, WebP or GIF)")
    if kind not in PICTURE_TYPES:
        raise ValueError(f"A {kind} picture can't be used: PNG, JPEG, WebP or GIF")
    STAGING.mkdir(parents=True, exist_ok=True)
    clear_old()
    token = uuid.uuid4().hex
    # (".pasted": put in as the person's own, not as made here)
    (STAGING / f'{token}.pasted{PICTURE_TYPES[kind]}').write_bytes(data)
    return token, f"/api/boxes/made/{token}"
