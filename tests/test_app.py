"""The routes, against the throwaway library in conftest.py."""

import io
import zipfile


def game(system, rom_path):
    return {"system": system, "rom_path": rom_path}


def test_pages_and_health(client):
    assert client.get("/api/health").get_json()["status"] == "healthy"
    for page in ("/", "/console", "/shelf", "/timeline", "/stats", "/import", "/play"):
        assert client.get(page).status_code == 200
    assert client.get("/api/nope").status_code == 404


def test_a_system_without_a_picture_is_given_its_drawn_tile(client):
    # The theme's picture where there is one and it's asked for...
    assert client.get("/imgs/snes.jpg?theme=1").headers["Content-Type"] == "image/jpeg"
    # ...else the tile: by the folder's name, by the system that name is another for, or the plain one
    for folder, word in (("xbox360", "Xbox 360"), ("playstation", "PlayStation"), ("some-new-folder", "Games")):
        tile = client.get(f"/imgs/{folder}.jpg")
        assert tile.status_code == 200 and tile.headers["Content-Type"] == "image/svg+xml" and word in tile.get_data(as_text=True)
    from backend.routes import pages
    # The header's logo and the tab's icon are their own where they're there (the Switch
    # themes' logo isn't in the repository: a copy without it has the stand-in), unless stand-ins are asked for
    own = (pages.FRONTEND_DIR / "themes/switch/retromanager-logo.svg").is_file()
    assert (b"SEGA" in client.get("/themes/switch/retromanager-logo.svg").data) == own
    pages.SYSTEM_TILES = True
    try:
        assert client.get("/imgs/snes.jpg").headers["Content-Type"] == "image/svg+xml"
        logo = client.get("/themes/switch/retromanager-logo.svg")
        assert b"SEGA" not in logo.data and b"make_logo" in logo.data and logo.headers["Content-Type"] == "image/svg+xml"
        assert client.get("/imgs/favicon.png").data == client.get("/icons/icon-512.png").data
    finally:
        pages.SYSTEM_TILES = False


def test_nothing_runs_in_the_background_at_rest(client):
    assert client.get("/api/tasks").get_json() == {"success": True, "tasks": []}


def test_systems_and_games(client):
    names = {s["name"] for s in client.get("/api/systems").get_json()["systems"]}
    assert {"snes", "gba", "psx"} <= names
    games = {g["path"]: g for g in client.get("/api/systems/psx/games").get_json()["games"]}
    # A disc's track file isn't a game of its own
    assert list(games) == ["./Disc Game.cue"]
    assert games["./Disc Game.cue"]["playable"]


def test_scan_finds_the_empty_rom_and_moves_it_aside(client, root):
    result = client.post("/api/systems/snes/scan").get_json()["result"]
    assert [e["path"] for e in result["empty_roms"]] == ["Empty.sfc"]
    moved = client.post("/api/systems/snes/empty-roms/move", json={"paths": ["Empty.sfc", "Game Two.sfc"]}).get_json()
    assert moved["moved"] == ["Empty.sfc"]
    assert not (root / "roms/snes/Empty.sfc").exists() and (root / "data/duplicates/snes/Empty.sfc").exists()
    assert (root / "roms/snes/Game Two.sfc").exists()


def test_status_favourite_and_collections(client, root):
    who = game("snes", "./Game One (USA).sfc")
    assert client.put("/api/play-status", json={**who, "status": "playing"}).get_json()["play_status"] == "playing"
    assert not client.put("/api/play-status", json={**who, "status": "nonsense"}).get_json()["success"]
    assert client.put("/api/play-status", json={**game("snes", "nope.sfc"), "status": "playing"}).status_code == 404
    assert client.put("/api/favorite", json={**who, "favorite": True}).get_json()["favorite"] is True
    assert "<favorite>true</favorite>" in (root / "roms/snes/gamelist.xml").read_text()
    made = client.post("/api/collections", json={"name": "Weekend"}).get_json()["collection"]
    assert not client.post("/api/collections", json={"name": "weekend"}).get_json()["success"]
    added = client.put(f"/api/collections/{made['id']}/games", json={"games": [who, game("gba", "Pocket Game.gba"), game("gba", "nope.gba")], "member": True}).get_json()
    assert added["changed"] == 2
    listed = client.get("/api/collections").get_json()["collections"][0]
    assert [g["system"] for g in listed["games"]] == ["snes", "gba"] or {g["system"] for g in listed["games"]} == {"snes", "gba"}
    entry = next(g for g in client.get("/api/systems/snes/games").get_json()["games"] if g["path"] == "./Game One (USA).sfc")
    assert entry["play_status"] == "playing" and entry["favorite"] and entry["collections"] == [made["id"]]
    assert (root / "data/collections/custom-Weekend.cfg").exists()
    assert client.put(f"/api/collections/{made['id']}", json={"name": "Long weekend"}).get_json()["success"]
    assert (root / "data/collections/custom-Long weekend.cfg").exists() and not (root / "data/collections/custom-Weekend.cfg").exists()


