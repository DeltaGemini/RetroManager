"""
A checksum index of the whole library: every ROM hashed once, in the
background, and looked up in the ROM databases (through Hasheous) and on
RetroAchievements. From it come:
    - which files are verified dumps, which are hacks, and which nothing knows
    - true duplicates (the same contents under two names)
    - files whose name doesn't match the game they contain
    - which games have achievements, without opening each one

Kept in DATA_PATH/rom-index.json. A file is only looked at again when it
changes, or when asked to recheck.
"""

import json
import logging
import threading
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.media_index import title_key
from backend.name_style import style_name

logger = logging.getLogger(__name__)

# Files that list a game's discs or tracks rather than holding it
DESCRIPTOR_EXTENSIONS = {'.m3u', '.cue', '.gdi', '.ccd', '.mds', '.txt'}
# A pause between Hasheous lookups: it's a free community service
LOOKUP_PAUSE = 0.25
# A file name this unlike the game inside it is reported as mislabelled
MISLABELLED_SCORE = 0.8
# ROM databases whose listing means "a known good dump"
VERIFYING_SOURCES = {'NoIntros', 'NoIntro', 'Redump', 'TOSEC', 'MAMEArcade', 'MAMEMess', 'MAMERedump', 'FBNeo', 'WHDLoad', 'PureDOSDAT'}


def _stamp(rom_file: Path) -> Optional[List[int]]:
    try:
        stat = rom_file.stat()
    except OSError:
        return None
    return [stat.st_size, stat.st_mtime_ns]


def name_matches(library_name: str, rom_path: str, known_name: str) -> bool:
    """Whether the game's name or file name looks like the name the databases
    give its contents. Several names ("A | B") count if any one matches."""
    ours = {title_key(style_name(library_name or '')), title_key(Path(rom_path).stem), title_key(style_name(Path(rom_path).stem))}
    ours.discard('')
    best = 0.0
    for part in (known_name or '').split('|'):
        theirs = {title_key(part), title_key(style_name(part.strip()))}
        theirs.discard('')
        for a in ours:
            for b in theirs:
                if a in b or b in a:
                    return True
                best = max(best, SequenceMatcher(None, a, b).ratio())
    return best >= MISLABELLED_SCORE


