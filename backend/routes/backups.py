"""
Gamelist backups: make, list, compare, restore and prune.
"""

from flask import jsonify, request
from datetime import datetime
import shutil
from pathlib import Path
import re
from lxml import etree
from backend.media_index import strip_dot_slash
from backend.core import _system_path_or_none, app, gamelist_mgr, logger, ROMS_BASE

# Backup gamelist.xml endpoint
@app.route("/api/backup_gamelist", methods=["POST"])
def backup_gamelist():
    try:
        data = request.get_json()
        system = data.get("system")
        if not system:
            return jsonify(error="Missing system name"), 400

        gamelist_path = Path(ROMS_BASE) / system / "gamelist.xml"
        if not gamelist_path.exists():
            return jsonify(error=f"gamelist.xml not found for system: {system}"), 404

        # Create dated backup filename
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = gamelist_path.parent / f"gamelist_{now}.xml"
        shutil.copy2(gamelist_path, backup_path)

        return jsonify(success=True, backup=str(backup_path.name))
    except Exception as e:
        logger.exception("Error backing up gamelist.xml")
        return jsonify(error=str(e)), 500


# List gamelist.xml backups for a system
@app.route("/api/list_gamelist_backups", methods=["POST"])
def list_gamelist_backups():
    try:
        data = request.get_json()
        system = data.get("system")
        if not system:
            return jsonify(error="Missing system name"), 400
        system_dir = Path(ROMS_BASE) / system
        if not system_dir.exists():
            return jsonify(error=f"System directory not found: {system}"), 404
        backups = []
        for f in system_dir.glob("gamelist_*.xml"):
            backups.append(f.name)
        backups.sort(reverse=True)
        return jsonify(success=True, backups=backups)
    except Exception as e:
        logger.exception("Error listing gamelist backups")
        return jsonify(error=str(e)), 500


# Restore gamelist.xml from a backup
@app.route("/api/restore_gamelist_backup", methods=["POST"])
def restore_gamelist_backup():
    try:
        data = request.get_json()
        system = data.get("system")
        backup_file = data.get("backup")
        if not system or not backup_file:
            return jsonify(error="Missing system name or backup file"), 400
        backup_path = _gamelist_backup_path(system, backup_file)
        if not backup_path:
            return jsonify(error=f"Backup file not found: {backup_file}"), 404
        current_backup = gamelist_mgr.backup(system, ROMS_BASE)
        shutil.copy2(backup_path, backup_path.parent / "gamelist.xml")
        return jsonify(success=True, backup=current_backup)
    except Exception as e:
        logger.exception("Error restoring gamelist backup")
        return jsonify(error=str(e)), 500


def _gamelist_backup_path(system, name):
    """A gamelist copy in a system folder (gamelist_<date>.xml, gamelist.backup.xml,
    Syncthing conflict copies...), never gamelist.xml itself or anything outside."""
    system_dir = _system_path_or_none(system)
    if (not system_dir or not name or '/' in name or '\\' in name or name == 'gamelist.xml'
            or not name.lower().startswith('gamelist') or not name.lower().endswith('.xml')):
        return None
    path = system_dir / name
    return path if path.is_file() else None


def _backup_kind(name):
    if 'sync-conflict' in name:
        return 'Sync conflict copy'
    if re.match(r'^gamelist_\d{8}_\d{6}\.xml$', name):
        return 'Backup'
    return 'Other copy'


def _read_entries(path):
    """{rom path (lowercase): {'path', field: text}} for a gamelist file."""
    entries = {}
    root = etree.parse(str(path)).getroot()
    for game in root.iter('game'):
        rom = strip_dot_slash(game.findtext('path') or '')
        if not rom:
            continue
        fields = {child.tag: (child.text or '').strip() for child in game if isinstance(child.tag, str)}
        fields['path'] = rom
        entries[rom.lower()] = fields
    return entries


