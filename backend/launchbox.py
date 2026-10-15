"""
The LaunchBox Games Database (gamesdb.launchbox-app.com): pictures of nearly
every kind, cartridges and discs among them. It has no search to ask, only one
big file of everything (about 110 MB), so RetroManager fetches that, keeps the
part it uses (the games and pictures of the platforms it knows) as an index in
its data folder, and looks games up there. No account and no quota.
"""

import logging
import os
import re
import sqlite3
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from xml.etree import ElementTree

import requests

from backend.media_index import title_key
from backend.systems import launchbox_platform, launchbox_platforms

logger = logging.getLogger(__name__)

METADATA_URL = "https://gamesdb.launchbox-app.com/Metadata.zip"
IMAGE_URL = "https://images.launchbox-app.com/"
# The index is fetched again when it's this old
REFRESH_AFTER = 30 * 24 * 3600

# RetroManager media folder -> LaunchBox picture types, the likeliest first
# (the "Fanart" ones are made by fans: better than nothing)
MEDIA_TYPES = {
    'support': ['Cart - Front', 'Disc', 'Fanart - Cart - Front', 'Fanart - Disc'],
    'box2d': ['Box - Front', 'Box - Front - Reconstructed', 'Fanart - Box - Front'],
    'boxback': ['Box - Back', 'Box - Back - Reconstructed'],
    'box3d': ['Box - 3D'],
    'boxside': ['Box - Spine'],
    'wheel': ['Clear Logo'],
    'screenshot': ['Screenshot - Gameplay'],
    'screenshottitle': ['Screenshot - Game Title'],
    'fanart': ['Fanart - Background'],
    'banner': ['Banner'],
}
_KEPT_TYPES = {kind for kinds in MEDIA_TYPES.values() for kind in kinds}
# Which region's picture to take, the likeliest first ("" is one with no region given)
_REGIONS = ['North America', 'United States', 'World', '', 'Europe', 'United Kingdom', 'Australia', 'Canada']


MAX_EXTRA = 4
_TAGS = re.compile(r'\([^)]*\)|\[[^\]]*\]')


def _region_rank(region: Optional[str]) -> int:
    region = region or ''
    return _REGIONS.index(region) if region in _REGIONS else len(_REGIONS) + (region == 'Japan')


