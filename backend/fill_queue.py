"""
The background scrape: Fill the gaps' look-up (every source in your order, matches
remembered) run on the server over the systems chosen, one game at a time, with
nothing applied. What each game could have is kept, to check and apply in Fill the
gaps (its Choose step opens with them looked up already).

DATA_PATH/fill-found.json   {"system/rom": {system, system_name, rom, name, gaps, offered, at, sources}}
DATA_PATH/fill-checked.json {"system/rom": when it was last looked up} (skipped for RECHECK_DAYS)
DATA_PATH/fill-queue.running  the choices of a run under way, to carry on after a restart
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

RECHECK_DAYS = 30


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.part')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


class FillQueue:
    def __init__(self, state_dir: Path, list_targets: Callable, look: Callable, offered: Callable):
        """list_targets(systems, kinds) -> [{system, system_name, rom, name, gaps}]
        look(system, rom, sources) -> {source: {match, candidates}} (as /api/fill/look)
        offered(gaps, sources_found) -> the gaps a source has something for"""
        self.found_file = Path(state_dir) / 'fill-found.json'
        self.checked_file = Path(state_dir) / 'fill-checked.json'
        self.running_file = Path(state_dir) / 'fill-queue.running'
        self._list_targets, self._look, self._offered = list_targets, look, offered
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._found: Optional[Dict] = None
        self._checked: Optional[Dict] = None
        self.status = self._idle()

    @staticmethod
    def _idle():
        return {'running': False, 'stopping': False, 'total': 0, 'done': 0, 'current': None, 'found_now': 0,
                'skipped_recent': 0, 'started': None, 'finished': None, 'stopped_reason': None}

    def _found_all(self) -> Dict:
        if self._found is None:
            self._found = _read(self.found_file, {})
        return self._found

    def _checked_all(self) -> Dict:
        if self._checked is None:
            self._checked = _read(self.checked_file, {})
        return self._checked

    # --- What was found ---
    def summary(self) -> List[Dict]:
        """Each system with games found: [{system, system_name, games: [{rom, name, offered, at}]}]."""
        with self._lock:
            systems: Dict[str, Dict] = {}
            for entry in self._found_all().values():
                s = systems.setdefault(entry['system'], {'system': entry['system'], 'system_name': entry['system_name'], 'games': []})
                s['games'].append({k: entry[k] for k in ('rom', 'name', 'offered', 'at')})
        for s in systems.values():
            s['games'].sort(key=lambda g: (g['name'] or g['rom']).lower())
        return sorted(systems.values(), key=lambda s: s['system_name'].lower())

    def get(self, key: str) -> Optional[Dict]:
        with self._lock:
            entry = self._found_all().get(key)
            return json.loads(json.dumps(entry)) if entry else None

    def forget(self, keys: List[str]):
        """Done with (applied in Fill the gaps, or left): no longer listed."""
        with self._lock:
            found = self._found_all()
            if any(found.pop(k, None) is not None for k in list(keys)):
                _write(self.found_file, found)

    def game_moved(self, system: str, old: str, new: Optional[str]):
        with self._lock:
            for store, path in ((self._found_all(), self.found_file), (self._checked_all(), self.checked_file)):
                entry = store.pop(f"{system}/{old}", None)
                if entry is None:
                    continue
                if new:
                    if isinstance(entry, dict):
                        entry['rom'] = new
                    store[f"{system}/{new}"] = entry
                _write(path, store)

    # --- Running ---
    def snapshot(self) -> Dict:
        with self._lock:
            return {**self.status, 'found': len(self._found_all())}

    def start(self, systems: Optional[List[str]], kinds: List[str], sources: List[str], recheck: bool) -> Dict:
        with self._lock:
            if self.status['running']:
                return {'success': False, 'error': 'A background scrape is already running'}
            if not kinds or not sources:
                return {'success': False, 'error': 'Choose what to fill and at least one source'}
            targets = self._list_targets(systems, kinds)
            cutoff = time.time() - RECHECK_DAYS * 86400
            checked = self._checked_all()
            fresh = [t for t in targets if recheck or checked.get(f"{t['system']}/{t['rom']}", 0) < cutoff]
            self.status = self._idle()
            self.status.update(running=True, total=len(fresh), skipped_recent=len(targets) - len(fresh),
                               started=datetime.now().isoformat(timespec='seconds'))
            self._stop.clear()
            try:
                _write(self.running_file, {'systems': systems, 'kinds': kinds, 'sources': sources})
            except OSError:
                pass
            self._thread = threading.Thread(target=self._run, args=(fresh, sources), daemon=True)
            self._thread.start()
            return {'success': True, 'total': len(fresh), 'skipped_recent': len(targets) - len(fresh)}

    def stop(self):
        with self._lock:
            if self.status['running']:
                self.status['stopping'] = True
        self._stop.set()

    def _run(self, targets: List[Dict], sources: List[str]):
        reason = None
        try:
            for i, target in enumerate(targets):
                if self._stop.is_set():
                    reason = 'Stopped'
                    break
                key = f"{target['system']}/{target['rom']}"
                with self._lock:
                    self.status['current'] = {'system_name': target['system_name'], 'name': target['name']}
                try:
                    looked = self._look(target['system'], target['rom'], sources)
                    offered = self._offered(target['gaps'], looked)
                    with self._lock:
                        found = self._found_all()
                        if offered:
                            found[key] = {**target, 'offered': offered, 'at': int(time.time()), 'sources': looked}
                            self.status['found_now'] += 1
                        else:
                            found.pop(key, None)
                        self._checked_all()[key] = time.time()
                        if offered or (i + 1) % 10 == 0:
                            _write(self.found_file, found)
                            _write(self.checked_file, self._checked_all())
                except Exception:
                    logger.exception(f"Background scrape: couldn't look up {key}")
                with self._lock:
                    self.status['done'] = i + 1
        finally:
            with self._lock:
                try:
                    _write(self.found_file, self._found_all())
                    _write(self.checked_file, self._checked_all())
                except OSError as e:
                    logger.warning(f"Couldn't save what the background scrape found: {e}")
                self.status.update(running=False, stopping=False, current=None, stopped_reason=reason,
                                   finished=datetime.now().isoformat(timespec='seconds'))
            try:
                self.running_file.unlink()
            except OSError:
                pass

    def resume_if_interrupted(self) -> bool:
        """Start again with the same choices if the last run was cut short by a restart
        (games already looked up are skipped). Returns whether it started."""
        choices = _read(self.running_file, None)
        if not choices:
            return False
        return bool(self.start(choices.get('systems'), choices.get('kinds') or [], choices.get('sources') or [], False).get('success'))