@app.route("/api/systems/<system_name>/gamelist-backups", methods=["GET"])
def gamelist_backups(system_name):
    """Every saved copy of a system's gamelist, newest first, with its entry count."""
    system_dir = _system_path_or_none(system_name)
    if not system_dir:
        return jsonify(success=False, error="Unknown system"), 404
    items = []
    for f in system_dir.glob('gamelist*.xml'):
        if f.name == 'gamelist.xml' or not _gamelist_backup_path(system_name, f.name):
            continue
        st = f.stat()
        try:
            count = sum(1 for _ in etree.parse(str(f)).getroot().iter('game'))
        except Exception:
            count = None
        # Dated backups are copied with the gamelist's own file time, so their
        # name says when they were made
        made = re.match(r'^gamelist_(\d{8}_\d{6})\.xml$', f.name)
        when = datetime.strptime(made.group(1), '%Y%m%d_%H%M%S') if made else datetime.fromtimestamp(st.st_mtime)
        items.append({'name': f.name, 'kind': _backup_kind(f.name), 'size': st.st_size, 'entries': count,
                      'modified': when.isoformat()})
    items.sort(key=lambda i: i['modified'], reverse=True)
    current = system_dir / 'gamelist.xml'
    current_count = sum(1 for _ in etree.parse(str(current)).getroot().iter('game')) if current.exists() else 0
    return jsonify(success=True, backups=items, current_entries=current_count)


@app.route("/api/systems/<system_name>/gamelist-backups/<name>/diff", methods=["GET"])
def gamelist_backup_diff(system_name, name):
    """What restoring this copy would change, entry by entry: games it would bring back,
    games it would remove, and fields that differ (before = now, after = the copy)."""
    path = _gamelist_backup_path(system_name, name)
    if not path:
        return jsonify(success=False, error="Backup not found"), 404
    try:
        backup = _read_entries(path)
        current_path = path.parent / 'gamelist.xml'
        current = _read_entries(current_path) if current_path.exists() else {}
    except Exception as e:
        return jsonify(success=False, error=f"Couldn't read the gamelist: {e}"), 400
    added = [{'path': e['path'], 'name': e.get('name')} for k, e in backup.items() if k not in current]
    removed = [{'path': e['path'], 'name': e.get('name')} for k, e in current.items() if k not in backup]
    changed = []
    for key in backup.keys() & current.keys():
        now, then = current[key], backup[key]
        fields = [{'field': f, 'now': now.get(f, ''), 'then': then.get(f, '')}
                  for f in sorted(set(now) | set(then)) if f != 'path' and now.get(f, '') != then.get(f, '')]
        if fields:
            changed.append({'path': then['path'], 'name': now.get('name') or then.get('name'), 'fields': fields})
    changed.sort(key=lambda c: (c['name'] or '').lower())
    return jsonify(success=True, added=added, removed=removed, changed=changed)


@app.route("/api/systems/<system_name>/gamelist-backups/<name>/restore", methods=["POST"])
def gamelist_backup_restore(system_name, name):
    """Replace gamelist.xml with this copy (the current one is backed up first)."""
    path = _gamelist_backup_path(system_name, name)
    if not path:
        return jsonify(success=False, error="Backup not found"), 404
    try:
        etree.parse(str(path))
    except Exception as e:
        return jsonify(success=False, error=f"That copy isn't valid XML: {e}"), 400
    current_backup = gamelist_mgr.backup(system_name, ROMS_BASE)
    shutil.copy2(path, path.parent / 'gamelist.xml')
    return jsonify(success=True, backup=current_backup)


@app.route("/api/systems/<system_name>/gamelist-backups/<name>", methods=["DELETE"])
def gamelist_backup_delete(system_name, name):
    path = _gamelist_backup_path(system_name, name)
    if not path:
        return jsonify(success=False, error="Backup not found"), 404
    path.unlink()
    return jsonify(success=True)


@app.route("/api/systems/<system_name>/gamelist-backups/prune", methods=["POST"])
def gamelist_backup_prune(system_name):
    """Body: {keep: n}. Deletes all but the newest n dated backups (gamelist_<date>.xml).
    Sync conflict copies and other copies are left alone."""
    system_dir = _system_path_or_none(system_name)
    if not system_dir:
        return jsonify(success=False, error="Unknown system"), 404
    keep = max(1, int((request.get_json(silent=True) or {}).get('keep', 10)))
    dated = sorted((f for f in system_dir.glob('gamelist_*.xml') if _backup_kind(f.name) == 'Backup'),
                   key=lambda f: f.name, reverse=True)
    removed = []
    for f in dated[keep:]:
        f.unlink()
        removed.append(f.name)
    return jsonify(success=True, removed=removed)