def test_settings_never_return_a_secret(client):
    saved = client.put("/api/settings", json={"values": {"steamgriddb_api_key": "very-secret", "retroachievements_user": "Someone"}}).get_json()
    assert set(saved["changed"]) == {"steamgriddb_api_key", "retroachievements_user"}
    assert "very-secret" not in client.get("/api/settings").get_data(as_text=True)
    sources = {s["id"]: s for s in client.get("/api/scrape-sources").get_json()["sources"]}
    assert sources["steamgriddb"]["available"] and not sources["screenscraper"]["available"]
    assert "Tools > Settings" in client.post("/api/scraper/search", json={"name": "Mario"}).get_json()["error"]
    client.put("/api/settings", json={"values": {"steamgriddb_api_key": "", "retroachievements_user": ""}})


def test_data_backup(client):
    made = client.post("/api/data-backups").get_json()
    assert made["success"] and made["name"].startswith("data-")
    assert client.get("/api/data-backups").get_json()["backups"][0]["name"] == made["name"]


def test_browser_play_serves_roms_discs_and_saves_safely(client, root):
    info = client.get("/api/play/info", query_string={"system": "psx", "rom": "Disc Game.cue"}).get_json()
    assert info["playable"] and info["rom_url"].endswith(".cue.zip") and info["emulatorjs_url"] == "/emulatorjs/"
    disc = zipfile.ZipFile(io.BytesIO(client.get(info["rom_url"]).data))
    assert set(disc.namelist()) == {"Disc Game.cue", "Disc Game (Track 1).bin"}
    assert client.get("/api/rom/gba/Pocket Game.gba").data == b"\x03" * 4096
    assert client.get("/api/rom/gba/../snes/gamelist.xml").status_code == 404
    assert not client.get("/api/play/info", query_string={"system": "snes", "rom": "nope.sfc"}).get_json()["playable"]

    who = {"system": "snes", "rom": "Game Two.sfc", "profile": "guest"}
    assert client.get("/api/play/save", query_string=who).status_code == 404
    assert client.put("/api/play/save", query_string={**who, "session": "a"}, data=b"first save").get_json()["backup"] is None
    replaced = client.put("/api/play/save", query_string={**who, "session": "a"}, data=b"second save").get_json()
    assert replaced["backup"].startswith("browser-play/") and (root / "save-backups" / replaced["backup"]).read_bytes() == b"first save"
    # Once per play session, and never with an empty save
    assert client.put("/api/play/save", query_string={**who, "session": "a"}, data=b"third save").get_json()["backup"] is None
    assert client.put("/api/play/save", query_string={**who, "session": "a"}, data=b"\x00" * 64).status_code == 409
    assert client.get("/api/play/save", query_string=who).data == b"third save"
    assert client.put("/api/play/save", query_string={**who, "profile": "stranger"}, data=b"x").status_code == 404

    assert client.put("/api/play/state", query_string=who, data=b"state").get_json()["success"]
    assert client.get("/api/play/state", query_string=who).data == b"state"
    assert (root / "savestates/guest/snes/Browser/Game Two.state").exists()


