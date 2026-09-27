"""
Library-wide scraping in the background: every game missing metadata (and,
optionally, games missing media) on every system, one at a time.

Confident matches (ScreenScraper recognised the file, or the name matches
closely) are applied the same way as Bulk scrape: empty fields only, media the
game doesn't have yet. Anything less certain is left for review. Each system's
gamelist is backed up before its first change.

Games already checked are remembered (in DATA_PATH), so a later
run skips them for RECHECK_DAYS unless asked to recheck.
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

RECHECK_DAYS = 30
AUTO_APPLY = ('exact', 'likely')


class ScrapeQueue:
    def __init__(self, state_dir: Path, list_targets: Callable, match: Callable, apply: Callable,
                 backup: Callable, on_change: Callable, fatal_errors: tuple):
        """list_targets(systems, include_media, media) -> [{system, system_name, rom_path, name, reason}]
        match(system, rom_path) -> BulkMatcher result; apply(system, rom_path, game_id, media) -> dict
        backup(system) before a system's first write; on_change() after each write."""
        self.state_file = Path(state_dir) / 'scrape-queue.json'
        self._list_targets = list_targets
        self._match = match
        self._apply = apply
        self._backup = backup
        self._on_change = on_change
        self._fatal_errors = fatal_errors
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.status = self._idle_status()
        self._checked = self._load_checked()

    @staticmethod
    def _idle_status():
        return {'running': False, 'stopping': False, 'total': 0, 'done': 0, 'current': None,
                'applied': [], 'review': [], 'failed': [], 'skipped_recent': 0,
                'started': None, 'finished': None, 'stopped_reason': None}

    # Remember what was checked, so reruns don't use up the ScreenScraper quota
    def _load_checked(self) -> Dict[str, float]:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {}

    def _save_checked(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix('.tmp')
            tmp.write_text(json.dumps(self._checked))
            tmp.replace(self.state_file)
        except OSError as e:
            logger.warning(f"Couldn't save scrape queue state: {e}")

    def snapshot(self) -> Dict:
        with self._lock:
            return json.loads(json.dumps(self.status))

    def start(self, systems: Optional[List[str]], include_media: bool, media: List[str], recheck: bool) -> Dict:
        with self._lock:
            if self.status['running']:
                return {'success': False, 'error': 'A library scrape is already running'}
            targets = self._list_targets(systems, include_media, media)
            cutoff = time.time() - RECHECK_DAYS * 86400
            fresh = [t for t in targets
                     if recheck or self._checked.get(f"{t['system']}/{t['rom_path']}", 0) < cutoff]
            self.status = self._idle_status()
            self.status.update(running=True, total=len(fresh), skipped_recent=len(targets) - len(fresh),
                               started=datetime.now().isoformat(timespec='seconds'))
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, args=(fresh, media), daemon=True)
            self._thread.start()
            return {'success': True, 'total': len(fresh), 'skipped_recent': len(targets) - len(fresh)}

    def stop(self):
        with self._lock:
            if self.status['running']:
                self.status['stopping'] = True
        self._stop.set()

    def _set(self, **changes):
        with self._lock:
            self.status.update(changes)

    def _append(self, key, item):
        with self._lock:
            self.status[key].append(item)

    def _run(self, targets: List[Dict], media: List[str]):
        backed_up = set()
        reason = None
        try:
            for i, target in enumerate(targets):
                if self._stop.is_set():
                    reason = 'Stopped'
                    break
                system, rom_path = target['system'], target['rom_path']
                self._set(current={'system_name': target['system_name'], 'name': target['name']})
                item = {'system': system, 'system_name': target['system_name'], 'rom_path': rom_path,
                        'name': target['name'], 'reason': target['reason']}
                try:
                    result = self._match(system, rom_path)
                    top = next((a for a in result.get('alternatives', [])
                                if str(a.get('id')) == str(result.get('match_id'))), None)
                    item.update(confidence=result['confidence'], match=top)
                    if result['confidence'] in AUTO_APPLY and result.get('match_id'):
                        if system not in backed_up:
                            self._backup(system)
                            backed_up.add(system)
                        applied = self._apply(system, rom_path, result['match_id'], media)
                        if applied.get('success'):
                            item.update(filled=applied.get('filled', []), downloaded=applied.get('downloaded', []),
                                        errors=applied.get('errors', []))
                            self._append('applied', item)
                            self._on_change()
                        else:
                            item['error'] = applied.get('error') or 'Could not apply'
                            self._append('failed', item)
                    else:
                        self._append('review', item)
                    self._checked[f"{system}/{rom_path}"] = time.time()
                except self._fatal_errors as e:
                    # Quota, overload, bad credentials: stop rather than fail every game
                    reason = str(e)
                    break
                except Exception as e:
                    logger.exception(f"Library scrape failed for {system}/{rom_path}")
                    item['error'] = str(e)
                    self._append('failed', item)
                self._set(done=i + 1)
                if (i + 1) % 10 == 0:
                    self._save_checked()
        finally:
            self._save_checked()
            self._set(running=False, stopping=False, current=None, stopped_reason=reason,
                      finished=datetime.now().isoformat(timespec='seconds'))
