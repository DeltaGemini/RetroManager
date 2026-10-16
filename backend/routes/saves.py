"""
Saves and save states: per game, play history, sync conflicts and zipped backups.
"""

from flask import jsonify, request, send_file
from datetime import datetime
import shutil
import os
from pathlib import Path
from io import BytesIO
import re
from backend.name_style import style_name
from backend.media_index import strip_dot_slash
from backend.media_index import title_key
import threading
import zipfile
from backend.core import (
    _system_path_or_none,
    app,
    logger,
    SAVE_BACKUP_BASE,
    save_finder,
    SAVE_PROFILES,
    scanner,
)

# -----------------------------------------------------------------------------
# Saves and save states
# -----------------------------------------------------------------------------
@app.route("/api/systems/<system_name>/saves", methods=["GET"])
def get_game_saves(system_name):
    """?rom=<rom path>. In-game saves and save states for one game, newest first,
    each with the person ("profile") it belongs to, or "shared"."""
    if not _system_path_or_none(system_name):
        return jsonify(success=False, error="Unknown system"), 404
    rom_path = request.args.get("rom")
    if not rom_path:
        return jsonify(success=False, error="Missing rom"), 400
    try:
        return jsonify(
            success=True,
            saves=save_finder.find(system_name, strip_dot_slash(rom_path)),
            profiles=SAVE_PROFILES,
            available=save_finder.available(),
        )
    except Exception as e:
        logger.exception("Error listing saves")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/save-screenshot/<root_name>/<path:rel_path>", methods=["GET"])
def get_save_screenshot(root_name, rel_path):
    """The .png screenshot RetroArch stores next to a save state."""
    path = save_finder.screenshot_path(root_name, rel_path)
    if not path:
        return jsonify(error="Not found"), 404
    return send_file(path, mimetype="image/png", max_age=3600)


def _match_save_records(records):
    """Attach the game each save belongs to ('game': {system, full_name, rom_path,
    name, box2d, playcount, lastplayed}). Files in a system folder match that
    system's games; files in emulator-named folders match any system, if only one."""
    lookups = {}
    for system in scanner.discover_systems():
        try:
            games = scanner.get_games_for_system(system.name)
        except Exception:
            continue
        table = {}
        for g in games:
            info = {'system': system.name, 'full_name': system.get_full_name(), 'rom_path': strip_dot_slash(g.path),
                    'name': (g.name or '').strip(), 'box2d': g.box2d or g.screenshot, 'playcount': g.playcount,
                    'lastplayed': g.lastplayed}
            stem = Path(g.path).stem
            table.setdefault(stem.lower(), info)
            table.setdefault(title_key(stem), info)
            # "Legend of Zelda - X, The" and "The Legend of Zelda - X" alike
            table.setdefault(title_key(style_name(stem)), info)
        lookups[system.name] = table
    for r in records:
        base = re.sub(r'\.\d+$', '', r['base'])  # "Croc.1" (a numbered copy)
        keys = (base.lower(), title_key(base), title_key(style_name(base)))
        if r['system'] in lookups:
            r['game'] = next((lookups[r['system']][k] for k in keys if k in lookups[r['system']]), None)
        else:
            hits = {id(t[k]): t[k] for t in lookups.values() for k in keys if k in t}
            r['game'] = next(iter(hits.values())) if len(hits) == 1 else None
    return records


@app.route("/api/play-history", methods=["GET"])
def play_history():
    """Per game: when it was last saved and by whom, from the saves and savestates
    folders (and play counts if EmulationStation writes them)."""
    try:
        records = _match_save_records(save_finder.scan_all())
        games = {}
        unmatched = 0
        for r in records:
            if not r.get('game'):
                unmatched += 1
                continue
            g = r['game']
            key = (g['system'], g['rom_path'])
            entry = games.setdefault(key, {**g, 'last': 0, 'last_by': None, 'profiles': {}, 'files': 0})
            entry['files'] += 1
            if r['mtime'] > entry['last']:
                entry['last'], entry['last_by'] = r['mtime'], r['profile']
            entry['profiles'][r['profile']] = max(entry['profiles'].get(r['profile'], 0), r['mtime'])
        # Games EmulationStation counted but that have no saves
        for system in scanner.discover_systems():
            for g in scanner.get_games_for_system(system.name):
                if g.playcount and (system.name, strip_dot_slash(g.path)) not in games:
                    games[(system.name, strip_dot_slash(g.path))] = {
                        'system': system.name, 'full_name': system.get_full_name(), 'rom_path': strip_dot_slash(g.path),
                        'name': (g.name or '').strip(), 'box2d': g.box2d or g.screenshot, 'playcount': g.playcount,
                        'lastplayed': g.lastplayed, 'last': 0, 'last_by': None, 'profiles': {}, 'files': 0}
        items = sorted(games.values(), key=lambda e: e['last'], reverse=True)
        return jsonify(success=True, people=SAVE_PROFILES, games=items, unmatched=unmatched,
                       available=save_finder.available())
    except Exception as e:
        logger.exception("Error building play history")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/save-conflicts", methods=["GET"])