def test_phone_play_lists_a_games_files_and_serves_them(client, root):
    info = client.get("/api/phone/info", query_string={"system": "psx", "rom": "./Disc Game.cue"}).get_json()
    assert info["playable"] and info["cores"][0] == "pcsx_rearmed" and info["save"] == "Disc Game.srm"
    assert info["players"][0] == {"id": "retroarch:pcsx_rearmed", "kind": "core", "core": "pcsx_rearmed", "name": "RetroArch: pcsx_rearmed", "folder": "PCSX-ReARMed"}
    from backend.systems import phone_players
    assert phone_players("Nintendo 3DS")[0]["package"] == "org.azahar_emu.azahar" and phone_players("nope") == []
    assert {f["path"]: f["size"] for f in info["files"]} == {"Disc Game.cue": (root / "roms/psx/Disc Game.cue").stat().st_size, "Disc Game (Track 1).bin": 2048}
    assert "guest" in info["profiles"]
    assert not client.get("/api/phone/info", query_string={"system": "snes", "rom": "nope.sfc"}).get_json()["playable"]
    assert client.get("/api/phone/rom/psx/Disc Game (Track 1).bin").data == b"\x04" * 2048
    part = client.get("/api/phone/rom/gba/Pocket Game.gba", headers={"Range": "bytes=4000-"})
    assert part.status_code == 206 and len(part.data) == 96
    assert client.get("/api/phone/rom/gba/../snes/gamelist.xml").status_code == 404
    assert client.get("/api/phone/rom/gba/nope.gba").status_code == 404
    assert "snes" in {s["name"] for s in client.get("/api/phone/cores").get_json()["systems"]}
    # A BIOS file, and a game started on the phone counting as played
    (root / "bios/scph5501.bin").write_bytes(b"\x07" * 512)
    assert client.get("/api/phone/info", query_string={"system": "psx", "rom": "Disc Game.cue"}).get_json()["bios"] == [{"name": "scph5501.bin", "size": 512}]
    assert client.get("/api/phone/bios/psx/scph5501.bin").data == b"\x07" * 512
    assert client.get("/api/phone/bios/psx/nope.bin").status_code == 404
    (root / "bios/scph5501.bin").unlink()
    assert client.post("/api/phone/played", json={"system": "psx", "rom": "./Disc Game.cue"}).get_json()["success"]
    assert client.post("/api/phone/played", json={"system": "psx", "rom": "nope.cue"}).status_code == 404
    from backend.routes.phone import played_on_phones
    assert "psx/Disc Game.cue" in played_on_phones(None)
    assert all(g["phone_playable"] for g in client.get("/api/systems/gba/games").get_json()["games"] if g["rom_exists"])


def test_phone_save_states_go_both_ways(client, root):
    who = {"system": "snes", "rom": "Game Two.sfc", "profile": "guest"}
    assert client.get("/api/play/phone-states", query_string=who).get_json()["states"] == []
    state = b"#!s9xsnp:0011\n" + b"\x05" * 64
    sent = client.put("/api/play/phone-state", query_string={**who, "name": "Game Two.state1", "modified": "1700000000"}, data=state).get_json()
    assert sent["success"] and sent["backup"] is None
    listed = client.get("/api/play/phone-states", query_string={**who, "core": "snes9x"}).get_json()["states"]
    assert [(s["name"], s["modified"], s["sha1"], s["made_by"], s["fits"]) for s in listed] == [("Game Two.state1", 1700000000, sent["sha1"], "Snes9x", True)]
    assert client.get("/api/play/phone-states", query_string={**who, "core": "bsnes"}).get_json()["states"][0]["fits"] is False
    assert client.get("/api/play/phone-state", query_string={**who, "name": "Game Two.state1"}).data == state
    again = client.put("/api/play/phone-state", query_string={**who, "name": "Game Two.state1"}, data=state + b"!").get_json()
    assert again["backup"].startswith("phone-play/") and (root / "save-backups" / again["backup"]).read_bytes() == state
    assert client.put("/api/play/phone-state", query_string={**who, "name": "Game Two.state.auto"}, data=state).get_json()["success"]
    for name in ("Other Game.state", "Game Two.srm", "Game Two.state/../x", "Game Two.state.png"):
        assert client.put("/api/play/phone-state", query_string={**who, "name": name}, data=state).status_code == 400
    assert client.put("/api/play/phone-state", query_string={**who, "profile": "stranger", "name": "Game Two.state"}, data=state).status_code == 404


