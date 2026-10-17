"""
What's running in the background, for the strip under the header on every
page: the background scrape, the ROM check, the series matching and the fetching of
LaunchBox's list of games, each with its
progress, and for a little while after it ends, how it went.
"""

from flask import jsonify
from datetime import datetime
import time
from backend.core import app, launchbox_index
from backend.routes.accounts import is_admin
from backend.routes.romindex import rom_index
from backend.routes.scraping import scrape_queue
from backend.routes.series import series_index

# A task that has ended is still listed for this long, to say how it went
FINISHED_FOR = 45


def _seconds_since(finished):
    """finished: an ISO time (the scrape, the ROM check) or a timestamp (series)."""
    if not finished:
        return None
    try:
        then = finished if isinstance(finished, (int, float)) else datetime.fromisoformat(finished).timestamp()
    except ValueError:
        return None
    return max(0, time.time() - then)


def _current(status):
    current = status.get('current')
    if not isinstance(current, dict):
        return current or None
    return ' · '.join(part for part in (current.get('name'), current.get('system_name')) if part) or None


def _count(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one)}"


def _scrape():
    s = scrape_queue.snapshot()
    parts = [f"{len(s['applied'])} filled", f"{len(s['review'])} to review"]
    if s['failed']:
        parts.append(f"{len(s['failed'])} failed")
    return dict(key='scrape', tool='scrape', label='Background scrape', running=s['running'], stopping=s['stopping'],
                done=s['done'], total=s['total'], current=_current(s), finished=_seconds_since(s['finished']),
                summary=', '.join(parts), problem=s['stopped_reason'] if s['stopped_reason'] != 'Stopped' else None,
                stopped=s['stopped_reason'] == 'Stopped')


def _rom_check():
    s = rom_index.snapshot()
    return dict(key='roms', tool='roms', label='ROM check', running=s['running'], stopping=s['stopping'],
                done=s['done'], total=s['total'], current=_current(s), finished=_seconds_since(s['finished']),
                summary=f"{_count(s['done'], 'file', 'files')} checked", problem=s['stopped_reason'] if s['stopped_reason'] != 'Stopped' else None,
                stopped=s['stopped_reason'] == 'Stopped')


def _series():
    s = dict(series_index.progress)
    return dict(key='series', tool='series', label='Series matching', running=s['running'], stopping=False,
                done=s['done'], total=s['total'], current=s.get('step') or None, finished=_seconds_since(s.get('finished')),
                summary='Series are up to date', problem=s.get('error'), stopped=False)


def _launchbox():
    s = dict(launchbox_index.progress)
    downloading = s['step'] == 'Downloading'
    return dict(key='launchbox', tool='settings', label="LaunchBox's list of games", running=s['running'], stopping=False,
                done=s['done'], total=s['total'], finished=_seconds_since(s['finished']),
                current=f"{s['step']}: {s['done']} {'MB' if downloading else 'games'}" if s['step'] else None,
                summary="LaunchBox's pictures are ready to use", problem=s['error'], stopped=False)


@app.route("/api/tasks", methods=["GET"])
def background_tasks():
    """The background jobs that are running, or ended in the last FINISHED_FOR
    seconds: [{key, tool, label, running, stopping, done, total, current,
    finished (seconds ago), summary, problem, stopped}]. For admins; anyone else
    gets none."""
    if not is_admin():
        return jsonify(success=True, tasks=[])
    tasks = [task for task in (_scrape(), _rom_check(), _series(), _launchbox())
             if task['running'] or (task['finished'] is not None and task['finished'] <= FINISHED_FOR)]
    return jsonify(success=True, tasks=tasks)
