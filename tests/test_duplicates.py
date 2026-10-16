"""The Duplicates tool: both checks' groups as one list."""


def test_games_more_than_once_are_listed_with_why(client, root):
    (root / "roms" / "snes" / "Twin Quest (USA).sfc").write_bytes(b"\x05" * 4096)
    (root / "roms" / "snes" / "Twin Quest (Europe).sfc").write_bytes(b"\x06" * 4096)
    d = client.get("/api/duplicates?system=snes").get_json()
    group = next(g for g in d["groups"] if {c["path"] for c in g["copies"]} == {"Twin Quest (USA).sfc", "Twin Quest (Europe).sfc"})
    assert group["reasons"] == ["name"] and group["system"] == "snes" and group["keep"].startswith("snes/twin quest")
    assert all(c["size"] == 4096 and c["system"] == "snes" for c in group["copies"])
    # Another system's duplicates aren't in one system's list
    assert all(g["system"] == "snes" for g in d["groups"])


def test_a_group_found_both_ways_is_marked_with_both(client, root, monkeypatch):
    from backend.routes import duplicates
    (root / "roms" / "snes" / "Same File (USA).sfc").write_bytes(b"\x07" * 4096)
    (root / "roms" / "snes" / "Same File (Europe).sfc").write_bytes(b"\x07" * 4096)
    found = [{"system": "snes", "rom_path": p, "name": "Same File"} for p in ("Same File (USA).sfc", "Same File (Europe).sfc", "Other.sfc")]
    monkeypatch.setattr(duplicates.rom_index, "report", lambda systems: {"duplicates": [found], "counts": {"known": 3}})
    groups = client.get("/api/duplicates?system=snes").get_json()["groups"]
    named = next(g for g in groups if g["reasons"][0] == "name" and any(c["path"] == "Same File (USA).sfc" for c in g["copies"]))
    assert named["reasons"] == ["name", "contents"]
    # The identical files' own group stays, as it has a copy the name group hasn't
    assert any(g["reasons"] == ["contents"] and len(g["copies"]) == 3 for g in groups)