def test_a_scrape_replaces_a_picture_only_when_asked_and_keeps_the_old_one(client, root, monkeypatch):
    from backend.routes import scraping
    # (the media folder a system's pictures are in needn't have the ROM folder's name)
    media_system = scraping.scanner.media_index("snes").media_system
    old = root / "media" / media_system / "box2d/Game Two.png"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"old picture")
    scraping._invalidate_caches()
    monkeypatch.setattr(scraping.jeu_cache, "get", lambda game_id: {"rom": {}})
    monkeypatch.setattr(scraping.scraper, "extract_game_data", lambda jeu: {"name": "Game Two", "media": {"box2d": "http://example.invalid/box.png"}})
    monkeypatch.setattr(scraping.settings, "get", lambda key: "off" if key == "libretro_thumbnails" else None)

    def download(url, target_dir, stem):
        (target_dir / f"{stem}.png").write_bytes(b"new picture")
    monkeypatch.setattr(scraping, "_download_one", download)

    kept = scraping.apply_scrape("snes", "Game Two.sfc", "1", ["box2d"])
    assert kept["success"] and kept["already_had"] == ["box2d"] and kept["replaced"] == [] and old.read_bytes() == b"old picture"
    scraping._invalidate_caches()
    swapped = scraping.apply_scrape("snes", "Game Two.sfc", "1", ["box2d"], replace=True)
    assert swapped["replaced"] == ["box2d"] and old.read_bytes() == b"new picture"
    assert (root / "data" / swapped["kept"] / media_system / "box2d/Game Two.png").read_bytes() == b"old picture"
    old.unlink()
    scraping._invalidate_caches()


def test_emulator_files_cannot_escape_their_folder(client):
    assert client.get("/emulatorjs/../settings.json").status_code == 404
    assert client.get("/emulatorjs/.hidden").status_code == 404


def test_rom_check_report_and_fixes(client, root):
    from backend.routes import romindex
    # Two files with the same contents, and one the databases would call something else
    (root / "roms/gba/Pocket Game copy.gba").write_bytes(b"\x03" * 4096)
    for found in romindex._library_roms():
        romindex.rom_index.check_one(found)
    for key, record in romindex.rom_index.records().items():
        if key == "snes/Game Two.sfc":
            record["known_name"] = "Second Game, The"
    report = client.get("/api/rom-index").get_json()["report"]
    assert report["counts"]["unknown"] >= 3
    assert [[g["rom_path"] for g in group] for group in report["duplicates"]] == [["Pocket Game copy.gba", "Pocket Game.gba"]]
    assert [m["rom_path"] for m in report["mislabelled"]] == ["Game Two.sfc"]

    client.put("/api/play-status", json={**game("gba", "Pocket Game copy.gba"), "status": "finished"})
    resolved = client.post("/api/rom-index/duplicates/resolve", json={"keep": game("gba", "Pocket Game.gba"), "remove": [game("gba", "Pocket Game copy.gba"), game("snes", "Game Two.sfc")]}).get_json()
    assert resolved["moved"] == ["gba/Pocket Game copy.gba"] and len(resolved["errors"]) == 1
    assert (root / "data/duplicates/gba/Pocket Game copy.gba").exists() and (root / "roms/snes/Game Two.sfc").exists()
    assert client.get("/api/library-state").get_json()["status"].get("gba/Pocket Game.gba") == "finished"

    client.put("/api/play-status", json={**game("snes", "Game Two.sfc"), "status": "backlog"})
    (root / "saves/guest/snes/Game Two.srm").write_bytes(b"third save")
    renamed = client.post("/api/rom-index/rename", json={"items": [game("snes", "Game Two.sfc")]}).get_json()
    assert renamed["results"][0]["new_rom_path"] == "Second Game, The.sfc"
    assert (root / "roms/snes/Second Game, The.sfc").exists() and (root / "saves/guest/snes/Second Game, The.srm").exists()
    assert client.get("/api/library-state").get_json()["status"].get("snes/Second Game, The.sfc") == "backlog"
    assert romindex.rom_index.get("snes", "Second Game, The.sfc") and not romindex.rom_index.get("snes", "Game Two.sfc")