def save_conflicts():
    """Saves Syncthing kept more than one version of, with each version's details."""
    try:
        records = save_finder.scan_all()
        groups = save_finder.conflicts(records)
        _match_save_records([v for g in groups for v in g['versions']])
        for g in groups:
            g['game'] = next((v['game'] for v in g['versions'] if v.get('game')), None)
        return jsonify(success=True, conflicts=groups, writable=_saves_writable())
    except Exception as e:
        logger.exception("Error listing save conflicts")
        return jsonify(success=False, error=str(e)), 500


def _saves_writable():
    return all(os.access(p, os.W_OK) for p in save_finder.roots.values() if p.is_dir())


def _move_to_backup(source: Path, root_name: str, rel: str, stamp: str):
    target = SAVE_BACKUP_BASE / 'conflicts' / stamp / root_name / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))


# -----------------------------------------------------------------------------
# Too many save states: keep each person's newest few of each game
# -----------------------------------------------------------------------------

def _thinning(keep):
    """What keeping each person's `keep` newest save states of each game would
    move: {groups: [{profile, folder, game, total, move: [records]}], files,
    bytes}. A game's auto state is never moved (RetroArch loads it by itself),
    nor are the browser's own states or Syncthing's conflict copies."""
    groups = {}
    for record in save_finder.scan_all():
        if record['kind'] not in ('state', 'auto') or record['conflict'] or record['folder'] == 'Browser':
            continue
        groups.setdefault((record['root'], record['profile'], record['folder'], record['base']), []).append(record)
    out, files, size = [], 0, 0
    for (root, profile, folder, base), records in groups.items():
        records.sort(key=lambda r: r['mtime'], reverse=True)
        move = [r for r in records[keep:] if r['kind'] != 'auto']
        if not move:
            continue
        files += len(move)
        size += sum(r['size'] for r in move)
        out.append({'root': root, 'profile': profile, 'folder': folder, 'game': base, 'total': len(records),
                    'move': [{k: r[k] for k in ('root', 'path', 'screenshot', 'size', 'modified', 'label')} for r in move]})
    out.sort(key=lambda g: -len(g['move']))
    return {'groups': out, 'files': files, 'bytes': size}


def _keep_count():
    try:
        keep = int(request.args.get("keep") or (request.get_json(silent=True) or {}).get("keep") or 10)
    except (TypeError, ValueError):
        keep = 10
    return max(1, min(keep, 999))


def _renumbering():
    """The numbered save states whose slot isn't yet their place in time: for
    each person's states of each game (in one folder), oldest first, slots 1,
    2, 3... (the newest highest, so RetroArch's "next slot" carries on after
    it). Auto states keep their name. [(record, new name)]."""
    groups = {}
    for record in save_finder.scan_all():
        if record['kind'] != 'state' or record['conflict'] or record['folder'] == 'Browser':
            continue
        groups.setdefault((record['root'], record['profile'], record['folder'], record['base']), []).append(record)
    renames = []
    for records in groups.values():
        records.sort(key=lambda r: (r['mtime'], r['slot'] or 0))
        for slot, record in enumerate(records, start=1):
            name = f"{record['base']}.state{slot}"
            if record['file'] != name:
                renames.append((record, name))
    return renames


def _renumber(renames=None):
    """Gives the states _renumbering finds (or those of them given) their new slots (and their screenshots
    theirs). In two steps, so a state never lands on a name another still has.
    Returns (how many, problems)."""
    renames, staged, problems = (_renumbering() if renames is None else renames), [], []
    for record, name in renames:
        source = save_finder.resolve_path(record['root'], record['path'])
        shot = save_finder.resolve_path(record['root'], record['screenshot']) if record['screenshot'] else None
        if not source or not source.is_file():
            continue
        try:
            temporary = source.with_name(f".renumbering-{source.name}")
            source.rename(temporary)
            shot_temporary = None
            if shot and shot.is_file():
                shot_temporary = shot.with_name(f".renumbering-{shot.name}")
                shot.rename(shot_temporary)
            staged.append((temporary, shot_temporary, source.with_name(name)))
        except OSError as e:
            problems.append(f"{record['path']}: {e}")
    done = 0
    for temporary, shot_temporary, target in staged:
        try:
            temporary.rename(target)
            if shot_temporary:
                shot_temporary.rename(target.with_name(target.name + '.png'))
            done += 1
        except OSError as e:
            problems.append(f"{target.name}: {e}")
    return done, problems


