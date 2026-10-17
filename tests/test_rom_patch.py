"""ROM patches (IPS, UPS, BPS): applied, checked against their checksums, and put in place of a game's
ROM or beside it as a new game. The patches are made here, to each format's rules."""

import zlib

import pytest

from backend.rom_patch import PatchError, apply_patch


def _crc(b):
    return (zlib.crc32(b) & 0xFFFFFFFF).to_bytes(4, 'little')


def _number(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def ips(changes, truncate=None):
    body = b''.join(off.to_bytes(3, 'big') + len(data).to_bytes(2, 'big') + data for off, data in changes)
    return b'PATCH' + body + b'EOF' + (truncate.to_bytes(3, 'big') if truncate is not None else b'')


def ups(source, target):
    body, at, last = bytearray(), 0, 0
    while at < len(target):
        s = source[at] if at < len(source) else 0
        if s == target[at]:
            at += 1
            continue
        body += _number(at - last)
        while at < len(target) and (source[at] if at < len(source) else 0) != target[at]:
            body.append((source[at] if at < len(source) else 0) ^ target[at])
            at += 1
        body.append(0)
        at += 1
        last = at
    patch = b'UPS1' + _number(len(source)) + _number(len(target)) + bytes(body) + _crc(source) + _crc(target)
    return patch + _crc(patch)


def bps(source, target):
    # Source reads where they match, target reads where they don't, and a target copy for a repeated run
    body, at = bytearray(), 0
    while at < len(target):
        same = at < len(source) and source[at] == target[at]
        end = at
        while end < len(target) and (end < len(source) and source[end] == target[end]) == same:
            end += 1
        body += _number(((end - at - 1) << 2) | (0 if same else 1))
        if not same:
            body += target[at:end]
        at = end
    patch = b'BPS1' + _number(len(source)) + _number(len(target)) + _number(0) + bytes(body) + _crc(source) + _crc(target)
    return patch + _crc(patch)


ROM = bytes(range(256)) * 8          # 2 KB


def test_ips_is_applied_and_can_grow_or_cut_the_rom():
    patched, notes = apply_patch(ROM, ips([(10, b'HACK'), (2050, b'MORE')]))
    assert patched[10:14] == b'HACK' and patched[2050:2054] == b'MORE' and len(patched) == 2054
    rle = b'PATCH' + (5).to_bytes(3, 'big') + b'\0\0' + (3).to_bytes(2, 'big') + b'Z' + b'EOF'
    assert apply_patch(ROM, rle)[0][5:8] == b'ZZZ'
    assert len(apply_patch(ROM, ips([(0, b'X')], truncate=1024))[0]) == 1024
    assert any('no checksums' in n for n in notes)


@pytest.mark.parametrize('make', [ups, bps])
def test_ups_and_bps_are_applied_and_checked(make):
    target = bytearray(ROM)
    target[100:110] = b'TRANSLATED'
    target += b'EXTRA DATA'
    patched, notes = apply_patch(ROM, make(ROM, bytes(target)))
    assert patched == bytes(target) and any('checked' in n for n in notes)
    with pytest.raises(PatchError, match='different ROM'):
        apply_patch(ROM[:-1] + b'?', make(ROM, bytes(target)))
    damaged = bytearray(make(ROM, bytes(target)))
    damaged[6] ^= 0xFF
    with pytest.raises(PatchError, match='damaged'):
        apply_patch(ROM, bytes(damaged))


def test_an_snes_rom_with_a_copier_header_is_patched_without_it():
    target = ROM[:500] + b'!' + ROM[501:]
    patched, notes = apply_patch(b'\0' * 512 + ROM, bps(ROM, target))
    assert patched == target and any('header' in n for n in notes)


def test_not_a_patch():
    with pytest.raises(PatchError):
        apply_patch(ROM, b'just some file')


def _upload(client, name, data):
    started = client.post("/api/uploads", json={"name": name, "size": len(data), "key": f"patch|{name}|{len(data)}"}).get_json()
    client.put(f"/api/uploads/{started['id']}?offset=0", data=data, headers={"Content-Type": "application/octet-stream"})
    return started["id"]


def test_a_patch_makes_a_new_game_or_replaces_the_rom(client, root):
    base = root / "roms" / "gba" / "Base Game.gba"
    base.write_bytes(ROM)
    hacked = ROM[:64] + b'EMERALD CREST' + ROM[77:]

    made = client.post("/api/systems/gba/patch-rom", json={"rom": "Base Game.gba", "upload": _upload(client, "Base Hack v1.bps", bps(ROM, hacked)),
                                                          "as": "new", "name": "Base Hack", "version": "1.0"}).get_json()
    assert made["success"] and made["rom"] == "Base Hack.gba", made
    assert (root / "roms" / "gba" / "Base Hack.gba").read_bytes() == hacked and base.read_bytes() == ROM   # the base game stays
    assert made["version"] == "1.0" and made["patched_from"] == {"rom": "Base Game.gba", "patch": "Base Hack v1.bps"}
    assert made["crc32"] == f"{zlib.crc32(hacked) & 0xFFFFFFFF:08x}"
    listed = {g["path"].lstrip("./"): g for g in client.get("/api/systems/gba/games").get_json()["games"]}
    assert listed["Base Hack.gba"]["name"] == "Base Hack" and listed["Base Hack.gba"]["rom_version"] == "1.0"

    # The hack's next version, over the first
    v2 = hacked[:200] + b'V2' + hacked[202:]
    swapped = client.post("/api/systems/gba/patch-rom", json={"rom": "Base Hack.gba", "upload": _upload(client, "Base Hack v1-to-v2.ups", ups(hacked, v2)),
                                                             "as": "replace", "version": "2.0"}).get_json()
    assert swapped["success"] and swapped["rom"] == "Base Hack.gba"
    assert (root / "roms" / "gba" / "Base Hack.gba").read_bytes() == v2
    assert (root / "data" / swapped["kept"]).read_bytes() == hacked
    assert swapped["history"][0]["version"] == "1.0" and swapped["history"][0]["then_patched_with"] == "Base Hack v1-to-v2.ups"

    # (where a new game came from is kept even with no version noted)
    plain = client.post("/api/systems/gba/patch-rom", json={"rom": "Base Game.gba", "upload": _upload(client, "Plain.ips", ips([(0, b'P')])), "as": "new", "name": "Plain Hack"}).get_json()
    assert plain["patched_from"]["patch"] == "Plain.ips"

    wrong = client.post("/api/systems/gba/patch-rom", json={"rom": "Base Game.gba", "upload": _upload(client, "Other.bps", bps(b'x' * 2048, b'y' * 2048)), "as": "replace"}).get_json()
    assert not wrong["success"] and "different ROM" in wrong["error"] and base.read_bytes() == ROM


def test_bps_copies_from_the_rom_and_from_its_own_result():
    # The result: 10 bytes of the ROM from offset 100, then "AB" repeated by copying itself (overlapping)
    target = ROM[100:110] + b'AB' * 5
    body = (_number(((10 - 1) << 2) | 2) + _number(100 << 1)              # SourceCopy 10 from +100
            + _number(((2 - 1) << 2) | 1) + b'AB'                          # TargetRead "AB"
            + _number(((8 - 1) << 2) | 3) + _number(10 << 1))              # TargetCopy 8 from result offset 10
    patch = b'BPS1' + _number(len(ROM)) + _number(len(target)) + _number(0) + body + _crc(ROM) + _crc(target)
    assert apply_patch(ROM, patch + _crc(patch))[0] == target