def test_saves_are_shared_until_a_person_takes_them(client, root):
    # With nobody chosen, a game is played with the saves that are nobody's in particular
    who = {"system": "snes", "rom": "Game One (USA).sfc", "profile": "shared"}
    info = client.get("/api/play/info", query_string=who).get_json()
    assert info["profiles"][0]["name"] == "shared" and info["profiles"][0]["has_save"] is False
    assert client.put("/api/play/save", query_string=who, data=b"shared save").get_json()["success"]
    assert (root / "saves/snes/Game One (USA).srm").read_bytes() == b"shared save"
    assert client.get("/api/play/save", query_string=who).data == b"shared save"
    # ...and its states: the phone's are RetroArch's own, kept beside each other
    assert client.put("/api/play/phone-state", query_string={**who, "name": "Game One (USA).state"}, data=b"#!s9xsnp:0011\n....").get_json()["success"]
    assert (root / "savestates/snes/Game One (USA).state").is_file()
    assert [s["name"] for s in client.get("/api/play/phone-states", query_string=who).get_json()["states"]] == ["Game One (USA).state"]
    phone = client.get("/api/phone/info", query_string={"system": "snes", "rom": "Game One (USA).sfc"}).get_json()
    assert phone["shared_saves"] is True and phone["save"] == "Game One (USA).srm"

    counted = client.get("/api/accounts/shared-saves").get_json()
    assert counted["saves"] >= 1 and counted["states"] >= 1
    # "shared" can't be a person; a new person may leave the shared saves alone, or take them
    assert client.post("/api/accounts/people", json={"name": "shared"}).status_code == 400
    assert client.post("/api/accounts/people", json={"name": "keeper"}).get_json()["moved"] == 0
    assert (root / "saves/snes/Game One (USA).srm").is_file() and (root / "saves/keeper").is_dir()
    taken = client.post("/api/accounts/people", json={"name": "taker", "take_shared": True}).get_json()
    assert taken["moved"] >= 2 and "taker" in {p["name"] for p in taken["profiles"]}
    assert (root / "saves/taker/snes/Game One (USA).srm").read_bytes() == b"shared save"
    assert (root / "savestates/taker/snes/Game One (USA).state").is_file() and not (root / "saves/snes/Game One (USA).srm").exists()
    assert client.get("/api/accounts/shared-saves").get_json() == {"success": True, "saves": 0, "states": 0, "beside_roms": False}
    assert list((root / "data/moved-saves").glob("*-taker.json"))
    assert client.get("/api/play/save", query_string={**who, "profile": "taker"}).data == b"shared save"


def test_a_phones_retroarch_setup_is_kept_for_another(client, root):
    assert client.get("/api/phone/setup").get_json()["saved"] is False
    for path, body in (("config/mGBA/mGBA.cfg", b'input_overlay = "x"'), ("overlays/mine/gba.cfg", b"overlays = 1"), ("overlays/mine/A.png", b"png")):
        assert client.put("/api/phone/setup/file", query_string={"path": path}, data=body).get_json()["success"]
    # Only RetroArch's own folders, and nothing outside them
    for path in ("roms/snes/x.sfc", "config/../settings.json", "config", "/etc/passwd"):
        assert client.put("/api/phone/setup/file", query_string={"path": path}, data=b"x").status_code == 400
    saved = client.post("/api/phone/setup", json={"device": "Phone A", "base": "/storage/emulated/0/RetroArch", "package": "com.retroarch",
                                                  "files": ["config/mGBA/mGBA.cfg", "overlays/mine/gba.cfg", "roms/x"]}).get_json()
    assert saved["device"] == "Phone A" and [f["path"] for f in saved["files"]] == ["config/mGBA/mGBA.cfg", "overlays/mine/gba.cfg"]
    # (a file that was sent but isn't in the list isn't part of it)
    assert client.get("/api/phone/setup/file", query_string={"path": "overlays/mine/A.png"}).status_code == 404
    assert client.get("/api/phone/setup/file", query_string={"path": "config/mGBA/mGBA.cfg"}).data == b'input_overlay = "x"'
    assert client.get("/api/phone/setup").get_json()["base"] == "/storage/emulated/0/RetroArch"
    from backend.systems import phone_players
    assert next(p for p in phone_players("psx") if p["id"] == "retroarch:mednafen_psx")["folder"] == "Beetle PSX"


def test_a_save_never_written_to_is_marked_empty(client, root):
    def empty():
        saves = client.get("/api/systems/snes/saves?rom=./Game Two.sfc").get_json()["saves"]
        return [s["empty"] for s in saves if s["path"] == "family/snes/Game Two.srm"]
    (root / "saves/family/snes").mkdir(parents=True, exist_ok=True)
    (root / "saves/family/snes/Game Two.srm").write_bytes(b"\xff" * 2048)
    assert empty() == [True]
    (root / "saves/family/snes/Game Two.srm").write_bytes(b"\xff" * 2047 + b"a")
    assert empty() == [False]
    (root / "saves/family/snes/Game Two.srm").unlink()