@app.route("/api/save-states/renumber", methods=["GET"])
def preview_renumbering():
    """How many numbered save states would get new slot numbers (oldest 1, 2, 3...)."""
    return jsonify(success=True, states=len(_renumbering()))


@app.route("/api/save-states/renumber", methods=["POST"])
def renumber_save_states():
    """Numbers each person's save states of each game 1, 2, 3... oldest first."""
    if not _saves_writable():
        return jsonify(success=False, error="The save states folder can't be written to"), 400
    done, problems = _renumber()
    if problems:
        logger.warning(f"Renumbering save states: {len(problems)} problems, e.g. {problems[0]}")
    return jsonify(success=not problems, renumbered=done, problems=problems[:20])


@app.route("/api/save-states/thin", methods=["GET"])
def preview_thinning():
    """?keep=10. Which save states keeping each person's newest `keep` of each game would move."""
    return jsonify(success=True, keep=_keep_count(), **_thinning(_keep_count()))


@app.route("/api/save-states/thin", methods=["POST"])
def thin_save_states():
    """{keep, renumber}: moves each person's older save states of each game, beyond the
    newest `keep` (and never an auto state), with their screenshots, to
    save-backups/thinned-states/<time>/, under the paths they had. With
    renumber, those games' remaining states are then numbered 1, 2, 3...
    oldest first."""
    keep = _keep_count()
    if not _saves_writable():
        return jsonify(success=False, error="The save states folder can't be written to"), 400
    plan = _thinning(keep)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    moved, problems = 0, []
    for group in plan['groups']:
        for record in group['move']:
            for rel in (record['path'], record['screenshot']):
                source = save_finder.resolve_path(record['root'], rel) if rel else None
                if not source or not source.is_file():
                    continue
                target = SAVE_BACKUP_BASE / 'thinned-states' / stamp / record['root'] / rel
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
                    moved += rel == record['path']
                except OSError as e:
                    problems.append(f"{rel}: {e}")
    # ...and, if asked, what's left of those games numbered 1, 2, 3... again, oldest first
    renumbered = 0
    if (request.get_json(silent=True) or {}).get("renumber"):
        thinned = {(g['root'], g['profile'], g['folder'], g['game']) for g in plan['groups']}
        renumbered, trouble = _renumber([(r, n) for r, n in _renumbering() if (r['root'], r['profile'], r['folder'], r['base']) in thinned])
        problems += trouble
    if problems:
        logger.warning(f"Thinning save states: {len(problems)} problems, e.g. {problems[0]}")
    return jsonify(success=not problems or moved > 0, moved=moved, renumbered=renumbered, backup=f"thinned-states/{stamp}", problems=problems[:20])


@app.route("/api/save-conflicts/resolve", methods=["POST"])
def resolve_save_conflict():
    """Body: {id, keep: path of the version to keep}. The other versions move to
    SAVE_BACKUP_PATH/conflicts/<time>/; a kept conflict copy takes the original's
    name so the emulator loads it. Screenshots move with their states."""
    data = request.get_json(silent=True) or {}
    group = next((g for g in save_finder.conflicts() if g['id'] == data.get('id')), None)
    if not group:
        return jsonify(success=False, error="That conflict is gone. Reload the list."), 404
    keep = next((v for v in group['versions'] if v['path'] == data.get('keep')), None)
    if not keep:
        return jsonify(success=False, error="Pick one of the versions"), 400
    if not _saves_writable():
        return jsonify(success=False, error="The saves folders are mounted read-only. Remove :ro from them in docker-compose.yml."), 400
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    root = group['root']
    moved = []
    try:
        for v in group['versions']:
            if v['path'] == keep['path']:
                continue
            for rel in filter(None, (v['path'], v.get('screenshot'))):
                source = save_finder.resolve_path(root, rel)
                if source and source.is_file():
                    _move_to_backup(source, root, rel, stamp)
                    moved.append(rel)
        if keep['path'] != group['path']:
            for rel, target_rel in ((keep['path'], group['path']),
                                    (keep.get('screenshot'), group['path'] + '.png' if keep.get('screenshot') else None)):
                if not rel:
                    continue
                source, target = save_finder.resolve_path(root, rel), save_finder.resolve_path(root, target_rel)
                if source and target and source.is_file() and not target.exists():
                    source.rename(target)
        # The kept version becomes the newest, so "newer wins" syncs (the RetroPie's
        # rsync) don't bring back a copy you chose against
        kept = save_finder.resolve_path(root, group['path'])
        if kept and kept.is_file():
            os.utime(kept, None)
        return jsonify(success=True, moved=moved, backup=f"conflicts/{stamp}")
    except OSError as e:
        logger.exception("Error resolving save conflict")
        return jsonify(success=False, error=str(e), moved=moved), 500


