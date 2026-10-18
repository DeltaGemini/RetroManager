"""A game's ROM replaced by an updated one: it takes the old name, the old one is kept, and the version is noted."""


def _upload(client, name, data):
    started = client.post("/api/uploads", json={"name": name, "size": len(data), "key": f"test|{name}|{data[:4].hex()}"}).get_json()
    client.put(f"/api/uploads/{started['id']}?offset=0", data=data, headers={"Content-Type": "application/octet-stream"})
    return started["id"]


def test_an_updated_rom_takes_the_old_name_and_the_old_one_is_kept(client, root):
    rom = root / "roms" / "gba" / "Patched Quest.gba"
    rom.write_bytes(b"old!" * 1024)
    assert client.put("/api/systems/gba/rom-version", json={"rom": "Patched Quest.gba", "version": "1.0"}).get_json()["version"] == "1.0"

    upload = _upload(client, "patched-quest-v1.1.gba", b"new!" * 1024)
    done = client.post("/api/systems/gba/replace-rom", json={"rom": "./Patched Quest.gba", "upload": upload, "version": "1.1"}).get_json()
    assert done["success"] and done["rom"] == "Patched Quest.gba"                # its name, so its saves still match
    assert rom.read_bytes() == b"new!" * 1024
    kept = root / "data" / done["kept"]
    assert kept.read_bytes() == b"old!" * 1024 and "replaced-roms" in done["kept"]
    record = client.get("/api/systems/gba/rom-version?rom=Patched%20Quest.gba").get_json()
    assert record["version"] == "1.1" and record["history"][0]["version"] == "1.0"


def test_another_kind_of_file_keeps_the_name_with_its_own_extension(client, root):
    (root / "roms" / "gba" / "Zipped Quest.gba").write_bytes(b"rom" * 100)
    upload = _upload(client, "Zipped Quest (v2).zip", b"PK\x03\x04zip" * 50)
    done = client.post("/api/systems/gba/replace-rom", json={"rom": "Zipped Quest.gba", "upload": upload}).get_json()
    assert done["success"] and done["rom"] == "Zipped Quest.zip"
    assert (root / "roms" / "gba" / "Zipped Quest.zip").is_file() and not (root / "roms" / "gba" / "Zipped Quest.gba").exists()


def test_a_disc_and_an_unfinished_upload_are_refused(client, root):
    disc = client.post("/api/systems/psx/replace-rom", json={"rom": "Disc Game.cue", "upload": "nothing"}).get_json()
    assert not disc["success"] and "several files" in disc["error"]
    (root / "roms" / "gba" / "Waiting.gba").write_bytes(b"w" * 10)
    started = client.post("/api/uploads", json={"name": "Waiting.gba", "size": 100, "key": "unfinished"}).get_json()
    half = client.post("/api/systems/gba/replace-rom", json={"rom": "Waiting.gba", "upload": started["id"]}).get_json()
    assert not half["success"] and (root / "roms" / "gba" / "Waiting.gba").read_bytes() == b"w" * 10


def test_a_version_noted_comes_with_the_game(client, root):
    (root / "roms" / "gba" / "Indie Game.gba").write_bytes(b"i" * 64)
    client.put("/api/systems/gba/rom-version", json={"rom": "Indie Game.gba", "version": "2024-06-01"})
    listed = {g["path"].lstrip("./"): g for g in client.get("/api/systems/gba/games").get_json()["games"]}
    assert listed["Indie Game.gba"]["rom_version"] == "2024-06-01" and listed["Pocket Game.gba"]["rom_version"] == ""
    assert client.get("/api/systems/gba/games/Indie%20Game.gba").get_json()["game"]["rom_version"] == "2024-06-01"


def test_replacing_or_patching_says_whether_retroachievements_still_knows_the_game(client, root, monkeypatch):
    from backend.routes import rom_replace
    # RetroAchievements stood in for: it knows the original dump, and a known hack of it
    known = {b"ORIGINAL" * 64: {'id': 10, 'title': 'Achieved Quest', 'achievements': 42},
             b"KNOWNHAK" * 64: {'id': 11, 'title': 'Achieved Quest Hack', 'achievements': 7}}
    monkeypatch.setattr(rom_replace, '_ra_checked', lambda system: True)
    monkeypatch.setattr(rom_replace, '_ra_game', lambda system, path: known.get(path.read_bytes()))
    rom = root / "roms" / "gba" / "Achieved Quest.gba"
    rom.write_bytes(b"ORIGINAL" * 64)

    changed = client.post("/api/systems/gba/replace-rom", json={"rom": "Achieved Quest.gba", "upload": _upload(client, "aq-fixed.gba", b"0RIGINAL" * 64)}).get_json()
    assert changed["achievements"] == {"before": known[b"ORIGINAL" * 64], "now": None}          # no longer recognised
    back = client.post("/api/systems/gba/replace-rom", json={"rom": "Achieved Quest.gba", "upload": _upload(client, "aq-original.gba", b"ORIGINAL" * 64)}).get_json()
    assert back["achievements"]["now"]["title"] == "Achieved Quest"                              # recognised again

    hack = b"PATCH" + (0).to_bytes(3, "big") + (512).to_bytes(2, "big") + b"KNOWNHAK" * 64 + b"EOF"
    made = client.post("/api/systems/gba/patch-rom", json={"rom": "Achieved Quest.gba", "upload": _upload(client, "Known Hack.ips", hack), "as": "new", "name": "Known Hack"}).get_json()
    assert made["achievements"] == {"before": known[b"ORIGINAL" * 64], "now": known[b"KNOWNHAK" * 64]}
    # ...and the game's Achievements section goes by it
    from backend.core import ra_game_ids
    assert ra_game_ids.get("gba/Known Hack.gba", root / "roms" / "gba" / "Known Hack.gba") == (True, 11)

    monkeypatch.setattr(rom_replace, '_ra_checked', lambda system: False)
    plain = client.post("/api/systems/gba/replace-rom", json={"rom": "Achieved Quest.gba", "upload": _upload(client, "aq3.gba", b"x" * 512)}).get_json()
    assert plain["success"] and plain["achievements"] is None                                    # no key: not asked