def test_pictures_nothing_else_has_come_from_thegamesdb_then_steamgriddb(client, root, monkeypatch):
    from backend.routes import scraping
    media_system = scraping.scanner.media_index("snes").media_system
    monkeypatch.setattr(scraping.jeu_cache, "get", lambda game_id: {"rom": {}})
    monkeypatch.setattr(scraping.scraper, "extract_game_data", lambda jeu: {"name": "Game One", "media": {}})
    monkeypatch.setattr(scraping.settings, "get", lambda key: "off" if key == "libretro_thumbnails" else None)
    monkeypatch.setattr(scraping, "_hasheous_lookup", lambda system, rom: None)
    monkeypatch.setattr(scraping, "_resting", {})
    fetched = {}

    def download(url, target_dir, stem):
        fetched[target_dir.name] = url
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"{stem}.png").write_bytes(b"picture")
    monkeypatch.setattr(scraping, "_download_one", download)

    tgdb, grid = scraping.thegamesdb_scraper, scraping.steamgriddb_scraper
    monkeypatch.setattr(tgdb, "api_key", "key")
    monkeypatch.setattr(grid, "api_key", "key")
    # A game of another title is never used; the one of the same title is
    monkeypatch.setattr(tgdb, "search_game", lambda name, system=None: [{"id": 1, "game_title": "Game One Turbo"}, {"id": 2, "game_title": "Game One"}])
    monkeypatch.setattr(tgdb, "get_images", lambda game_id: {"boxart": [f"http://tgdb.invalid/{game_id}/box.png"]})
    monkeypatch.setattr(grid, "search_game", lambda name: [{"id": 9, "name": "Game One!"}])
    monkeypatch.setattr(grid, "get_game_info", lambda game_id: {"name": "Game One", "grids": ["http://grid.invalid/grid.png"], "heroes": ["http://grid.invalid/hero.png"], "logos": []})

    done = scraping.apply_scrape("snes", "Game One (USA).sfc", "1", ["box2d", "fanart", "wheel"])
    assert done["success"] and done["downloaded"] == ["box2d", "fanart"], done
    assert done["from_thegamesdb"] == ["box2d"] and done["from_steamgriddb"] == ["fanart"]

    assert fetched == {"box2d": "http://tgdb.invalid/2/box.png", "fanart": "http://grid.invalid/hero.png"}
    # A cartridge comes from LaunchBox's list when it's in use (GameTDB has nothing for this system)
    monkeypatch.setattr(scraping.launchbox_index, "pictures", lambda system, names: {"support": "http://launchbox.invalid/cart.png", "box2d": "http://launchbox.invalid/box.png"})
    cart = scraping.apply_scrape("snes", "Game One (USA).sfc", "1", ["support", "box2d"])
    assert cart["downloaded"] == ["support"] and cart["from_launchbox"] == ["support"] and cart["from_gametdb"] == []
    (root / "media" / media_system / "support" / "Game One (USA).png").unlink()

    # One that can't be asked is left alone for a while, not asked for every game
    def fails(name, system=None):
        raise scraping.TheGamesDBError("allowance used up")
    monkeypatch.setattr(tgdb, "search_game", fails)
    assert scraping._thegamesdb_pictures("snes", ["Game One"]) == {} and scraping._resting_source("TheGamesDB")
    for folder in ("box2d", "fanart"):
        (root / "media" / media_system / folder / "Game One (USA).png").unlink()
    scraping._invalidate_caches()


def test_a_system_has_its_drawn_tile_unless_the_themes_picture_is_chosen(client):
    from backend.routes import pages
    have = (pages.FRONTEND_DIR / "imgs" / "snes.jpg").is_file()
    theirs = "image/jpeg" if have else "image/svg+xml"
    assert client.get("/imgs/snes.jpg").mimetype == "image/svg+xml" and client.get("/imgs/snes.jpg?drawn=1").mimetype == "image/svg+xml"
    assert client.get("/imgs/snes.jpg?theme=1").mimetype == theirs
    about = client.get("/api/system-pictures").get_json()
    assert about["default"] == "drawn" and about["theme"] == have and "CC BY-NC-SA" in about["credit"]
    # The setting makes the theme's the ones shown; a browser can still ask for the tiles
    client.put("/api/settings", json={"values": {"system_pictures": "theme"}})
    assert client.get("/imgs/snes.jpg").mimetype == theirs and client.get("/imgs/snes.jpg?drawn=1").mimetype == "image/svg+xml"
    assert client.get("/api/system-pictures").get_json()["default"] == ("theme" if have else "drawn")
    assert client.get("/imgs/nosuchsystem.jpg").mimetype == "image/svg+xml"
    client.put("/api/settings", json={"values": {"system_pictures": "drawn"}})