class LaunchBoxIndex:
    enabled = False

    def __init__(self, data_dir: Any):
        self.path = Path(data_dir) / 'launchbox.db'
        self._lock = threading.Lock()
        self.progress = dict(running=False, step=None, done=0, total=0, finished=None, error=None)

    @property
    def ready(self) -> bool:
        return self.path.is_file()

    @property
    def stale(self) -> bool:
        try:
            db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            try:
                db.execute("SELECT 1 FROM games LIMIT 1")  # (an index from before it kept the titles is made again)
            finally:
                db.close()
        except sqlite3.Error:
            return True
        try:
            return time.time() - self.path.stat().st_mtime > REFRESH_AFTER
        except OSError:
            return True

    # --- Looking a game up ---

    def pictures(self, system_name: str, names: Iterable[Optional[str]]) -> Dict[str, str]:
        """{media folder: url} for the game with one of these names (or known
        there by one of them) on this system's platform, or {}. Only a game whose
        title is the same but for tags and punctuation is used. Never raises."""
        platform = launchbox_platform(system_name)
        keys = [k for k in dict.fromkeys(title_key(n) for n in names if n) if k]
        if not self.enabled or not platform or not keys or not self.ready:
            return {}
        try:
            db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            try:
                game_id = None
                for key in keys:
                    row = db.execute("SELECT id FROM names WHERE platform = ? AND key = ? ORDER BY alternate LIMIT 1", (platform, key)).fetchone()
                    if row:
                        game_id = row[0]
                        break
                if game_id is None:
                    return {}
                media = self._media(db, game_id)
            finally:
                db.close()
        except sqlite3.Error as e:
            logger.warning(f"LaunchBox's index couldn't be read: {e}")
            return {}
        return {folder: url for folder, url in media.items() if folder in MEDIA_TYPES}

    def _media(self, db, game_id) -> Dict[str, str]:
        found = {}
        for kind, region, file_name in db.execute("SELECT type, region, file FROM images WHERE id = ?", (game_id,)):
            found.setdefault(kind, []).append((_region_rank(region), file_name))
        media = {}
        for folder, kinds in MEDIA_TYPES.items():
            kind = next((k for k in kinds if k in found), None)
            if kind:
                media[folder] = IMAGE_URL + min(found[kind])[1]
            # The others of that kind, to choose between by hand
            extra = [name for k in kinds for _, name in sorted(found.get(k, []))]
            for i, name in enumerate([n for n in extra if IMAGE_URL + n != media.get(folder)][:MAX_EXTRA], start=2):
                media[f'{folder}_{i}'] = IMAGE_URL + name
        return media

    def search(self, system_name: str, name: str, limit: int = 30) -> list:
        """Games on the system's platform whose title has every word of `name`:
        [{id, name, cover_url}], a game of exactly that title first. Raises
        ValueError (with what to tell the person) when it can't be searched."""
        platform = launchbox_platform(system_name)
        if not self.enabled:
            raise ValueError("LaunchBox is turned off: Tools › Settings › Matching and media.")
        if not self.ready:
            raise ValueError("LaunchBox's list of games is still being fetched. Try again in a few minutes.")
        if not platform:
            raise ValueError("RetroManager doesn't know this system's name at LaunchBox.")
        words = [title_key(w) for w in _TAGS.sub(' ', name or '').split()]
        words = [w for w in words if w]
        if not words:
            return []
        db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        try:
            rows = db.execute("SELECT id, MIN(alternate), key FROM names WHERE platform = ? AND " + " AND ".join(["key LIKE ?"] * len(words))
                              + " GROUP BY id ORDER BY key = ? DESC, MIN(alternate), LENGTH(key) LIMIT ?",
                              (platform, *[f"%{w}%" for w in words], ''.join(words), limit)).fetchall()
            out = []
            for game_id, _, _ in rows:
                title = db.execute("SELECT title FROM games WHERE id = ?", (game_id,)).fetchone()
                media = self._media(db, game_id)
                out.append({'id': game_id, 'name': title[0] if title else str(game_id), 'platform': platform,
                            'cover_url': media.get('box2d') or media.get('support') or media.get('wheel')})
            return out
        finally:
            db.close()

    def game(self, game_id: Any) -> Dict[str, Any]:
        """{name, media: {folder: url}} for one of search's games. Raises ValueError."""
        if not self.ready or not str(game_id).isdigit():
            raise ValueError("That isn't a LaunchBox game.")
        db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        try:
            title = db.execute("SELECT title FROM games WHERE id = ?", (int(game_id),)).fetchone()
            if not title:
                raise ValueError("LaunchBox's list hasn't that game (any more).")
            return {'name': title[0], 'media': self._media(db, int(game_id))}
        finally:
            db.close()

    # --- Fetching the index ---

    def refresh_if_needed(self) -> bool:
        """Starts fetching the index in the background if there's none or it's
        old. Returns whether it started."""
        if not self.enabled or self.progress['running'] or (self.ready and not self.stale):
            return False
        return self.refresh()

    def refresh(self) -> bool:
        with self._lock:
            if self.progress['running']:
                return False
            self.progress.update(running=True, step='Starting', done=0, total=0, finished=None, error=None)
        threading.Thread(target=self._run, name='launchbox-index', daemon=True).start()
        return True

    def _run(self):
        try:
            self.build()
        except Exception as e:  # anything: the old index (if any) stays in use
            logger.exception("LaunchBox's index couldn't be made")
            self.progress['error'] = f"LaunchBox's list couldn't be fetched: {e}"
            if self.ready:
                # Not again until tomorrow, rather than at every scrape
                os.utime(self.path, (time.time(), time.time() - REFRESH_AFTER + 24 * 3600))
        finally:
            self.progress.update(running=False, step=None, finished=time.time())

    def build(self, metadata_zip: Optional[Path] = None):
        """Fetches Metadata.zip (unless given one) and makes the index from it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fetched = None
        try:
            if metadata_zip is None:
                for left in self.path.parent.glob('launchbox-*.zip'):
                    left.unlink(missing_ok=True)  # from a fetch that was cut short
                fetched = Path(tempfile.mkstemp(dir=self.path.parent, prefix='launchbox-', suffix='.zip')[1])
                self._download(fetched)
                metadata_zip = fetched
            building = self.path.with_suffix('.building')
            building.unlink(missing_ok=True)
            self._index(metadata_zip, building)
            os.replace(building, self.path)
        finally:
            if fetched:
                fetched.unlink(missing_ok=True)

    def _download(self, target: Path):
        self.progress.update(step='Downloading')
        with requests.get(METADATA_URL, stream=True, timeout=60, headers={'User-Agent': 'RetroManager'}) as response:
            response.raise_for_status()
            self.progress['total'] = int(response.headers.get('Content-Length') or 0) // (1024 * 1024)
            got = 0
            with open(target, 'wb') as out:
                for chunk in response.iter_content(1024 * 1024):
                    out.write(chunk)
                    got += len(chunk)
                    self.progress['done'] = got // (1024 * 1024)

    def _index(self, metadata_zip: Path, target: Path):
        """Reads Metadata.xml a piece at a time (it's half a gigabyte), keeping
        the games of the platforms RetroManager knows and the picture types it uses."""
        platforms = launchbox_platforms()
        self.progress.update(step='Reading', done=0, total=0)
        db = sqlite3.connect(target)
        try:
            db.executescript("""
                CREATE TABLE names (platform TEXT, key TEXT, id INTEGER, alternate INTEGER);
                CREATE TABLE games (id INTEGER PRIMARY KEY, title TEXT);
                CREATE TABLE images (id INTEGER, type TEXT, region TEXT, file TEXT);
            """)
            kept, alternates, images = {}, [], []
            with zipfile.ZipFile(metadata_zip) as archive, archive.open('Metadata.xml') as xml:
                for _, element in ElementTree.iterparse(xml):
                    tag = element.tag
                    if tag == 'Game':
                        platform, game_id = element.findtext('Platform'), element.findtext('DatabaseID')
                        key = title_key(element.findtext('Name') or '')
                        if platform in platforms and key and (game_id or '').isdigit():
                            kept[int(game_id)] = platform
                            db.execute("INSERT INTO names VALUES (?, ?, ?, 0)", (platform, key, int(game_id)))
                            db.execute("INSERT OR REPLACE INTO games VALUES (?, ?)", (int(game_id), element.findtext('Name')))
                            self.progress['done'] = len(kept)
                    elif tag == 'GameAlternateName':
                        alternates.append((element.findtext('DatabaseID'), element.findtext('AlternateName')))
                    elif tag == 'GameImage':
                        if element.findtext('Type') in _KEPT_TYPES and element.findtext('FileName'):
                            images.append((element.findtext('DatabaseID'), element.findtext('Type'), element.findtext('Region') or '', element.findtext('FileName')))
                    else:
                        continue
                    element.clear()
                    if len(images) >= 50000:
                        self._keep_images(db, kept, images)
            self._keep_images(db, kept, images)
            for game_id, name in alternates:
                key = title_key(name or '')
                if key and (game_id or '').isdigit() and int(game_id) in kept:
                    db.execute("INSERT INTO names VALUES (?, ?, ?, 1)", (kept[int(game_id)], key, int(game_id)))
            if not kept:
                raise ValueError("there were no games in it")
            db.executescript("CREATE INDEX names_key ON names (platform, key); CREATE INDEX images_id ON images (id);")
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _keep_images(db, kept, images):
        # (the games come before their pictures in the file, so `kept` is whole by now)
        db.executemany("INSERT INTO images VALUES (?, ?, ?, ?)",
                       [(int(i), kind, region, name) for i, kind, region, name in images if (i or '').isdigit() and int(i) in kept])
        images.clear()
