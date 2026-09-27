"""
Adding new games: files uploaded from a browser (in resumable chunks) or
dropped in the inbox folder are grouped into games, given a system, and then
filed into roms/<system>/.

Uploads are staged in INBOX_PATH/.uploads/<id>/ (hidden from the inbox list),
so half-finished files never land in roms/, which other devices may sync. The
inbox is INBOX_PATH; a file in inbox/<system>/ gets that system. Without an
inbox, uploads are staged in DATA_PATH/uploads/.

Grouping:
  - a .cue and the track files it names are one game;
  - discs of one game ("… (Disc 1)", "… (Disc 2)") are one game, filed with an
    .m3u playlist;
  - anything else is a game of its own.
"""

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.scanner import DISC_TAG_RE, _CUE_FILE_RE
from backend.systems import screenscraper_system_id

# Extension -> likely systems (folder-style names, matched to your folders by
# ScreenScraper system id, so "genesis" also finds a "megadrive" folder)
EXTENSION_SYSTEMS = {
    '.nes': ['nes'], '.fds': ['fds'], '.unf': ['nes'], '.unif': ['nes'],
    '.sfc': ['snes'], '.smc': ['snes'], '.fig': ['snes'], '.swc': ['snes'],
    '.n64': ['n64'], '.z64': ['n64'], '.v64': ['n64'],
    '.gb': ['gb'], '.sgb': ['gb'], '.gbc': ['gbc'], '.gba': ['gba'],
    '.nds': ['nds'], '.dsi': ['nds'], '.3ds': ['3ds'], '.cia': ['3ds'], '.cci': ['3ds'], '.3dsx': ['3ds'],
    '.gcm': ['gc'], '.gcz': ['gc'], '.rvz': ['gc', 'wii'], '.ciso': ['gc', 'wii'],
    '.wbfs': ['wii'], '.wad': ['wii'], '.wia': ['wii'],
    '.xci': ['nsw'], '.nsp': ['nsw'],
    '.vb': ['virtualboy'], '.min': ['pokemini'],
    '.md': ['megadrive'], '.gen': ['megadrive'], '.smd': ['megadrive'],
    '.sms': ['mastersystem'], '.gg': ['gamegear'], '.32x': ['sega32x'], '.sg': ['sg1000'],
    '.gdi': ['dreamcast'], '.cdi': ['dreamcast'],
    '.pce': ['pcengine'], '.sgx': ['supergrafx'],
    '.ngp': ['ngp'], '.ngc': ['ngpc'], '.ws': ['wonderswan'], '.wsc': ['wonderswancolor'],
    '.a26': ['atari2600'], '.a52': ['atari5200'], '.a78': ['atari7800'], '.lnx': ['atarilynx'],
    '.j64': ['atarijaguar'], '.jag': ['atarijaguar'],
    '.col': ['colecovision'], '.vec': ['vectrex'], '.int': ['intellivision'],
    '.d64': ['c64'], '.t64': ['c64'], '.prg': ['c64'], '.tap': ['c64', 'zxspectrum'],
    '.tzx': ['zxspectrum'], '.z80': ['zxspectrum'], '.dsk': ['amstradcpc', 'msx'],
    '.adf': ['amiga'], '.st': ['atarist'],
    '.cso': ['psp'], '.pbp': ['psx', 'psp'],
    # Disc images: narrowed down by looking inside (see sniff_disc)
    '.iso': ['psx', 'ps2', 'psp', 'gc', 'wii', 'segacd', 'saturn', 'dreamcast', 'pcenginecd', '3do'],
    '.cue': ['psx', 'segacd', 'saturn', 'pcenginecd', '3do', 'dreamcast'],
    '.bin': ['psx', 'segacd', 'saturn', 'megadrive', 'atari2600'],
    '.img': ['psx', 'segacd', 'saturn'],
    '.chd': ['psx', 'ps2', 'segacd', 'saturn', 'dreamcast', 'pcenginecd', '3do'],
    '.ccd': ['psx', 'segacd', 'saturn'], '.mds': ['psx', 'segacd', 'saturn'],
    '.m3u': ['psx', 'segacd', 'saturn', 'dreamcast'],
}