def _zip_name(text):
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in text).strip("-")[:80] or "saves"


@app.route("/api/systems/<system_name>/saves/download", methods=["GET"])
def download_game_saves(system_name):
    """?rom=<path>. A zip of one game's saves and states (all people)."""
    rom = strip_dot_slash(request.args.get("rom", ""))
    if not _system_path_or_none(system_name) or not rom:
        return jsonify(success=False, error="Unknown system or ROM"), 404
    files = save_finder.find(system_name, rom)
    if not files:
        return jsonify(success=False, error="No saves for this game"), 404
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            for rel in filter(None, (f['path'], f.get('screenshot'))):
                path = save_finder.resolve_path(f['root'], rel)
                if path and path.is_file():
                    zf.write(path, f"{f['root']}/{rel}")
    buffer.seek(0)
    name = f"{_zip_name(Path(rom).stem)}-saves-{datetime.now().strftime('%Y%m%d')}.zip"
    return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=name)
_save_backup_job = {"running": False, "scope": None, "done": 0, "total": 0, "error": None, "file": None}
_save_backup_lock = threading.Lock()


def _run_save_backup(system, include_states, target):
    try:
        records = save_finder.scan_all()
        if system:
            _match_save_records(records)
            records = [r for r in records if r['system'] == system or (r.get('game') or {}).get('system') == system]
        if not include_states:
            records = [r for r in records if r['kind'] == 'save']
        files = [(r['root'], rel) for r in records for rel in filter(None, (r['path'], r.get('screenshot')))]
        _save_backup_job.update(total=len(files))
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.part')
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, (root, rel) in enumerate(files):
                path = save_finder.resolve_path(root, rel)
                if path and path.is_file():
                    zf.write(path, f"{root}/{rel}")
                _save_backup_job['done'] = i + 1
        tmp.replace(target)
        _save_backup_job.update(file=target.name)
    except Exception as e:
        logger.exception("Save backup failed")
        _save_backup_job.update(error=str(e))
    finally:
        _save_backup_job['running'] = False


@app.route("/api/save-backups", methods=["GET"])
def list_save_backups():
    """Zipped save backups in SAVE_BACKUP_PATH/zips, newest first, and the current job."""
    folder = SAVE_BACKUP_BASE / 'zips'
    zips = []
    if folder.is_dir():
        for z in folder.glob('*.zip'):
            st = z.stat()
            zips.append({'name': z.name, 'size': st.st_size, 'modified': datetime.fromtimestamp(st.st_mtime).isoformat()})
    zips.sort(key=lambda z: z['modified'], reverse=True)
    return jsonify(success=True, backups=zips, job=_save_backup_job, folder_ok=_backup_folder_ok(),
                   saves_writable=_saves_writable())


def _backup_folder_ok():
    try:
        SAVE_BACKUP_BASE.mkdir(parents=True, exist_ok=True)
        return os.access(SAVE_BACKUP_BASE, os.W_OK)
    except OSError:
        return False


@app.route("/api/save-backups", methods=["POST"])
def create_save_backup():
    """Body: {system?: name (default everything), include_states?: bool}. Zips in the background."""
    data = request.get_json(silent=True) or {}
    system = data.get("system") or None
    if system and not _system_path_or_none(system):
        return jsonify(success=False, error="Unknown system"), 404
    if not _backup_folder_ok():
        return jsonify(success=False, error=f"Can't write to {SAVE_BACKUP_BASE}. Mount a folder there (see docker-compose.yml)."), 400
    with _save_backup_lock:
        if _save_backup_job['running']:
            return jsonify(success=False, error="A backup is already running"), 409
        include_states = bool(data.get("include_states", True))
        name = f"saves-{_zip_name(system or 'everything')}{'' if include_states else '-no-states'}-{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        _save_backup_job.update(running=True, scope=system or 'everything', done=0, total=0, error=None, file=None)
        threading.Thread(target=_run_save_backup, args=(system, include_states, SAVE_BACKUP_BASE / 'zips' / name),
                         daemon=True).start()
    return jsonify(success=True, name=name)


def _save_backup_file(name):
    path = (SAVE_BACKUP_BASE / 'zips' / name)
    if '/' in name or '\\' in name or not name.endswith('.zip') or not path.is_file():
        return None
    return path


@app.route("/api/save-backups/<name>", methods=["GET"])
def download_save_backup(name):
    path = _save_backup_file(name)
    if not path:
        return jsonify(success=False, error="Not found"), 404
    return send_file(path, mimetype="application/zip", as_attachment=True, download_name=name)


@app.route("/api/save-backups/<name>", methods=["DELETE"])
def delete_save_backup(name):
    path = _save_backup_file(name)
    if not path:
        return jsonify(success=False, error="Not found"), 404
    path.unlink()
    return jsonify(success=True)
