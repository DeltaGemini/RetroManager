"""
Duplicates: every game in the library more than once, found two ways and shown
as one list. By name (the Scan's check: the same title apart from region and
version tags, or the same gamelist name) and by contents (the ROM check: files
with the same checksum, even under different names or in different systems).
A group found both ways is listed once, marked with both.

Moving copies aside is done by the check that found the group (a group found
by name also has its details and media folded into the kept copy).
"""

from flask import jsonify, request
from pathlib import Path
from backend.core import app, logger, scanner, ROMS_BASE
from backend.media_index import strip_dot_slash
from backend.routes.romindex import rom_index


def _key(system, path):
    return f"{system}/{strip_dot_slash(path)}".lower()


def _size(system, path):
    try:
        return (Path(ROMS_BASE) / system / strip_dot_slash(path)).stat().st_size
    except OSError:
        return None


@app.route("/api/duplicates", methods=["GET"])
def duplicates_report():
    """?system=<name> for one system. Groups: {id, name, reasons: [name, contents],
    system (None when the copies are in different systems), keep (suggested),
    copies: [{system, path, size, name, media?, playcount?}]}."""
    only = request.args.get("system")
    try:
        systems = {s.name: s.get_full_name() for s in scanner.discover_systems()}
        groups = []
        by_members = {}
        for name, full_name in systems.items():
            if only and name != only:
                continue
            try:
                found = scanner.scan_system(name)['duplicates']
            except Exception as e:
                logger.warning(f"Duplicates: scanning {name} failed: {e}")
                continue
            for g in found:
                copies = [{'system': name, 'path': strip_dot_slash(c['path']), 'size': c.get('size'), 'name': c.get('name'),
                           'media': c.get('media'), 'playcount': c.get('playcount')} for c in g['copies']]
                group = {'id': f"name:{name}:{g['id']}", 'name': g.get('name'), 'reasons': ['name'], 'system': name,
                         'full_name': full_name, 'keep': _key(name, g.get('keep') or copies[0]['path']), 'copies': copies}
                groups.append(group)
                by_members[frozenset(_key(name, c['path']) for c in copies)] = group

        report = rom_index.report(systems)
        for found in report.get('duplicates') or []:
            members = frozenset(_key(r['system'], r['rom_path']) for r in found)
            if only and not any(r['system'] == only for r in found):
                continue
            # A group found by name whose copies are all identical files is marked so
            for named_members, named in by_members.items():
                if named_members <= members and 'contents' not in named['reasons']:
                    named['reasons'].append('contents')
            if members in by_members:
                continue
            in_one = len({r['system'] for r in found}) == 1
            groups.append({
                'id': 'contents:' + '|'.join(sorted(members)), 'name': found[0].get('name'), 'reasons': ['contents'],
                'system': found[0]['system'] if in_one else None,
                'full_name': found[0].get('full_name') if in_one else ', '.join(sorted({r.get('full_name') or r['system'] for r in found})),
                'keep': _key(found[0]['system'], found[0]['rom_path']),
                'copies': [{'system': r['system'], 'path': strip_dot_slash(r['rom_path']), 'size': _size(r['system'], r['rom_path']),
                            'name': r.get('name')} for r in found],
            })
        groups.sort(key=lambda g: ((g['full_name'] or '').lower(), (g['name'] or '').lower()))
        # Without the ROM check having run, only duplicates by name can be found
        checked = sum(v for v in (report.get('counts') or {}).values() if isinstance(v, int))
        return jsonify(success=True, groups=groups, rom_check_ran=checked > 0)
    except Exception as e:
        logger.exception("Error listing duplicates")
        return jsonify(success=False, error=str(e)), 500
