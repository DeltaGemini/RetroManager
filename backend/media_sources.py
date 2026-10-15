"""
Where each downloaded picture came from (ScreenScraper, LaunchBox, a file of
yours...), kept in media-sources.db in the data folder, so one that turns out
to be the wrong game's can be traced. A file changed since by other means (its
size is different) is no longer said to be from anywhere.
"""

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# The end of a download address's host -> the source's name
_HOSTS = {
    'screenscraper.fr': 'ScreenScraper', 'libretro.com': 'libretro', 'igdb.com': 'IGDB', 'gametdb.com': 'GameTDB',
    'launchbox-app.com': 'LaunchBox', 'thegamesdb.net': 'TheGamesDB', 'steamgriddb.com': 'SteamGridDB',
    'retroachievements.org': 'RetroAchievements', 'steamstatic.com': 'Steam', 'steampowered.com': 'Steam',
    'akamaihd.net': 'Steam',
}
UPLOADED = 'a file of yours'


def source_of(url: str) -> Optional[str]:
    host = (urlparse(url or '').hostname or '').lower()
    return next((name for end, name in _HOSTS.items() if host == end or host.endswith('.' + end)), host or None)


class MediaSources:
    def __init__(self, data_dir: Any, media_base: Any):
        self.path = Path(data_dir) / 'media-sources.db'
        self.media_base = Path(media_base)
        self._lock = threading.Lock()
        self._made = False

    def _db(self):
        db = sqlite3.connect(self.path, timeout=20)
        if not self._made:
            db.execute("CREATE TABLE IF NOT EXISTS sources (path TEXT PRIMARY KEY, source TEXT, size INTEGER, at REAL)")
            self._made = True
        return db

    def record(self, saved: Path, source: Optional[str]):
        """Notes where the media file just saved came from. Never raises."""
        if not source:
            return
        try:
            rel = Path(saved).relative_to(self.media_base).as_posix()
            with self._lock:
                db = self._db()
                try:
                    # (another format of the same picture was replaced by this one)
                    db.execute("DELETE FROM sources WHERE path LIKE ? ESCAPE '\\'",
                               (rel.rsplit('.', 1)[0].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '.%',))
                    db.execute("INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?)", (rel, source, Path(saved).stat().st_size, time.time()))
                    db.commit()
                finally:
                    db.close()
        except (OSError, ValueError, sqlite3.Error) as e:
            logger.warning(f"Couldn't note where {saved} came from: {e}")

    def for_paths(self, paths: Iterable[Optional[str]]) -> Dict[str, Dict]:
        """{media path: {source, at}} for those of these paths (relative to the
        media folder) that are still the file that was downloaded."""
        wanted = [p for p in paths if p]
        if not wanted or not self.path.is_file():
            return {}
        try:
            with self._lock:
                db = self._db()
                try:
                    rows = db.execute(f"SELECT path, source, size, at FROM sources WHERE path IN ({','.join('?' * len(wanted))})", wanted).fetchall()
                finally:
                    db.close()
        except sqlite3.Error as e:
            logger.warning(f"Couldn't read where media came from: {e}")
            return {}
        found = {}
        for rel, source, size, at in rows:
            try:
                if (self.media_base / rel).stat().st_size == size:
                    found[rel] = {'source': source, 'at': at}
            except OSError:
                pass
        return found
