"""The Storage tool: measuring what's been set aside, and deleting only what was asked."""

import time


def _write(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_set_aside_files_are_measured_and_old_ones_deleted(client, root):
    data, saves = root / "data", root / "save-backups"
    now = time.strftime("%Y%m%d-%H%M%S")
    _write(data / "replaced-media" / "20200101-000000" / "snes" / "box2d" / "Old.png", 100)
    _write(data / "replaced-media" / now / "snes" / "box2d" / "New.png", 50)
    _write(saves / "thinned-states" / "20200102-000000" / "snes" / "Game.state1", 30)
    _write(saves / "thinned-states" / now / "snes" / "Game.state2", 20)
    _write(data / "duplicates" / "wii" / "Copy (Europe).rvz", 70)
    (data / "duplicates" / "moved.log").write_text("moved\n")
    _write(data / "thumbs" / "ab" / "abc.webp", 10)

    areas = {a["id"]: a for a in client.get("/api/storage").get_json()["areas"]}
    replaced = {i["id"]: i for i in areas["replaced-media"]["items"]}
    assert replaced["20200101-000000"]["size"] == 100 and replaced["20200101-000000"]["date"].startswith("2020-01-01")
    assert replaced[now]["files"] == 1
    assert {i["id"] for i in areas["save-backups"]["items"]} >= {"thinned-states/20200102-000000", f"thinned-states/{now}"}
    duplicates = [i["id"] for i in areas["duplicates"]["items"]]
    assert "wii/Copy (Europe).rvz" in duplicates and not any("moved.log" in i for i in duplicates)
    assert areas["thumbs"]["cache"] and areas["thumbs"]["size"] == 10

    done = client.post("/api/storage/delete", json={"area": "replaced-media", "older_than_days": 30}).get_json()
    assert done["deleted"] == ["20200101-000000"] and done["freed"] == 100
    assert not (data / "replaced-media" / "20200101-000000").exists() and (data / "replaced-media" / now).is_dir()

    done = client.post("/api/storage/delete", json={"area": "save-backups", "items": ["thinned-states/20200102-000000"]}).get_json()
    assert done["deleted"] == ["thinned-states/20200102-000000"] and (saves / "thinned-states" / now).is_dir()

    # Only what the listing has: nothing outside the area, nothing made up
    refused = client.post("/api/storage/delete", json={"area": "save-backups", "items": ["../roms"]})
    assert refused.status_code == 400 and (root / "roms" / "snes").is_dir()
    assert client.post("/api/storage/delete", json={"area": "roms", "all": True}).status_code == 400

    done = client.post("/api/storage/delete", json={"area": "thumbs", "all": True}).get_json()
    assert done["freed"] == 10 and (data / "thumbs").is_dir() and not any((data / "thumbs").iterdir())
    assert "replaced-media/20200101-000000" in (data / "storage-cleanup.log").read_text()


def test_set_aside_files_are_compared_with_the_librarys(client, root):
    data, media = root / "data", root / "media"
    _write(media / "snes" / "box2d" / "Compare Me.png", 40)
    _write(data / "replaced-media" / "20240101-000000" / "snes" / "box2d" / "Compare Me.jpg", 30)
    _write(data / "replaced-media" / "20240101-000000" / "snes" / "box2d" / "Gone Now.png", 20)
    files = {f["name"]: f for f in client.get("/api/storage/compare?area=replaced-media&item=20240101-000000").get_json()["files"]}
    # The picture now may be another format of the same name
    assert files["Compare Me.jpg"]["now"]["name"] == "Compare Me.png" and files["Compare Me.jpg"]["same"] is False
    assert files["Gone Now.png"]["now"] is None and files["Gone Now.png"]["kind"] == "picture"
    aside = client.get("/api/storage/file?area=replaced-media&item=20240101-000000&rel=snes/box2d/Compare Me.jpg&side=aside")
    now = client.get("/api/storage/file?area=replaced-media&item=20240101-000000&rel=snes/box2d/Compare Me.jpg&side=now")
    assert len(aside.data) == 30 and len(now.data) == 40
    assert client.get("/api/storage/file?area=replaced-media&item=20240101-000000&rel=../../../roms/snes/gamelist.xml&side=aside").status_code == 404

    # A gamelist backup, compared entry by entry with the gamelist now
    snes = root / "roms" / "snes"
    (snes / "gamelist.xml").write_text("<gameList><game><path>./Game Two.sfc</path><name>Game Two</name></game></gameList>")
    (snes / "gamelist_20240102_030405.xml").write_text(
        "<gameList><game><path>./Game Two.sfc</path><name>Game 2</name></game><game><path>./Old.sfc</path><name>Old</name></game></gameList>")
    areas = {a["id"]: a for a in client.get("/api/storage").get_json()["areas"]}
    assert "snes/gamelist_20240102_030405.xml" in {i["id"] for i in areas["gamelist-backups"]["items"]}
    compared = client.get("/api/storage/compare?area=gamelist-backups&item=snes/gamelist_20240102_030405.xml").get_json()
    assert compared["restorable"] and compared["files"][0]["kind"] == "gamelist" and compared["files"][0]["now"]["name"] == "gamelist.xml"
    diff = client.get("/api/storage/diff?area=gamelist-backups&item=snes/gamelist_20240102_030405.xml&rel=").get_json()["gamelist"]
    assert [a["path"] for a in diff["added"]] == ["Old.sfc"] and diff["changed"][0]["fields"][0] == {"field": "name", "now": "Game Two", "then": "Game 2"}