def test_a_new_copy_is_taken_through_its_first_steps_once(client, root, monkeypatch):
    from backend.routes import setup
    # Not this one: it has profiles (and a library) already
    assert client.get("/api/setup").get_json()["needed"] is False and client.get("/").status_code == 200
    state = client.get("/api/setup").get_json()
    assert {f["key"]: (f["exists"], f["writable"]) for f in state["folders"]}["roms"] == (True, True) and state["library"]["systems"] >= 1
    assert client.get("/setup").status_code == 200
    # A new one: the pages lead to the steps until they've been gone through
    monkeypatch.setattr(setup, "SAVE_PROFILES", [])
    monkeypatch.setattr(setup, "DONE", root / "data" / "setup-test.json")
    assert client.get("/api/setup").get_json()["needed"] is True
    for page in ("/", "/console"):
        answer = client.get(page)
        assert answer.status_code == 302 and answer.headers["Location"].endswith("/setup")
    assert client.post("/api/setup/done").get_json()["success"]
    assert client.get("/api/setup").get_json()["needed"] is False and client.get("/").status_code == 200
    (root / "data" / "setup-test.json").unlink()


def test_saves_can_be_kept_beside_the_games_and_are_then_everyones(client, root):
    game = {"system": "snes", "rom": "Game One (USA).sfc"}
    beside = root / "roms/snes/Game One (USA).srm"
    beside.write_bytes(b"save beside the game")
    try:
        # Kept in folders (the usual): one beside a game is a stray, and isn't anyone's save
        assert client.get("/api/play/save", query_string={**game, "profile": "shared"}).status_code == 404
        assert client.put("/api/settings", json={"values": {"save_location": "roms"}}).get_json()["success"]

        found = client.get("/api/systems/snes/saves?rom=./Game One (USA).sfc").get_json()["saves"]
        assert [(s["root"], s["profile"], s["path"]) for s in found if s["kind"] == "save" and s["root"] == "roms"] == [("roms", "shared", "snes/Game One (USA).srm")]
        # Whoever asks gets everyone's: there are no people's own saves this way
        for who in ("shared", "family", "guest"):
            got = client.get("/api/play/save", query_string={**game, "profile": who})
            assert got.status_code == 200 and got.data == b"save beside the game"
        put = client.put("/api/play/save", query_string={**game, "profile": "family", "session": "s1"}, data=b"a newer save")
        assert put.get_json()["success"] and beside.read_bytes() == b"a newer save"
        assert put.get_json()["backup"].endswith("roms/snes/Game One (USA).srm")
        assert not (root / "saves/family/snes/Game One (USA).srm").exists()

        # RetroArch's states from a phone go beside the game too, and are listed back from there
        state = b"#RZIPv\x01#" + b"\x00" * 64
        sent = client.put("/api/play/phone-state", query_string={**game, "profile": "guest", "name": "Game One (USA).state.auto"}, data=state)
        assert sent.get_json()["success"] and (root / "roms/snes/Game One (USA).state.auto").read_bytes() == state
        listed = client.get("/api/play/phone-states", query_string={**game, "profile": "family"}).get_json()["states"]
        assert [s["name"] for s in listed] == ["Game One (USA).state.auto"]

        # Nothing offers to move them out of the ROM folder, or to hand them to a person
        assert client.post("/api/systems/snes/saves-in-roms/move", json={}).status_code == 400
        assert client.get("/api/accounts/shared-saves").get_json()["beside_roms"] is True
        assert client.get("/api/setup").get_json()["saves"]["beside_roms"] >= 2
    finally:
        client.put("/api/settings", json={"values": {"save_location": "folders"}})
        for leftover in root.glob("roms/snes/Game One (USA).s*"):
            if leftover.suffix != ".sfc":
                leftover.unlink()
    assert client.get("/api/accounts/shared-saves").get_json()["beside_roms"] is False