# Files a .cue names, which travel with it
TRACK_EXTENSIONS = {'.bin', '.img', '.wav', '.iso', '.raw', '.ogg', '.mp3', '.flac'}


def safe_name(name: str) -> str:
    """A file name without any folder part or characters the NAS can't store."""
    name = os.path.basename((name or '').replace('\\', '/')).strip()
    name = re.sub(r'[\x00-\x1f<>:"|?*]', '', name)
    return name.lstrip('.') or 'upload'


def sniff_disc(path: Path, size: int) -> Optional[str]:
    """Which system a disc image is for, from markers near its start, or None."""
    try:
        with open(path, 'rb') as f:
            head = f.read(0x10000)
    except OSError:
        return None
    if len(head) >= 0x20 and head[0x1C:0x20] == b'\xc2\x33\x9f\x3d':
        return 'gc'
    if len(head) >= 0x1C and head[0x18:0x1C] == b'\x5d\x1c\x9e\xa3':
        return 'wii'
    if head.startswith(b'WBFS'):
        return 'wii'
    if b'SEGA SEGASATURN' in head[:0x200]:
        return 'saturn'
    if b'SEGADISCSYSTEM' in head[:0x200] or b'SEGA SEGACD' in head[:0x200]:
        return 'segacd'
    if b'PSP GAME' in head:
        return 'psp'
    if b'PLAYSTATION' in head:
        # Both PlayStations say this; PS2 games are DVDs, far bigger than a CD
        return 'ps2' if size > 900 * 1024 * 1024 else 'psx'
    if b'PC Engine CD-ROM' in head or b'PC-Engine CD' in head:
        return 'pcenginecd'
    return None


