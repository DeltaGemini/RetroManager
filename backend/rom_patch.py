"""
Applying a ROM patch: IPS, UPS or BPS, the formats ROM hacks and translations come in.

UPS and BPS patches carry the checksum (CRC32) of the ROM they're made for and of
the result, so a patch for another ROM (another region, another revision) is
refused, and the result is checked. IPS has no checksums: it's applied as it is.
An SNES ROM with the 512-byte header some dumps have is tried without it when the
patch's checksum says it's for a ROM without one (most are).

    patched, notes = apply_patch(rom_bytes, patch_bytes)   # raises PatchError
"""

import zlib
from typing import List, Tuple


class PatchError(Exception):
    pass


def _crc(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def kind_of(patch: bytes) -> str:
    if patch[:5] == b'PATCH':
        return 'ips'
    if patch[:4] == b'UPS1':
        return 'ups'
    if patch[:4] == b'BPS1':
        return 'bps'
    raise PatchError("That isn't an IPS, UPS or BPS patch")


class _Reader:
    def __init__(self, data: bytes, at: int):
        self.data, self.at = data, at

    def byte(self) -> int:
        if self.at >= len(self.data):
            raise PatchError("The patch is cut short")
        b = self.data[self.at]
        self.at += 1
        return b

    def bytes(self, n: int) -> bytes:
        if self.at + n > len(self.data):
            raise PatchError("The patch is cut short")
        chunk = self.data[self.at:self.at + n]
        self.at += n
        return chunk

    def number(self) -> int:
        """UPS and BPS's variable-length numbers."""
        value, shift = 0, 1
        while True:
            x = self.byte()
            value += (x & 0x7F) * shift
            if x & 0x80:
                return value
            shift <<= 7
            value += shift


def _ips(rom: bytes, patch: bytes) -> bytes:
    out = bytearray(rom)
    r = _Reader(patch, 5)
    while True:
        head = r.bytes(3)
        if head == b'EOF':
            break
        offset = int.from_bytes(head, 'big')
        size = int.from_bytes(r.bytes(2), 'big')
        if size:
            data = r.bytes(size)
        else:   # (run-length: one byte, repeated)
            count = int.from_bytes(r.bytes(2), 'big')
            data = bytes([r.byte()]) * count
        if offset + len(data) > len(out):
            out.extend(b'\0' * (offset + len(data) - len(out)))
        out[offset:offset + len(data)] = data
    # (an IPS patch can end with the size to cut the result to)
    if len(patch) - r.at >= 3:
        out = out[:int.from_bytes(patch[r.at:r.at + 3], 'big')]
    return bytes(out)


def _footer(patch: bytes) -> Tuple[int, int, int]:
    if len(patch) < 16:
        raise PatchError("The patch is cut short")
    if _crc(patch[:-4]) != int.from_bytes(patch[-4:], 'little'):
        raise PatchError("The patch file is damaged (its own checksum doesn't match)")
    return int.from_bytes(patch[-12:-8], 'little'), int.from_bytes(patch[-8:-4], 'little'), len(patch) - 12


def _ups(rom: bytes, patch: bytes) -> bytes:
    source_crc, target_crc, end = _footer(patch)
    if _crc(rom) != source_crc:
        raise _WrongRom()
    r = _Reader(patch, 4)
    r.number()   # (the source's size: the checksum has settled that)
    target_size = r.number()
    out = bytearray(target_size)
    out[:min(len(rom), target_size)] = rom[:target_size]
    at = 0
    while r.at < end:
        at += r.number()
        while True:
            x = r.byte()
            if at < target_size:
                out[at] = (rom[at] if at < len(rom) else 0) ^ x
            at += 1
            if x == 0:
                break
    if _crc(out) != target_crc:
        raise PatchError("Patched, but the result isn't what the patch says it makes")
    return bytes(out)


def _bps(rom: bytes, patch: bytes) -> bytes:
    source_crc, target_crc, end = _footer(patch)
    if _crc(rom) != source_crc:
        raise _WrongRom()
    r = _Reader(patch, 4)
    r.number()   # (the source's size)
    target_size = r.number()
    r.bytes(r.number())   # (metadata)
    out = bytearray(target_size)
    at = source_at = target_at = 0
    while r.at < end:
        data = r.number()
        command, length = data & 3, (data >> 2) + 1
        if at + length > target_size:
            raise PatchError("The patch writes past the end of the result")
        if command == 0:     # the source's bytes at the same place
            out[at:at + length] = rom[at:at + length].ljust(length, b'\0')
            at += length
        elif command == 1:   # bytes in the patch
            out[at:at + length] = r.bytes(length)
            at += length
        elif command == 2:   # the source's bytes from elsewhere
            d = r.number()
            source_at += -(d >> 1) if d & 1 else (d >> 1)
            out[at:at + length] = rom[source_at:source_at + length].ljust(length, b'\0')
            source_at += length
            at += length
        else:                # the result's own bytes from earlier (can overlap)
            d = r.number()
            target_at += -(d >> 1) if d & 1 else (d >> 1)
            for _ in range(length):
                out[at] = out[target_at]
                at += 1
                target_at += 1
    if _crc(out) != target_crc:
        raise PatchError("Patched, but the result isn't what the patch says it makes")
    return bytes(out)


class _WrongRom(PatchError):
    def __init__(self):
        super().__init__("This patch is for a different ROM (another region or revision, most likely): its checksum doesn't match this one")


def apply_patch(rom: bytes, patch: bytes) -> Tuple[bytes, List[str]]:
    """The patched ROM, and notes on how it went (said to the person)."""
    kind = kind_of(patch)
    notes = [f"{kind.upper()} patch"]
    if kind == 'ips':
        notes.append("IPS patches carry no checksums, so whether it suits this ROM can't be checked")
        return _ips(rom, patch), notes
    patcher = _ups if kind == 'ups' else _bps
    try:
        result = patcher(rom, patch)
        notes.append("the ROM and the result checked against the patch's checksums")
        return result, notes
    except _WrongRom:
        # An SNES dump with a 512-byte copier header: most patches are for the ROM without it
        if len(rom) % 1024 == 512:
            result = patcher(rom[512:], patch)
            notes.append("the ROM's 512-byte header taken off first, as the patch wants; the result has none")
            return result, notes
        raise
