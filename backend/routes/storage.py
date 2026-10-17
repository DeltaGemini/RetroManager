"""
Storage: what RetroManager has set aside instead of deleting (replaced pictures,
duplicate games, saves it moved out of the way...) and the caches it keeps,
with how much room each takes, and deleting them for good when asked.

Each area's items are its top-level folders and files; a folder whose contents
are all dated folders (thinned-states/20261015-...) is listed by those instead,
so old ones can go and recent ones stay. Deleting is only of items the listing
shows, and each is noted in DATA_PATH/storage-cleanup.log.

An item's files can be compared with the ones in the library now: the same path
under the media, saves or save states folder (or the system's gamelist, or for a
duplicate game the copy kept), shown side by side, with what changed in a
gamelist or a text file.
"""

from flask import jsonify, request, send_file
from datetime import datetime, timedelta
import difflib
import hashlib
import io
import mimetypes
import os
import re
import shutil
import tarfile
import time
from pathlib import Path
from backend.core import app, logger, DATA_DIR, SAVE_BACKUP_BASE, MEDIA_BASE, ROMS_BASE, SAVES_BASE, SAVESTATES_BASE
from backend.media_index import title_key
from backend.routes.backups import diff_gamelists
from backend.routes.play import DISC_CACHE
from backend.routes.views import THUMB_DIR

# A name that starts with a date: 20261015-152357, 20260927_004907, data-20261008-030055...
_DATED_RE = re.compile(r'(?:^|[-_])(\d{4})(\d{2})(\d{2})(?:[-_]?(\d{2})(\d{2})(\d{2})?)?')
CLEANUP_LOG = DATA_DIR / 'storage-cleanup.log'

# id, folder, name, what it is, whether it's a cache (rebuilt when needed), and
# folders always listed by what's in them
AREAS = [
    ('replaced-media', DATA_DIR / 'replaced-media', 'Pictures replaced by scraping',
     'The pictures a scrape or Prefer Mix replaced, kept in case the new one was worse.', False, ()),
    ('gamelist-backups', Path(ROMS_BASE), 'Gamelist backups',
     "Copies of each system's gamelist.xml, made before every change (and Syncthing's conflict copies). "
     'Compare one with the gamelist now, or put it back.', False, ('gamelists',)),
    ('gamelist-copies', DATA_DIR / 'gamelist-backups', 'Gamelists copied before library-wide changes',
     'Every gamelist, copied before a change to all of them (moving the media folder, say).', False, ()),
    ('replaced-roms', DATA_DIR / 'replaced-roms', 'ROM files replaced by updated ones',
     "The file each game had before Replace the ROM put a new one in its place, with its version.", False, ()),
    ('duplicates', DATA_DIR / 'duplicates', 'Duplicate games set aside',
     'Copies of games removed by the duplicates tool. The copy you kept is still in your library.', False, ('*',)),
    ('save-backups', SAVE_BACKUP_BASE, 'Saves and save states set aside',
     'Saves and states moved out of the way: thinned states, sync conflicts, saves replaced while playing, '
     'clean-ups and save zips. Your current saves are not here.', False, ('zips',)),
    ('mix-backups', DATA_DIR / 'mix-backups', 'Mix pictures replaced by generated ones',
     'Each bundle holds the Mix pictures a generated Mix replaced.', False, ()),
    ('box-staging', DATA_DIR / 'box-staging', 'Made and pasted pictures not applied',
     '3D boxes and spines made, and pictures pasted, in Fill the gaps but never applied. Cleared after a day.', False, ()),
    ('mix-staging', DATA_DIR / 'mix-staging', 'Unfinished generated Mix previews',
     'Previews from Mix generation that were never approved or rejected.', False, ()),
    ('data-backups', DATA_DIR / 'backups', "Nightly copies of RetroManager's own data",
     'Profiles, collections, settings and so on, copied each night. The newest 14 are kept anyway.', False, ()),
    ('thumbs', THUMB_DIR, 'Small pictures (cache)',
     'Scaled-down pictures for the Bookcase and the Media viewer. Made again when next shown.', True, ()),
    ('play-cache', DISC_CACHE, 'Disc games ready to play in the browser (cache)',
     'Disc games zipped with their tracks for playing in the browser. Made again when next played.', True, ()),
]
_SKIP = {'moved.log'}


def _dated(name):
    match = _DATED_RE.search(name)
    if not match:
        return None
    y, mo, d, h, mi, s = match.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
    except ValueError:
        return None


