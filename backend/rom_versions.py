"""
Each game's ROM version, as you note it (a ROM hack's 1.2, a translation's
patch date...), and the files it replaced: DATA_PATH/rom-versions.json,
{"system/rom path": {version, at, history: [{version, file, at}]}}. Kept by
RetroManager rather than in gamelist.xml, which EmulationStation rewrites
without fields it doesn't know. A game's record follows it when its file is
renamed and goes when the file does.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)
HISTORY = 20


class RomVersions:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'rom-versions.json'
        self._lock = threading.Lock()
        self._data = None

    def _load(self) -> Dict:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.is_file() else {}
            except (OSError, ValueError) as e:
                logger.warning(f"Couldn't read the ROM versions ({e}); starting afresh")
                self._data = {}
        return self._data

    def _save(self):
        tmp = self.path.with_suffix('.part')
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=0), encoding='utf-8')
        os.replace(tmp, self.path)

    def get(self, key: str) -> Dict:
        with self._lock:
            return dict(self._load().get(key, {}))

    def for_system(self, system: str) -> Dict[str, str]:
        """{rom path: version} of one system's games that have one noted."""
        prefix = f"{system}/"
        with self._lock:
            return {k[len(prefix):]: v.get('version', '') for k, v in self._load().items() if k.startswith(prefix) and v.get('version')}

    def set_version(self, key: str, version: Optional[str]):
        with self._lock:
            record = self._load().setdefault(key, {})
            record['version'] = (version or '').strip()[:60]
            record['at'] = int(time.time())
            if not record['version'] and not record.get('history'):
                self._data.pop(key, None)
            self._save()

    def replaced(self, old_key: str, new_key: str, kept_file: str, version: Optional[str]):
        """The file was replaced by a new one (kept_file: where the old one went)."""
        with self._lock:
            data = self._load()
            record = data.pop(old_key, {})
            history = [{'version': record.get('version', ''), 'file': kept_file, 'at': int(time.time())}] + record.get('history', [])
            data[new_key] = {'version': (version if version is not None else record.get('version', '')).strip()[:60],
                             'at': int(time.time()), 'history': history[:HISTORY]}
            self._save()

    def game_moved(self, system: str, old: str, new: Optional[str]):
        with self._lock:
            data = self._load()
            record = data.pop(f"{system}/{old}", None)
            if record is None:
                return
            if new:
                data[f"{system}/{new}"] = record
            self._save()
