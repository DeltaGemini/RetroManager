"""
Checksums of ROM files, for sources that identify a game by its contents
(Hasheous, RetroAchievements).

Hashing a large file on the NAS is slow, so results are remembered in DATA_PATH
and reused until the file's size or modified time changes.
"""

import hashlib
import io
import json
import logging
import threading
import zipfile
import zlib
from pathlib import Path
from typing import BinaryIO, Dict, Optional

logger = logging.getLogger(__name__)

# Files over this size aren't hashed (they take too long on the NAS)
HASH_LIMIT = 1024 * 1024 * 1024
# Zipped ROMs up to this size are unpacked in memory to hash what's inside
UNZIP_LIMIT = 256 * 1024 * 1024


def _single_zip_member(path: Path) -> Optional[zipfile.ZipInfo]:
    """The one file inside a .zip that holds a single ROM, else None."""
    if path.suffix.lower() != '.zip':
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
    except (OSError, zipfile.BadZipFile):
        return None
    return members[0] if len(members) == 1 else None


def open_rom(path: Path, unzip: bool = True) -> Optional[BinaryIO]:
    """The ROM's contents as a seekable file. A .zip holding one file is opened as
    that file (databases list the ROM, not the archive). None if it can't be read."""
    path = Path(path)
    try:
        member = _single_zip_member(path) if unzip else None
        if member:
            if member.file_size > UNZIP_LIMIT:
                return None
            with zipfile.ZipFile(path) as archive:
                return io.BytesIO(archive.read(member))
        return open(path, 'rb')
    except (OSError, zipfile.BadZipFile) as e:
        logger.warning(f"Couldn't open {path} for hashing: {e}")
        return None


class HashCache:
    def __init__(self, state_dir: Path):
        self.state_file = Path(state_dir) / 'rom-hashes.json'
        self._lock = threading.Lock()
        try:
            self._items: Dict[str, Dict] = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self._items = {}

    def _save(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix('.tmp')
            tmp.write_text(json.dumps(self._items))
            tmp.replace(self.state_file)
        except OSError as e:
            logger.warning(f"Couldn't save ROM hashes: {e}")

    def hashes(self, path: Path, unzip: bool = True, cached_only: bool = False) -> Optional[Dict[str, str]]:
        """{'md5', 'sha1', 'crc32'} of a ROM file, or None when it isn't a file, is
        over HASH_LIMIT or can't be read. With `unzip` off, a .zip is hashed as it
        is (arcade sets)."""
        path = Path(path)
        try:
            stat = path.stat()
        except OSError:
            return None
        if not path.is_file() or stat.st_size > HASH_LIMIT:
            return None

        key = f"{path}|{int(unzip)}"
        stamp = [stat.st_size, stat.st_mtime_ns]
        with self._lock:
            cached = self._items.get(key)
        if cached and cached.get('stamp') == stamp:
            return cached['hashes']
        if cached_only:
            return None

        handle = open_rom(path, unzip)
        if handle is None:
            return None
        md5, sha1, crc = hashlib.md5(), hashlib.sha1(), 0
        try:
            with handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    md5.update(chunk)
                    sha1.update(chunk)
                    crc = zlib.crc32(chunk, crc)
        except OSError as e:
            logger.warning(f"Couldn't hash {path}: {e}")
            return None

        result = {'md5': md5.hexdigest(), 'sha1': sha1.hexdigest(), 'crc32': f"{crc & 0xffffffff:08x}"}
        with self._lock:
            self._items[key] = {'stamp': stamp, 'hashes': result}
            self._save()
        return result
