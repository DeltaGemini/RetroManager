"""
RetroManager Backend API
Flask application providing REST API for EmulationStation metadata management.

The app and everything shared are made in backend/core.py; importing the route
modules below attaches their routes to it. Run with gunicorn backend.app:app.
"""

import os

from backend.core import app
from backend.routes import (  # noqa: F401 (imported for their routes)
    accounts,
    setup,
    pages,
    systems,
    games,
    views,
    backups,
    importing,
    saves,
    media,
    scraping,
    settings,
    achievements,
    sources,
    romindex,
    collections,
    play,
    phone,
    series,
    console,
    mix,
    tasks,
    storage,
    duplicates,
)

# Not when a test imports the app
if os.environ.get("RETROMANAGER_NO_BACKGROUND") != "1":
    romindex.start_background_work()

if __name__ == "__main__":
    # For development. The container runs gunicorn (see the Dockerfile). The
    # debugger lets anyone who can reach the port run code, so it's only on
    # when asked for.
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