def _measure(path):
    """(bytes, files, newest change) of a file or everything in a folder."""
    try:
        if path.is_file() or path.is_symlink():
            st = path.lstat()
            return st.st_size, 1, st.st_mtime
    except OSError:
        return 0, 0, 0
    size = files = newest = 0
    for folder, _, names in os.walk(path):
        for name in names:
            try:
                st = os.lstat(os.path.join(folder, name))
            except OSError:
                continue
            size += st.st_size
            files += 1
            newest = max(newest, st.st_mtime)
    return size, files, newest


def _children(folder):
    try:
        return sorted((p for p in folder.iterdir() if p.name not in _SKIP), key=lambda p: p.name)
    except OSError:
        return []


def _items(root, expand):
    """[(relative id, path)] of one area."""
    if expand == ('gamelists',):
        # Each system's gamelist copies, beside its gamelist.xml
        return [(f"{folder.name}/{f.name}", f) for folder in _children(root) if folder.is_dir()
                for f in sorted(folder.glob('gamelist*.xml')) if f.name != 'gamelist.xml']
    found = []
    for top in _children(root):
        inside = _children(top) if top.is_dir() else []
        if inside and ('*' in expand or top.name in expand or all(_dated(p.name) for p in inside)):
            found.extend((f"{top.name}/{p.name}", p) for p in inside)
        else:
            found.append((top.name, top))
    return found


def _area(area_id, root, name, help_text, cache, expand):
    items = []
    for rel, path in _items(root, expand):
        size, files, newest = _measure(path)
        when = _dated(path.name) or (datetime.fromtimestamp(newest) if newest else None)
        items.append({'id': rel, 'name': rel.replace('/', ' › '), 'size': size, 'files': files,
                      'date': when.isoformat(timespec='minutes') if when else None})
    items.sort(key=lambda i: i['date'] or '', reverse=True)
    return {'id': area_id, 'name': name, 'help': help_text, 'cache': cache,
            'size': sum(i['size'] for i in items), 'files': sum(i['files'] for i in items), 'items': items}


def _area_by_id(area_id):
    return next((a for a in AREAS if a[0] == area_id), None)


@app.route("/api/storage", methods=["GET"])
def storage_report():
    try:
        areas = [_area(*a) for a in AREAS]
        return jsonify(success=True, areas=areas, total=sum(a['size'] for a in areas))
    except Exception as e:
        logger.exception("Error measuring storage")
        return jsonify(success=False, error=str(e)), 500


@app.route("/api/storage/delete", methods=["POST"])
def storage_delete():
    """Body: {area, items: [ids]} or {area, older_than_days: n} or {area, all: true}.
    Deletes for good. Only items the area's listing has can be deleted."""
    data = request.get_json(silent=True) or {}
    area = _area_by_id(data.get('area'))
    if not area:
        return jsonify(success=False, error="Unknown area"), 400
    area_id, root, _, _, _, expand = area
    listed = dict(_items(root, expand))
    if data.get('all'):
        wanted = list(listed)
    elif data.get('older_than_days') is not None:
        try:
            cutoff = datetime.now() - timedelta(days=max(0, float(data['older_than_days'])))
        except (TypeError, ValueError):
            return jsonify(success=False, error="older_than_days must be a number"), 400
        wanted = []
        for rel, path in listed.items():
            when = _dated(path.name)
            if when is None:
                try:
                    when = datetime.fromtimestamp(_measure(path)[2] or path.lstat().st_mtime)
                except OSError:
                    continue
            if when < cutoff:
                wanted.append(rel)
    else:
        wanted = [str(i) for i in data.get('items') or []]
        unknown = [i for i in wanted if i not in listed]
        if unknown:
            return jsonify(success=False, error=f"Not in {area_id}: {', '.join(unknown[:3])}"), 400

    freed = files = 0
    deleted, errors = [], []
    resolved_root = root.resolve()
    for rel in wanted:
        path = listed[rel]
        if resolved_root not in path.resolve().parents and not path.is_symlink():
            errors.append(f"{rel}: outside {area_id}")
            continue
        size, count, _ = _measure(path)
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as e:
            errors.append(f"{rel}: {e}")
            continue
        freed += size
        files += count
        deleted.append(rel)
        _log(f"{area_id}/{rel}\t{count} files\t{size} bytes")
    # A folder that held only dated items, now empty, goes too
    for rel in deleted:
        parent = (root / rel).parent
        if parent != root and parent.is_dir() and not any(parent.iterdir()):
            try:
                parent.rmdir()
            except OSError:
                pass
    return jsonify(success=not errors or bool(deleted), deleted=deleted, freed=freed, files=files, errors=errors)


