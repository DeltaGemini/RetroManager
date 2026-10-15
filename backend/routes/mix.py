"""
Generating Mix pictures from a game's other media: what can be made, previews
made in the background, and committing the approved ones (see backend/mix_jobs.py).
"""

from flask import jsonify, send_file
import os
from backend.mix_generator import MixError
from backend.mix_jobs import DEFAULT_MAX_AGE_HOURS, DEFAULT_WORKERS, MixJobs
from backend.core import (
    _game_moved_hooks,
    _request_json,
    app,
    DATA_DIR,
    gamelist_mgr,
    logger,
    MEDIA_BASE,
    mix_provenance,
    ROMS_BASE,
    scanner,
)


def _number(name, default, kind):
    try:
        return kind(os.environ.get(name, default))
    except ValueError:
        return default
mix_jobs = MixJobs(DATA_DIR, scanner, gamelist_mgr, ROMS_BASE, MEDIA_BASE, mix_provenance,
                   workers=_number("MIX_WORKERS", DEFAULT_WORKERS, int),
                   max_age_hours=_number("MIX_STAGING_HOURS", DEFAULT_MAX_AGE_HOURS, float))
_game_moved_hooks.append(mix_provenance.game_moved)


def _selection(data):
    """Which games a request is about: games ([{system, rom_path}]), or
    system/systems (their games without a Mix), or neither (every system's).
    With generated, the games whose Mix was generated instead, to make them again."""
    games = data.get("games")
    if games is not None:
        games = [g for g in games if isinstance(g, dict)] if isinstance(games, list) else []
    systems = data.get("systems") or ([data["system"]] if data.get("system") else None)
    return dict(systems=systems, games=games, template=data.get("template") or None, options=data.get("options"),
                generated=data.get("generated") is True)


def _no_job():
    return jsonify(success=False, error="That set of previews is gone. Generate them again."), 404


@app.route("/api/mix/templates", methods=["GET"])
def mix_templates():
    """The layouts a Mix can be generated with."""
    templates = mix_jobs.templates()
    return jsonify(success=True, default=mix_jobs.default_template("", templates), templates=[
        {'name': t['name'], 'label': t.get('label') or t['name'], 'version': t.get('version', 1),
         'canvas': t['canvas'], 'roles': list(t['elements'])} for t in templates.values()])


@app.route("/api/mix/inventory", methods=["POST"])
def mix_inventory():
    """Body: {system | systems | games: [{system, rom_path}], template?, options?,
    generated?: true}. What generating would make, per system and per game.
    Writes nothing."""
    try:
        return jsonify(success=True, **mix_jobs.inventory(**_selection(_request_json())))
    except MixError as e:
        return jsonify(success=False, error=str(e)), 400
    except Exception as e:
        logger.exception("Error building the Mix inventory")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/mix/jobs", methods=["GET"])
def mix_job_list():
    """Sets of previews still around, newest first (without their games)."""
    return jsonify(success=True, jobs=mix_jobs.list_jobs())


@app.route("/api/mix/jobs", methods=["POST"])
def mix_job_start():
    """Body as for the inventory. Starts making previews in the staging folder."""
    try:
        return jsonify(success=True, job=mix_jobs.start(**_selection(_request_json())))
    except MixError as e:
        return jsonify(success=False, error=str(e)), 400
    except Exception as e:
        logger.exception("Error starting Mix previews")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/mix/jobs/<job_id>", methods=["GET"])
def mix_job_status(job_id):
    job = mix_jobs.get(job_id)
    return jsonify(success=True, job=job) if job else _no_job()


@app.route("/api/mix/jobs/<job_id>", methods=["DELETE"])
def mix_job_discard(job_id):
    """Throw a set of previews away. The library isn't touched."""
    return jsonify(success=True) if mix_jobs.discard(job_id) else _no_job()


@app.route("/api/mix/preview/<job_id>/<int:index>", methods=["GET"])
def mix_preview(job_id, index):
    path = mix_jobs.preview_file(job_id, index)
    if not path:
        return jsonify(error="Not found"), 404
    return send_file(path, mimetype="image/png", max_age=0)


@app.route("/api/mix/jobs/<job_id>/regenerate", methods=["POST"])
def mix_job_regenerate(job_id):
    """Body: {items: [{index, template?, options?}]}. options: box, media, wheel
    (false leaves it out), box_type ('3d' | '2d'), screenshot ('screenshot' | 'title')."""
    items = _request_json().get("items")
    if not isinstance(items, list) or not items:
        return jsonify(success=False, error="Say which previews to make again"), 400
    try:
        job = mix_jobs.regenerate(job_id, items)
    except MixError as e:
        return jsonify(success=False, error=str(e)), 400
    return jsonify(success=True, job=job) if job else _no_job()


@app.route("/api/mix/jobs/<job_id>/commit", methods=["POST"])
def mix_job_commit(job_id):
    """Body: {approve: [index...], reject?: [index...], overwrite?: bool}. Puts
    the approved previews in the library. A Mix that's already there and wasn't
    generated is only replaced with overwrite; what's replaced is backed up first."""
    data = _request_json()
    approve = data.get("approve")
    if not isinstance(approve, list):
        return jsonify(success=False, error="Say which previews to commit"), 400
    try:
        result = mix_jobs.commit(job_id, approve, overwrite=data.get("overwrite") is True, reject=data.get("reject"))
    except Exception as e:
        logger.exception("Error committing Mix pictures")
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True, **result, job=mix_jobs.get(job_id)) if result is not None else _no_job()