class RomIndex:
    def __init__(self, state_dir: Path, list_games: Callable, hash_file: Callable, lookup: Callable, identify_ra: Callable):
        """list_games() -> [{system, system_name, rom_path, name, file: Path}]
        hash_file(system, file) -> {'md5', 'sha1', 'crc32'} or None (too big, unreadable)
        lookup(hashes) -> Hasheous's answer or None; may raise when it can't be reached
        identify_ra(system, file, known) -> RetroAchievements game-list entry or None"""
        self.state_file = Path(state_dir) / 'rom-index.json'
        # There while a check is running, so one cut short by a restart starts again
        self.running_file = Path(state_dir) / 'rom-index.running'
        self._list_games = list_games
        self._hash_file = hash_file
        self._lookup = lookup
        self._identify_ra = identify_ra
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.status = self._idle_status()
        try:
            self._items: Dict[str, Dict] = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self._items = {}

    @staticmethod
    def _idle_status():
        return {'running': False, 'stopping': False, 'total': 0, 'done': 0, 'current': None,
                'started': None, 'finished': None, 'stopped_reason': None}

    def _save(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix('.tmp')
            with self._lock:
                text = json.dumps(self._items)
            tmp.write_text(text)
            tmp.replace(self.state_file)
        except OSError as e:
            logger.warning(f"Couldn't save the ROM index: {e}")

    def snapshot(self) -> Dict:
        with self._lock:
            return json.loads(json.dumps(self.status))

    def get(self, system: str, rom_path: str) -> Optional[Dict]:
        with self._lock:
            return self._items.get(f"{system}/{rom_path}")

    def move(self, system: str, old_rom_path: str, new_rom_path: Optional[str], new_file: Optional[Path] = None):
        """A game's file was renamed (its record follows) or removed (it's dropped)."""
        with self._lock:
            record = self._items.pop(f"{system}/{old_rom_path}", None)
            if record and new_rom_path:
                if new_file is not None:
                    record['stamp'] = _stamp(new_file)
                self._items[f"{system}/{new_rom_path}"] = record
        if record:
            self._save()

    def records(self) -> Dict[str, Dict]:
        with self._lock:
            return dict(self._items)

    def start(self, recheck: bool = False) -> Dict:
        with self._lock:
            if self.status['running']:
                return {'success': False, 'error': 'The ROM check is already running'}
            self.status = self._idle_status()
            self.status.update(running=True, started=datetime.now().isoformat(timespec='seconds'))
            self._stop.clear()
            try:
                self.running_file.parent.mkdir(parents=True, exist_ok=True)
                self.running_file.write_text('1')
            except OSError:
                pass
            self._thread = threading.Thread(target=self._run, args=(recheck,), daemon=True)
            self._thread.start()
        return {'success': True}

    def stop(self):
        with self._lock:
            if self.status['running']:
                self.status['stopping'] = True
        self._stop.set()

    def _set(self, **changes):
        with self._lock:
            self.status.update(changes)

    def check_one(self, game: Dict) -> Dict:
        """Hash one ROM and look it up. Returns its record (also kept)."""
        rom_file: Path = game['file']
        record = {'stamp': _stamp(rom_file), 'checked_at': time.time(), 'name': game['name']}
        if not rom_file.is_file() or rom_file.suffix.lower() in DESCRIPTOR_EXTENSIONS:
            record['status'] = 'skipped'
            record['reason'] = 'a folder or a disc list, not a ROM file' if rom_file.exists() else 'missing'
        elif rom_file.stat().st_size == 0:
            record['status'] = 'skipped'
            record['reason'] = 'the file is empty (0 bytes)'
        else:
            hashes = self._hash_file(game['system'], rom_file)
            if not hashes:
                record['status'] = 'skipped'
                record['reason'] = 'too large to hash, or unreadable'
            else:
                record.update(md5=hashes['md5'], sha1=hashes['sha1'], crc32=hashes['crc32'])
                known = self._lookup(hashes)
                time.sleep(LOOKUP_PAUSE)
                ra_game = self._identify_ra(game['system'], rom_file, known)
                sources = (known or {}).get('sources') or []
                record['sources'] = sources
                record['known_name'] = (known or {}).get('name') or ''
                record['ids'] = (known or {}).get('ids') or {}
                if ra_game:
                    record['ra_id'] = ra_game.get('id')
                    record['ra_title'] = ra_game.get('title') or ''
                    record['ids']['retroachievements'] = str(ra_game.get('id'))
                    record['known_name'] = record['known_name'] or ra_game.get('title', '').split('~')[-1].strip()
                is_hack = '~Hack~' in (record.get('ra_title') or '')
                if is_hack:
                    record['status'] = 'hack'
                elif VERIFYING_SOURCES & set(sources):
                    record['status'] = 'verified'
                elif known or ra_game:
                    record['status'] = 'known'      # listed somewhere, but not as a verified dump
                else:
                    record['status'] = 'unknown'
        with self._lock:
            self._items[f"{game['system']}/{game['rom_path']}"] = record
        return record

    def _run(self, recheck: bool):
        reason = None
        try:
            games = self._list_games()
            with self._lock:
                # Forget files that are gone
                present = {f"{g['system']}/{g['rom_path']}" for g in games}
                for key in [k for k in self._items if k not in present]:
                    del self._items[key]
                todo = [g for g in games if recheck
                        or (self._items.get(f"{g['system']}/{g['rom_path']}") or {}).get('stamp') != _stamp(g['file'])]
                # A name changed in the library doesn't need the file hashed again
                for g in games:
                    item = self._items.get(f"{g['system']}/{g['rom_path']}")
                    if item:
                        item['name'] = g['name']
            self._set(total=len(todo))
            for i, game in enumerate(todo):
                if self._stop.is_set():
                    reason = 'Stopped'
                    break
                self._set(current={'system_name': game['system_name'], 'name': game['name']})
                try:
                    self.check_one(game)
                except Exception as e:
                    # Hasheous out of reach: stop rather than mark everything unknown
                    logger.warning(f"ROM check stopped at {game['system']}/{game['rom_path']}: {e}")
                    reason = str(e)
                    break
                self._set(done=i + 1)
                if (i + 1) % 20 == 0:
                    self._save()
        except Exception as e:
            logger.exception("ROM check failed")
            reason = str(e)
        finally:
            self._save()
            try:
                self.running_file.unlink()
            except OSError:
                pass
            self._set(running=False, stopping=False, current=None, stopped_reason=reason,
                      finished=datetime.now().isoformat(timespec='seconds'))

    def resume_if_interrupted(self) -> bool:
        """Start again if the last check was cut short by a restart (files already
        checked are skipped). Returns whether it started."""
        return self.running_file.exists() and bool(self.start(False).get('success'))

    def report(self, systems: Dict[str, str]) -> Dict:
        """What the index shows. `systems` is {folder: full name} for labels.
        {counts, by_system, duplicates, mislabelled, unknown, hacks, skipped}."""
        items = self.records()
        counts = {'verified': 0, 'known': 0, 'hack': 0, 'unknown': 0, 'skipped': 0}
        by_system: Dict[str, Dict] = {}
        by_md5: Dict[str, List[Dict]] = {}
        rows = {'mislabelled': [], 'unknown': [], 'hack': [], 'skipped': []}

        def row(key, item, **extra):
            system, _, rom_path = key.partition('/')
            return {'system': system, 'full_name': systems.get(system, system), 'rom_path': rom_path,
                    'name': item.get('name') or Path(rom_path).stem, **extra}

        for key, item in items.items():
            status = item.get('status', 'unknown')
            counts[status] = counts.get(status, 0) + 1
            system = key.partition('/')[0]
            per = by_system.setdefault(system, {'system': system, 'full_name': systems.get(system, system), 'total': 0,
                                                'verified': 0, 'known': 0, 'hack': 0, 'unknown': 0, 'skipped': 0})
            per['total'] += 1
            per[status] = per.get(status, 0) + 1
            if item.get('md5'):
                by_md5.setdefault(item['md5'], []).append(row(key, item))
            if status in ('unknown', 'skipped'):
                rows[status].append(row(key, item, reason=item.get('reason')))
            elif status == 'hack':
                rows['hack'].append(row(key, item, known_name=item.get('known_name')))
            if item.get('known_name') and not name_matches(item.get('name') or '', key.partition('/')[2], item['known_name']):
                rows['mislabelled'].append(row(key, item, known_name=item['known_name'].split('|')[0].strip(), sources=item.get('sources') or []))

        duplicates = [sorted(group, key=lambda r: (r['system'], r['rom_path'])) for group in by_md5.values() if len(group) > 1]
        duplicates.sort(key=lambda group: (group[0]['system'], group[0]['rom_path']))
        for group in rows.values():
            group.sort(key=lambda r: (r['full_name'], r['name'].lower()))
        return {
            'checked': len(items), 'counts': counts,
            'by_system': sorted(by_system.values(), key=lambda s: s['full_name']),
            'duplicates': duplicates, 'mislabelled': rows['mislabelled'], 'unknown': rows['unknown'],
            'hacks': rows['hack'], 'skipped': rows['skipped'],
        }