def test_the_consoles_collections_follow_a_change_at_once(client):
    import time
    made = client.post("/api/collections", json={"name": "Console test"}).get_json()["collection"]
    game = {"system": "snes", "rom_path": "Game One (USA).sfc"}
    assert client.put(f"/api/collections/{made['id']}/games", json={**game, "member": True}).get_json()["success"]

    def lists():
        for _ in range(100):
            home = client.get("/api/console/home").get_json()
            if not home["pending"]:
                return {entry["id"]: [g["path"] for g in entry["games"]] for entry in home["lists"]}
            time.sleep(0.05)
        raise AssertionError("the Console's lists never came")
    assert lists()[made["id"]] == ["./Game One (USA).sfc"]
    # Taken out: gone from the list straight away, not when the rest is next worked out
    assert made["id"] not in client.put(f"/api/collections/{made['id']}/games", json={**game, "member": False}).get_json()["collections"]
    assert made["id"] not in lists()
    client.delete(f"/api/collections/{made['id']}")


def test_save_states_beyond_the_newest_few_move_to_the_backups(client, root):
    import os, time
    folder = root / "savestates/guest/snes"
    folder.mkdir(parents=True, exist_ok=True)
    now = time.time()
    names = [f"Thin Test.state{n}" for n in range(1, 8)] + ["Thin Test.state.auto"]
    for age, name in enumerate(names):
        (folder / name).write_bytes(b"state")
        os.utime(folder / name, (now - 1000 + age * 10, now - 1000 + age * 10))   # the auto state is the newest
    (folder / "Thin Test.state1.png").write_bytes(b"picture")
    (folder.parent.parent / "family/snes").mkdir(parents=True, exist_ok=True)
    (folder.parent.parent / "family/snes/Thin Test.state1").write_bytes(b"someone else's")
    try:
        plan = client.get("/api/save-states/thin?keep=3").get_json()
        mine = [g for g in plan["groups"] if g["profile"] == "guest" and g["game"] == "Thin Test"]
        # The three newest stay (auto, 7, 6); the four oldest go. Family's one state is theirs, and alone
        assert len(mine) == 1 and mine[0]["total"] == 8
        assert [r["path"] for r in mine[0]["move"]] == [f"guest/snes/Thin Test.state{n}" for n in (5, 4, 3, 2, 1)]
        assert not [g for g in plan["groups"] if g["profile"] == "family"]
        done = client.post("/api/save-states/thin", json={"keep": 3}).get_json()
        assert done["success"] and done["moved"] >= 5
        kept = sorted(p.name for p in folder.glob("Thin Test.*"))
        assert kept == ["Thin Test.state.auto", "Thin Test.state6", "Thin Test.state7"]
        backup = root / "save-backups" / done["backup"] / "savestates/guest/snes"
        assert (backup / "Thin Test.state1").is_file() and (backup / "Thin Test.state1.png").is_file()
    finally:
        for p in list(folder.glob("Thin Test.state*")) + [folder.parent.parent / "family/snes/Thin Test.state1"]:
            p.unlink(missing_ok=True)


def test_save_states_can_be_numbered_again_oldest_first(client, root):
    import os, time
    folder = root / "savestates/guest/snes"
    folder.mkdir(parents=True, exist_ok=True)
    now = time.time()
    # Slots 40, 7, 0 and 12, oldest to newest; 1 already is the newest one's... no: 12 is newest
    for age, slot in enumerate([40, 7, None, 12]):
        name = f"Renumber Test.state{slot if slot is not None else ''}"
        (folder / name).write_bytes(f"from slot {slot}".encode())
        os.utime(folder / name, (now - 100 + age, now - 100 + age))
    (folder / "Renumber Test.state40.png").write_bytes(b"picture of 40")
    (folder / "Renumber Test.state.auto").write_bytes(b"auto")
    try:
        assert client.get("/api/save-states/renumber").get_json()["states"] >= 4
        done = client.post("/api/save-states/renumber").get_json()
        assert done["success"]
        got = {p.name: p.read_bytes() for p in folder.glob("Renumber Test.*")}
        assert got == {"Renumber Test.state1": b"from slot 40", "Renumber Test.state1.png": b"picture of 40",
                       "Renumber Test.state2": b"from slot 7", "Renumber Test.state3": b"from slot None",
                       "Renumber Test.state4": b"from slot 12", "Renumber Test.state.auto": b"auto"}
        assert not list(folder.glob(".renumbering-*"))
    finally:
        for p in folder.glob("Renumber Test.*"):
            p.unlink()