def md5_of(path: Path, limit: int = 1024 * 1024 * 1024) -> Optional[str]:
    """MD5 checksum (skipped for files over `limit`, which take too long on the NAS)."""
    try:
        if path.stat().st_size > limit:
            return None
        digest = hashlib.md5()
        with open(path, 'rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


class Importer:
    def __init__(self, roms_base: str, inbox_base: str, system_folders: Callable, data_dir: Path):
        self.roms_base = Path(roms_base)
        self.inbox = Path(inbox_base) if inbox_base else None
        self.upload_dir = (self.inbox / '.uploads') if self.inbox_available() else Path(data_dir) / 'uploads'
        self.system_folders = system_folders

    # ------------------------------------------------------------------
    # Uploads, in chunks that can resume after a dropped connection
    # ------------------------------------------------------------------

    def _meta_path(self, upload_id: str) -> Path:
        return self.upload_dir / upload_id / 'upload.json'

    def _read_meta(self, upload_id: str) -> Optional[Dict]:
        if not re.fullmatch(r'[0-9a-f]{16}', upload_id or ''):
            return None
        try:
            return json.loads(self._meta_path(upload_id).read_text())
        except (OSError, ValueError):
            return None

    def _data_path(self, upload_id: str, meta: Dict) -> Path:
        return self.upload_dir / upload_id / meta['name']

    def start_upload(self, name: str, size: int, key: str) -> Dict:
        """Start (or resume) an upload. The same key (name, size and date of the
        file on the device) gets the same upload back, with what already arrived."""
        name = safe_name(name)
        upload_id = hashlib.sha1(f"{key}|{name}|{size}".encode()).hexdigest()[:16]
        meta = self._read_meta(upload_id)
        if not meta:
            meta = {'id': upload_id, 'name': name, 'size': int(size), 'created': time.time()}
            folder = self.upload_dir / upload_id
            folder.mkdir(parents=True, exist_ok=True)
            self._meta_path(upload_id).write_text(json.dumps(meta))
            self._data_path(upload_id, meta).touch()
        return self.upload_status(upload_id)

    def upload_status(self, upload_id: str) -> Optional[Dict]:
        meta = self._read_meta(upload_id)
        if not meta:
            return None
        data = self._data_path(upload_id, meta)
        received = data.stat().st_size if data.exists() else 0
        return {**meta, 'received': received, 'complete': received >= meta['size']}

    def write_chunk(self, upload_id: str, offset: int, stream, length: int) -> Dict:
        """Write a chunk that starts at `offset`. A retried chunk overwrites from its
        offset; one that would leave a gap is refused."""
        status = self.upload_status(upload_id)
        if not status:
            raise KeyError('Unknown upload')
        if offset > status['received']:
            raise ValueError(f"Expected data from byte {status['received']}")
        data = self._data_path(upload_id, status)
        with open(data, 'r+b') as f:
            f.truncate(offset)
            f.seek(offset)
            remaining = min(length, status['size'] - offset)
            while remaining > 0:
                block = stream.read(min(1024 * 1024, remaining))
                if not block:
                    break
                f.write(block)
                remaining -= len(block)
        return self.upload_status(upload_id)

    def save_whole(self, name: str, stream) -> Dict:
        """A file that arrives in one piece (shared from another app)."""
        name = safe_name(name)
        upload_id = hashlib.sha1(f"share|{name}|{time.time()}".encode()).hexdigest()[:16]
        folder = self.upload_dir / upload_id
        folder.mkdir(parents=True, exist_ok=True)
        data = folder / name
        with open(data, 'wb') as f:
            shutil.copyfileobj(stream, f, 1024 * 1024)
        meta = {'id': upload_id, 'name': name, 'size': data.stat().st_size, 'created': time.time()}
        self._meta_path(upload_id).write_text(json.dumps(meta))
        return self.upload_status(upload_id)

    def discard_upload(self, upload_id: str) -> bool:
        if not self._read_meta(upload_id):
            return False
        shutil.rmtree(self.upload_dir / upload_id, ignore_errors=True)
        return True

    def uploads(self) -> List[Dict]:
        if not self.upload_dir.is_dir():
            return []
        items = [self.upload_status(p.name) for p in self.upload_dir.iterdir() if p.is_dir()]
        return sorted((i for i in items if i), key=lambda i: i['created'])

    # ------------------------------------------------------------------
    # Inbox
    # ------------------------------------------------------------------

    def inbox_available(self) -> bool:
        return bool(self.inbox and self.inbox.is_dir())

    def inbox_files(self) -> List[Dict]:
        if not self.inbox_available():
            return []
        items = []
        for f in sorted(self.inbox.rglob('*')):
            rel = f.relative_to(self.inbox)
            if not f.is_file() or any(part.startswith('.') for part in rel.parts) or f.suffix.lower() in ('.part', '.tmp'):
                continue
            items.append({'ref': f"inbox:{rel.as_posix()}", 'name': f.name, 'rel': rel.as_posix(),
                          'size': f.stat().st_size, 'folder': rel.parts[0] if len(rel.parts) > 1 else None})
        return items

    # ------------------------------------------------------------------
    # From refs to games
    # ------------------------------------------------------------------

    def resolve(self, ref: str) -> Optional[Dict]:
        """'upload:<id>' or 'inbox:<path>' -> {ref, path, name, size, folder hint}."""
        kind, _, value = (ref or '').partition(':')
        if kind == 'upload':
            status = self.upload_status(value)
            if not status or not status['complete']:
                return None
            return {'ref': ref, 'path': self._data_path(value, status), 'name': status['name'],
                    'size': status['size'], 'hint': None}
        if kind == 'inbox' and self.inbox_available():
            path = (self.inbox / value).resolve()
            if not str(path).startswith(str(self.inbox.resolve()) + os.sep) or not path.is_file():
                return None
            rel = path.relative_to(self.inbox.resolve())
            return {'ref': ref, 'path': path, 'name': path.name, 'size': path.stat().st_size,
                    'hint': rel.parts[0] if len(rel.parts) > 1 else None}
        return None

    def group(self, files: List[Dict]) -> List[Dict]:
        """Files -> games: [{files: [file…], main: file, discs: [file…] | None, missing: [names]}]."""
        by_name = {f['name'].lower(): f for f in files}
        used = set()
        games = []
        # A .cue takes the tracks it names
        for f in files:
            if Path(f['name']).suffix.lower() != '.cue':
                continue
            try:
                text = f['path'].read_text(encoding='utf-8', errors='replace') if f['size'] < 256 * 1024 else ''
            except OSError:
                text = ''
            names = [os.path.basename((m.group(1) or m.group(2)).replace('\\', '/')) for m in _CUE_FILE_RE.finditer(text)]
            tracks = [by_name[n.lower()] for n in names if n.lower() in by_name]
            missing = [n for n in names if n.lower() not in by_name]
            games.append({'files': [f] + tracks, 'main': f, 'missing': missing})
            used.update(id(x) for x in [f] + tracks)
        for f in files:
            if id(f) not in used:
                games.append({'files': [f], 'main': f, 'missing': []})
        # Discs of one game become one game
        merged, by_base = [], {}
        for g in games:
            stem = Path(g['main']['name']).stem
            m = DISC_TAG_RE.search(stem)
            if not m:
                merged.append(g)
                continue
            base = DISC_TAG_RE.sub('', stem).strip()
            key = (base.lower(), g['main'].get('hint'))
            if key in by_base:
                by_base[key]['discs'].append((int(m.group(1)), g))
            else:
                entry = {'base': base, 'discs': [(int(m.group(1)), g)]}
                by_base[key] = entry
                merged.append(entry)
        result = []
        for g in merged:
            if 'discs' not in g:
                result.append({**g, 'discs': None})
                continue
            discs = [d for _, d in sorted(g['discs'], key=lambda x: x[0])]
            if len(discs) == 1:
                result.append({**discs[0], 'discs': None})
                continue
            result.append({'files': [f for d in discs for f in d['files']], 'main': discs[0]['main'],
                           'discs': [d['main'] for d in discs], 'base': g['base'],
                           'missing': [n for d in discs for n in d['missing']]})
        return result

    def systems_for(self, game: Dict) -> Dict:
        """{'systems': [folders, likeliest first], 'reason': why}. Only folders you have."""
        folders = sorted(self.system_folders())
        main = game['main']
        hint = main.get('hint')
        if hint and hint in folders:
            return {'systems': [hint], 'reason': f"it was in the inbox's {hint} folder"}

        def existing(candidates):
            out = []
            for c in candidates:
                target = screenscraper_system_id(c)
                for folder in folders:
                    if folder not in out and (folder.lower() == c or (target and screenscraper_system_id(folder) == target)):
                        out.append(folder)
            return out

        ext = Path(main['name']).suffix.lower()
        disc_file = main
        if ext == '.cue' and len(game['files']) > 1:
            disc_file = game['files'][1]
        sniffed = sniff_disc(disc_file['path'], sum(f['size'] for f in game['files'])) \
            if Path(disc_file['name']).suffix.lower() in ('.iso', '.bin', '.img', '.cue', '.ciso', '.rvz', '.gcm') else None
        candidates = EXTENSION_SYSTEMS.get(ext, [])
        if sniffed:
            found = existing([sniffed])
            if found:
                return {'systems': found + [s for s in existing(candidates) if s not in found], 'reason': 'found in the disc image'}
        found = existing(candidates)
        if found:
            reason = 'from the file type' if len(found) == 1 else 'the file type fits several systems'
            return {'systems': found, 'reason': reason}
        return {'systems': [], 'reason': "the file type doesn't say"}

    def move_into(self, file: Dict, target: Path):
        """Move a staged upload or inbox file to its place in roms/."""
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file['path']), str(target))
        if file['ref'].startswith('upload:'):
            shutil.rmtree(self.upload_dir / file['ref'].split(':', 1)[1], ignore_errors=True)
        elif self.inbox_available():
            # Tidy empty folders left in the inbox
            parent = Path(file['path']).parent
            while parent != self.inbox and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
