"""
Settings: accounts, keys and scraping options, kept in DATA_PATH/settings.json.
"""

from flask import jsonify
from backend.core import _request_json, app, apply_settings, logger, settings

# -----------------------------------------------------------------------------
# Settings: accounts, keys and scraping options, kept in DATA_PATH/settings.json
# -----------------------------------------------------------------------------
@app.route("/api/settings", methods=["GET"])
def get_settings():
    """The settings, in groups, for the Settings panel. Passwords and keys are
    never sent: a secret field only says whether it's set."""
    return jsonify(success=True, groups=settings.describe())


@app.route("/api/settings", methods=["PUT"])
def put_settings():
    """Body: {values: {key: value}}. Saves the settings given and applies them
    straight away; a key left out is unchanged and "" clears one."""
    values = _request_json().get("values")
    if not isinstance(values, dict):
        return jsonify(success=False, error="Missing values"), 400
    try:
        changed = settings.update(values)
    except OSError as e:
        logger.exception("Couldn't save settings")
        return jsonify(success=False, error=f"Couldn't save settings: {e}"), 500
    apply_settings()
    return jsonify(success=True, changed=changed, groups=settings.describe())
