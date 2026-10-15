"""
Housekeeping that runs by itself: once a night, RetroManager's own data is
backed up and (unless switched off in Settings) the ROM check looks at files
that are new or changed. Jobs cut short by a restart are started again.

The data backup is a zip of the small files in DATA_PATH that can't be rebuilt
from the library: settings, play statuses and collections, the ROM check's
results and what scraping has already looked at. It holds the same passwords
and keys settings.json does, and stays in the same folder.
"""

import json
import logging
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Files backed up, relative to DATA_PATH
DATA_FILES = ('settings.json', 'library-state.json', 'rom-index.json', 'scrape-queue.json',
              'rom-hashes.json', 'retroachievements/rom-games.json', 'series.json', 'accounts.json', 'mix-generated.json')
KEEP_BACKUPS = 14
# The hour (server time) after which the night's housekeeping runs
NIGHTLY_HOUR = 3


class Maintenance:
    def __init__(self, data_dir: Path, nightly: Callable[[], None]):
        """nightly() does the rest of the night's work (the ROM check); it must not raise."""
        self.data_dir = Path(data_dir)
        self.backup_dir = self.data_dir / 'backups'
        self.state_file = self.data_dir / 'maintenance.json'
        self._nightly = nightly
        self._lock = threading.Lock()

    def list_backups(self) -> List[Dict]:
        try:
            files = sorted(self.backup_dir.glob('data-*.zip'), reverse=True)
        except OSError:
            return []
        return [{'name': f.name, 'size': f.stat().st_size,
                 'made': datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec='seconds')} for f in files]

    def backup_data(self) -> Optional[str]:
        """Zip the data files into DATA_PATH/backups and drop all but the newest
        KEEP_BACKUPS. Returns the new file's name, or None if there was nothing to back up."""
        with self._lock:
            present = [name for name in DATA_FILES if (self.data_dir / name).is_file()]
            if not present:
                return None
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            target = self.backup_dir / f"data-{time.strftime('%Y%m%d-%H%M%S')}.zip"
            tmp = target.with_suffix('.part')
            with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name in present:
                    archive.write(self.data_dir / name, name)
            tmp.replace(target)
            for old in sorted(self.backup_dir.glob('data-*.zip'), reverse=True)[KEEP_BACKUPS:]:
                try:
                    old.unlink()
                except OSError:
                    pass
            return target.name

    def _last_night(self) -> str:
        try:
            return json.loads(self.state_file.read_text()).get('last_night', '')
        except (OSError, ValueError):
            return ''

    def _loop(self):
        while True:
            try:
                now = datetime.now()
                today = now.strftime('%Y-%m-%d')
                if now.hour >= NIGHTLY_HOUR and self._last_night() != today:
                    self.state_file.write_text(json.dumps({'last_night': today}))
                    self.backup_data()
                    self._nightly()
            except Exception:
                logger.exception("Nightly housekeeping failed")
            time.sleep(600)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name='maintenance').start()