def _log(line):
    try:
        with open(CLEANUP_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\tdeleted\t{line}\n")
    except OSError as e:
        logger.warning(f"Couldn't note a deletion in {CLEANUP_LOG}: {e}")


# --- Comparing what was set aside with what's in the library now ---

_PICTURES = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
_TEXT = {'.xml', '.txt', '.csv', '.cfg', '.log', '.json', '.ini', '.m3u', '.cue', '.opt'}
_COMPARE_LIMIT = 150
_HASH_LIMIT = 64 * 1024 * 1024
_FOLDERS = {'media': MEDIA_BASE, 'saves': SAVES_BASE, 'savestates': SAVESTATES_BASE, 'roms': ROMS_BASE}


def _kind(name):
    ext = Path(name).suffix.lower()
    if name.lower().startswith('gamelist') and ext == '.xml':
        return 'gamelist'
    return 'picture' if ext in _PICTURES else 'text' if ext in _TEXT else 'file'


def _item(area_id, item_id):
    area = _area_by_id(area_id)
    if not area:
        return None, None
    return area, dict(_items(area[1], area[5])).get(item_id)


def _aside_files(path):
    """[(rel, size, mtime)] of what an item holds: the file, a folder's files, or a bundle's."""
    if path.is_file() and path.name.endswith(('.tar.gz', '.tgz', '.tar')):
        with tarfile.open(path) as bundle:
            return [(m.name, m.size, m.mtime) for m in bundle.getmembers() if m.isfile()]
    if path.is_file():
        st = path.stat()
        return [('', st.st_size, st.st_mtime)]
    out = []
    for folder, _, names in os.walk(path):
        for name in sorted(names):
            full = Path(folder) / name
            try:
                st = full.stat()
            except OSError:
                continue
            out.append((full.relative_to(path).as_posix(), st.st_size, st.st_mtime))
    return sorted(out)


def _same_stem(candidate):
    """The file itself, or one with the same name but another picture format."""
    if candidate.is_file():
        return candidate
    if candidate.suffix.lower() in _PICTURES and candidate.parent.is_dir():
        for other in candidate.parent.glob(f"{_glob_escape(candidate.stem)}.*"):
            if other.suffix.lower() in _PICTURES and other.is_file():
                return other
    return None


def _glob_escape(text):
    return re.sub(r'([\[\]*?])', r'[\1]', text)


def _current(area_id, item_id, item_path, rel):
    """The file in the library now that this set-aside one was (or None)."""
    full = (Path(item_id) / rel).as_posix() if rel else item_id
    parts = Path(full).parts
    if area_id == 'gamelist-backups':
        current = Path(ROMS_BASE) / parts[0] / 'gamelist.xml'
        return current if current.is_file() else None
    if area_id == 'gamelist-copies':
        current = Path(ROMS_BASE) / Path(rel).parent / 'gamelist.xml' if rel else None
        return current if current and current.is_file() else None
    if area_id == 'duplicates' and len(parts) >= 2:
        # The copy kept: the same game, by name, in that system's folder
        wanted = title_key(Path(parts[-1]).stem)
        folder = Path(ROMS_BASE) / parts[0]
        try:
            return next((f for f in sorted(folder.iterdir()) if f.is_file() and title_key(f.stem) == wanted
                         and f.suffix.lower() == Path(parts[-1]).suffix.lower()), None)
        except OSError:
            return None
    # Elsewhere the path is the one it had, under a dated folder: try each ending of it
    # in the folder it names (saves/..., media/...), or in media, saves and save states
    for start in range(len(parts) - 1):
        tail = parts[start:]
        if tail[0] in _FOLDERS and len(tail) >= 3:
            bases = [(_FOLDERS[tail[0]], tail[1:])]
        else:
            bases = [(MEDIA_BASE, tail), (SAVES_BASE, tail), (SAVESTATES_BASE, tail)]
        for base, rest in bases:
            found = _same_stem(Path(base).joinpath(*rest))
            if found:
                return found
    return None


def _digest(read, size):
    if size > _HASH_LIMIT:
        return None
    h = hashlib.sha1()
    with read() as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _opener(item_path, rel):
    """A function giving the set-aside file's contents as a file object."""
    if item_path.is_file() and item_path.name.endswith(('.tar.gz', '.tgz', '.tar')):
        def read():
            with tarfile.open(item_path) as bundle:
                return io.BytesIO(bundle.extractfile(rel).read())
        return read
    target = (item_path / rel) if rel else item_path
    if item_path.resolve() not in target.resolve().parents and target.resolve() != item_path.resolve():
        raise ValueError("Not in that item")
    return lambda: open(target, 'rb')


@app.route("/api/storage/compare", methods=["GET"])
def storage_compare():
    """?area=&item=: the item's files beside the library's own, the first 150."""
    area, item_path = _item(request.args.get('area'), request.args.get('item', ''))
    if not area or item_path is None:
        return jsonify(success=False, error="Not found"), 404
    area_id, item_id = area[0], request.args.get('item')
    try:
        files = _aside_files(item_path)
    except (OSError, tarfile.TarError) as e:
        return jsonify(success=False, error=str(e)), 400
    out = []
    for rel, size, mtime in files[:_COMPARE_LIMIT]:
        now = _current(area_id, item_id, item_path, rel)
        entry = {'rel': rel, 'name': Path(rel or item_id).name, 'kind': _kind(Path(rel or item_id).name),
                 'aside': {'size': size, 'date': datetime.fromtimestamp(mtime).isoformat(timespec='minutes')}, 'now': None, 'same': None}
        if now:
            st = now.stat()
            entry['now'] = {'size': st.st_size, 'date': datetime.fromtimestamp(st.st_mtime).isoformat(timespec='minutes'),
                            'name': now.name, 'where': now.parent.name}
            if st.st_size != size:
                entry['same'] = False
            else:
                try:
                    a, b = _digest(_opener(item_path, rel), size), _digest(lambda: open(now, 'rb'), st.st_size)
                    entry['same'] = a == b if a and b else None
                except (OSError, ValueError, KeyError, tarfile.TarError):
                    pass
        out.append(entry)
    return jsonify(success=True, files=out, total=len(files), restorable=area_id == 'gamelist-backups')


@app.route("/api/storage/file", methods=["GET"])
def storage_file():
    """?area=&item=&rel=&side=aside|now: one of the two files being compared."""
    area, item_path = _item(request.args.get('area'), request.args.get('item', ''))
    if not area or item_path is None:
        return jsonify(error="Not found"), 404
    rel = request.args.get('rel', '')
    name = Path(rel or request.args.get('item')).name
    try:
        if request.args.get('side') == 'now':
            now = _current(area[0], request.args.get('item'), item_path, rel)
            if not now:
                return jsonify(error="Not in the library now"), 404
            return send_file(now, mimetype=mimetypes.guess_type(now.name)[0] or 'application/octet-stream', max_age=0)
        data = _opener(item_path, rel)()
        return send_file(data, mimetype=mimetypes.guess_type(name)[0] or 'application/octet-stream', download_name=name, max_age=0)
    except (OSError, ValueError, KeyError, tarfile.TarError) as e:
        return jsonify(error=str(e)), 404


@app.route("/api/storage/diff", methods=["GET"])
def storage_diff():
    """?area=&item=&rel=: what's different between a set-aside gamelist or text
    file and the library's. A gamelist: {added, removed, changed} entries (as if
    the copy were put back); text: {lines} of a unified diff, the first 400."""
    area, item_path = _item(request.args.get('area'), request.args.get('item', ''))
    if not area or item_path is None:
        return jsonify(success=False, error="Not found"), 404
    rel = request.args.get('rel', '')
    now = _current(area[0], request.args.get('item'), item_path, rel)
    if not now:
        return jsonify(success=False, error="There's no version of it in the library now"), 404
    try:
        if _kind(Path(rel or request.args.get('item')).name) == 'gamelist' and not item_path.name.endswith(('.tar.gz', '.tar')):
            return jsonify(success=True, gamelist=diff_gamelists((item_path / rel) if rel else item_path, now))
        with _opener(item_path, rel)() as f:
            old = f.read(2 * 1024 * 1024).decode('utf-8', errors='replace').splitlines()
        new = now.read_bytes()[:2 * 1024 * 1024].decode('utf-8', errors='replace').splitlines()
        lines = list(difflib.unified_diff(old, new, 'set aside', 'now', lineterm='', n=2))
        return jsonify(success=True, lines=lines[:400], more=max(0, len(lines) - 400))
    except Exception as e:
        return jsonify(success=False, error=f"Couldn't compare them: {e}"), 400
