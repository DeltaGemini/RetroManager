"""
Which game each source knows a ROM as, once that's settled (Fill the gaps):
DATA_PATH/matches.json, {"system/rom path": {source: {id, name, confidence, at}}}.
A remembered match isn't looked up again, which saves time and the sources'
quotas. A match is kept when it's Exact or Likely, or chosen by hand; it
follows its game when the file is renamed and goes when the file does.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MatchMemory:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'matches.json'
        self._lock = threading.Lock()
        self._data = None

    def _load(self) -> Dict:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.is_file() else {}
            except (OSError, ValueError) as e:
                logger.warning(f"Couldn't read the remembered matches ({e}); starting afresh")
                self._data = {}
        return self._data

    def _save(self):
        tmp = self.path.with_suffix('.part')
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=0), encoding='utf-8')
        os.replace(tmp, self.path)

    def get(self, key: str) -> Dict[str, Dict]:
        with self._lock:
            return dict(self._load().get(key, {}))

    def keys_for(self, system: str) -> Dict[str, Dict[str, Dict]]:
        """{rom path: {source: match}} for one system."""
        prefix = f"{system}/"
        with self._lock:
            return {k[len(prefix):]: v for k, v in self._load().items() if k.startswith(prefix)}

    def remember(self, key: str, source: str, match_id: str, name: Optional[str], confidence: str):
        with self._lock:
            self._load().setdefault(key, {})[source] = {'id': str(match_id), 'name': name or '', 'confidence': confidence, 'at': int(time.time())}
            self._save()

    def forget(self, key: str, source: Optional[str] = None):
        with self._lock:
            data = self._load()
            if source is None:
                data.pop(key, None)
            elif key in data:
                data[key].pop(source, None)
                if not data[key]:
                    data.pop(key)
            self._save()

    def game_moved(self, system: str, old: str, new: Optional[str]):
        """A game's file was renamed (its matches follow) or removed (they go)."""
        with self._lock:
            data = self._load()
            matches = data.pop(f"{system}/{old}", None)
            if matches is None:
                return
            if new:
                data[f"{system}/{new}"] = matches
            self._save()
