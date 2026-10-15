"""
Reading RetroArch's save states (the ones made on the Pi, or any RetroArch)
so the browser emulator can load them.

A state file is the emulator core's own snapshot, which RetroArch wraps twice:
  - "#RZIPv": compressed in chunks (savestate_file_compression, on by default)
  - "RASTATE": a container of blocks; the "MEM " block is the core's snapshot,
    the others (achievements, replays) are RetroArch's own
A core can only load a snapshot made by the same core, so each one is matched
to the EmulatorJS core that reads it by how the snapshot starts.
"""

import struct
import zlib
from pathlib import Path
from typing import Optional

RZIP_MAGIC = b'#RZIPv'
RASTATE_MAGIC = b'RASTATE'
# The largest state unpacked (an N64 state is 16 MB, a PSP one far more)
MAX_STATE_BYTES = 64 * 1024 * 1024


def _unrzip(data: bytes, limit: Optional[int] = None) -> bytes:
    """The file's contents, uncompressed. `limit` stops after that many bytes
    (enough to see what kind of state it is without unpacking all of it)."""
    if data[:6] != RZIP_MAGIC or data[7:8] != b'#':
        return data if limit is None else data[:limit]
    _chunk_size, total = struct.unpack('<IQ', data[8:20])
    if total > MAX_STATE_BYTES:
        raise ValueError("The save state is too large")
    wanted = total if limit is None else min(total, limit)
    out, pos = bytearray(), 20
    while len(out) < wanted and pos + 4 <= len(data):
        size, = struct.unpack('<I', data[pos:pos + 4])
        pos += 4
        out += zlib.decompress(data[pos:pos + size])
        pos += size
    return bytes(out[:wanted])


def _core_block(raw: bytes) -> bytes:
    """The core's snapshot out of RetroArch's container (or the data itself,
    from a RetroArch too old to use one). May be cut short if `raw` was."""
    if raw[:7] != RASTATE_MAGIC:
        return raw
    pos = 8
    while pos + 8 <= len(raw):
        tag = raw[pos:pos + 4]
        size, = struct.unpack('<I', raw[pos + 4:pos + 8])
        if tag == b'MEM ':
            return raw[pos + 8:pos + 8 + size]
        if tag == b'END ':
            break
        pos += 8 + ((size + 7) & ~7)   # blocks are padded to 8 bytes
    return b''


# How each core's snapshot starts -> (the core's name, the EmulatorJS core that loads it).
# None: recognised, but the browser has no core that reads it.
_SIGNATURES = (
    (lambda b: b[:8] == b'GENPLUS-', 'Genesis Plus GX', 'genesis_plus_gx'),
    (lambda b: b[:4] == b'NST\x1a', 'Nestopia', 'nestopia'),
    (lambda b: b[:8] == b'#!s9xsnp', 'Snes9x', 'snes9x'),
    (lambda b: b[:8] == b'STv4 PCS', 'PCSX ReARMed', 'pcsx_rearmed'),
    (lambda b: b[:8] == b'M64+SAVE', 'Mupen64Plus', 'mupen64plus_next'),
    (lambda b: b[:8] == b'DeSmuME ', 'DeSmuME', 'desmume'),
    (lambda b: b[:8] == b'MDFNSVST', 'Beetle (Mednafen)', None),
    # mGBA: a version number counting up from 0x01000000 (GBA) or 0x00400000 (Game Boy)
    (lambda b: len(b) >= 4 and b[3:4] == b'\x01' and b[1:3] == b'\x00\x00' and 0 < b[0] < 64, 'mGBA', 'mgba'),
    (lambda b: len(b) >= 4 and b[2:4] == b'\x40\x00' and b[1:2] == b'\x00' and 0 < b[0] < 64, 'mGBA', 'mgba'),
)


def identify(snapshot_start: bytes):
    """(core name, EmulatorJS core) for a snapshot, from its first bytes;
    (None, None) if it isn't one we know."""
    for matches, name, emulatorjs_core in _SIGNATURES:
        if matches(snapshot_start):
            return name, emulatorjs_core
    return None, None


def describe(path: Path):
    """(core name, EmulatorJS core) for a state file, reading only its start."""
    try:
        with open(path, 'rb') as f:
            head = f.read(256 * 1024)
        return identify(_core_block(_unrzip(head, limit=4096))[:16])
    except (OSError, ValueError, zlib.error, struct.error):
        return None, None


def snapshot(path: Path) -> bytes:
    """The core's snapshot from a state file, ready for the emulator to load.
    Raises ValueError if the file can't be unpacked."""
    try:
        data = _core_block(_unrzip(Path(path).read_bytes()))
    except (zlib.error, struct.error) as e:
        raise ValueError(f"The save state couldn't be unpacked: {e}")
    if not data:
        raise ValueError("The save state has nothing in it for the emulator")
    return data
