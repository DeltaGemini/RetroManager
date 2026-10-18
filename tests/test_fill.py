"""Fill the gaps: looking a game up on the sources, choosing, and remembering the matches.
The sources are stood in for here, and so is downloading: nothing goes out."""


from backend.thegamesdb import TheGamesDBError


def _sources(monkeypatch, searched, info):
    from backend.routes import fill, sources
    monkeypatch.setitem(sources._OTHER_SOURCES, 'thegamesdb', ('TheGamesDB', (TheGamesDBError,), lambda data, name: searched(name), lambda data: info(data)))
    monkeypatch.setattr(fill, 'available_sources', lambda: [{'id': 'thegamesdb', 'available': True}, {'id': 'screenscraper', 'available': False}])


def test_a_game_is_looked_up_filled_and_its_match_remembered(client, root, monkeypatch):
    from backend.routes import fill
    rom = "Gap Filler (USA).sfc"
    (root / "roms" / "snes" / rom).write_bytes(b"\x09" * 4096)
    asked = []

    def searched(name):
        asked.append(name)
        return [{'id': 41, 'name': 'Gap Filler', 'cover_url': None, 'platform_names': 'SNES', 'year': '1994', 'is_hack': False, 'hash_match': False}]

    _sources(monkeypatch, searched, lambda data: {'desc': 'Fills gaps.', 'developer': 'Holes Ltd', 'media': {'box2d_1': 'http://example.invalid/box.png', 'logo_1': 'http://example.invalid/logo.png'}})

    looked = client.post("/api/fill/look", json={"system_name": "snes", "rom_path": rom, "sources": ["thegamesdb", "screenscraper"]}).get_json()
    assert list(looked["sources"]) == ["thegamesdb"]                      # one that isn't set up isn't asked
    tgdb = looked["sources"]["thegamesdb"]
    assert tgdb["match"]["confidence"] == "likely" and tgdb["match"]["id"] == "thegamesdb:41"
    assert tgdb["candidates"]["media"] == {'box2d': 'http://example.invalid/box.png', 'wheel': 'http://example.invalid/logo.png'}
    assert tgdb["candidates"]["fields"]["desc"] == "Fills gaps."

    saved = []
    def download(url, folder, stem, source=None):
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{stem}.png"
        target.write_bytes(b"\x89PNG fake")
        saved.append((url, folder.name))
        return target
    monkeypatch.setattr(fill, '_download_one', download)
    applied = client.post("/api/fill/apply", json={"system_name": "snes", "rom_path": rom,
                                                  "pictures": {"box2d": "http://example.invalid/box.png", "mix": "file:///etc/passwd"},
                                                  "fields": {"desc": "Fills gaps.", "lastplayed": "Not this"},
                                                  "remember": {"thegamesdb": tgdb["match"]}}).get_json()
    assert applied["success"] and applied["downloaded"] == ["box2d"] and applied["filled"] == ["desc"]
    assert any("mix" in e for e in applied["errors"])                      # only web addresses are fetched
    assert saved == [("http://example.invalid/box.png", "box2d")]
    gamelist = (root / "roms" / "snes" / "gamelist.xml").read_text()
    assert "Fills gaps." in gamelist and "Not this" not in gamelist          # only the fields it fills

    # Next time: remembered, so not searched again
    assert client.get("/api/fill/remembered?system=snes").get_json()["games"][rom] == ["thegamesdb"]
    again = client.post("/api/fill/look", json={"system_name": "snes", "rom_path": rom, "sources": ["thegamesdb"]}).get_json()
    assert asked == ["Gap Filler"] and again["sources"]["thegamesdb"]["match"]["remembered"]

    # A remembered match follows its game when it's renamed
    from backend.core import game_moved
    game_moved("snes", rom, "Gap Filler (Europe).sfc")
    assert "Gap Filler (Europe).sfc" in client.get("/api/fill/remembered?system=snes").get_json()["games"]


def test_an_unsure_match_isnt_remembered_but_one_chosen_by_hand_is(client, root, monkeypatch):
    rom = "Maybe Game.sfc"
    (root / "roms" / "snes" / rom).write_bytes(b"\x0a" * 4096)
    _sources(monkeypatch, lambda name: [{'id': 5, 'name': 'Maybe Gamer Deluxe', 'cover_url': None, 'platform_names': 'SNES', 'year': None, 'is_hack': False, 'hash_match': False},
                                         {'id': 6, 'name': 'Maybe Game', 'cover_url': None, 'platform_names': 'SNES', 'year': None, 'is_hack': False, 'hash_match': False}],
             lambda data: {'media': {}})
    unsure = {'id': 'thegamesdb:5', 'name': 'Maybe Gamer Deluxe', 'confidence': 'unsure'}
    client.post("/api/fill/apply", json={"system_name": "snes", "rom_path": rom, "remember": {"thegamesdb": unsure}})
    assert rom not in client.get("/api/fill/remembered?system=snes").get_json()["games"]
    chosen = client.post("/api/fill/look", json={"system_name": "snes", "rom_path": rom, "sources": ["thegamesdb"],
                                                "rematch": {"source": "thegamesdb", "id": "thegamesdb:5"}}).get_json()["sources"]["thegamesdb"]["match"]
    assert chosen["confidence"] == "chosen" and chosen["id"] == "thegamesdb:5"
    client.post("/api/fill/apply", json={"system_name": "snes", "rom_path": rom, "remember": {"thegamesdb": chosen}})
    assert client.get("/api/fill/remembered?system=snes").get_json()["games"][rom] == ["thegamesdb"]


def test_the_background_scrape_finds_but_applies_nothing(client, root, monkeypatch):
    import time
    from backend.core import _invalidate_caches
    (root / "roms" / "gba" / "Found Later.gba").write_bytes(b"\x0d" * 2048)
    _invalidate_caches()
    gamelist = (root / "roms" / "gba" / "gamelist.xml")
    before = gamelist.read_text() if gamelist.exists() else ''
    _sources(monkeypatch, lambda name: [{'id': 77, 'name': 'Found Later', 'cover_url': None, 'platform_names': 'GBA', 'year': '2002',
                                         'is_hack': False, 'hash_match': False}] if name == 'Found Later' else [],
             lambda data: {'desc': 'Found in the background.'})

    started = client.post("/api/fill/background/start", json={"systems": ["gba"], "kinds": ["desc"], "sources": ["thegamesdb"], "recheck": True}).get_json()
    assert started["success"] and started["total"] >= 1
    for _ in range(100):
        status = client.get("/api/fill/background").get_json()
        if not status["running"]:
            break
        time.sleep(0.05)
    games = {g["rom"]: g for s in status["systems"] if s["system"] == "gba" for g in s["games"]}
    assert games["Found Later.gba"]["offered"] == ["desc"]
    assert (gamelist.read_text() if gamelist.exists() else '') == before          # nothing applied
    kept = client.get("/api/fill/found?system=gba&rom=Found%20Later.gba").get_json()
    assert kept["sources"]["thegamesdb"]["candidates"]["fields"]["desc"] == "Found in the background."

    # Applied in Fill the gaps: no longer listed
    client.post("/api/fill/apply", json={"system_name": "gba", "rom_path": "Found Later.gba", "fields": {"desc": "Found in the background."}})
    status = client.get("/api/fill/background").get_json()
    assert "Found Later.gba" not in {g["rom"] for s in status["systems"] for g in s["games"]}
    assert "Found in the background." in gamelist.read_text()

    # A second run skips what was looked up lately, unless asked to look again
    again = client.post("/api/fill/background/start", json={"systems": ["gba"], "kinds": ["desc"], "sources": ["thegamesdb"]}).get_json()
    assert again["skipped_recent"] >= 1
    for _ in range(100):
        if not client.get("/api/fill/background").get_json()["running"]:
            break
        time.sleep(0.05)


def _picked(fields=None, media=None):
    return {'fields': fields or {}, 'media': media or {}}


def test_a_game_being_added_is_filled_from_the_pick_then_the_order(client, root, monkeypatch):
    """The game picked when adding it, then the other sources in Fill the gaps' order for what it hasn't:
    a confident match only, another source's copy of a picture tried when one won't download."""
    from backend.core import _invalidate_caches, scanner
    from backend.routes import fill
    rom = "Added Later (USA).sfc"
    (root / "roms" / "snes" / rom).write_bytes(b"\x0e" * 4096)
    _invalidate_caches()
    monkeypatch.setattr(fill, "_candidates", lambda source, match_id, system: _picked(
        {'name': 'Added Later', 'desc': 'From the pick.'}, {'box2d': 'http://pick.invalid/box.png'}))
    monkeypatch.setattr(fill, "look_game", lambda system, rom_path, sources: {
        'thegamesdb': {'match': {'confidence': 'likely', 'id': 'thegamesdb:5', 'name': 'Added Later'},
                       'candidates': _picked({'developer': 'TGDB Dev', 'desc': 'Not used: the pick has one'}, {'box2d': 'http://tgdb.invalid/box.png', 'fanart': 'http://tgdb.invalid/fan.png'})},
        'steamgriddb': {'match': {'confidence': 'unsure', 'id': 'steamgriddb:9'},
                        'candidates': _picked({'publisher': 'Never'}, {'wheel': 'http://grid.invalid/logo.png'})},
    })
    fetched = []

    def download(url, target_dir, stem):
        fetched.append(url)
        if 'pick.invalid' in url:
            raise ValueError("the source returned HTTP 404")       # the pick's box won't download...
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"{stem}.png").write_bytes(b"picture")
    monkeypatch.setattr(fill, "_download_one", download)

    done, status = fill.fill_from_match("snes", rom, "123", ["box2d", "fanart", "wheel"])
    assert status == 200 and done["success"], done
    assert sorted(done["downloaded"]) == ["box2d", "fanart"]                       # ...so TheGamesDB's is used
    assert fetched == ["http://pick.invalid/box.png", "http://tgdb.invalid/box.png", "http://tgdb.invalid/fan.png"]
    game = scanner.get_game_details("snes", rom)
    assert game.desc == "From the pick." and game.developer == "TGDB Dev" and not game.publisher   # an unsure match isn't used
    remembered = client.get("/api/fill/remembered?system=snes").get_json()["games"][rom]
    assert remembered == ["screenscraper", "thegamesdb"]


def test_a_name_typed_when_adding_is_kept_and_a_picture_it_has_is_left(client, root, monkeypatch):
    from backend.core import _invalidate_caches, gamelist_mgr, ROMS_BASE, scanner
    from backend.models import Game
    from backend.routes import fill
    rom = "Typed Name.sfc"
    (root / "roms" / "snes" / rom).write_bytes(b"\x0f" * 4096)
    gamelist_mgr.add_entries("snes", ROMS_BASE, [Game(path=f"./{rom}", name="My Own Name")])
    folder = root / "media" / scanner.media_index("snes").media_system / "box2d"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Typed Name.png").write_bytes(b"mine")
    _invalidate_caches()
    monkeypatch.setattr(fill, "_candidates", lambda source, match_id, system: _picked(
        {'name': 'Their Name', 'desc': 'Theirs.', 'developer': 'Dev'}, {'box2d': 'http://pick.invalid/box.png'}))
    monkeypatch.setattr(fill, "look_game", lambda *a: {})
    monkeypatch.setattr(fill, "_download_one", lambda *a: (_ for _ in ()).throw(AssertionError("it has one: not downloaded")))
    done, _ = fill.fill_from_match("snes", rom, "77", ["box2d"], keep_name=True)
    game = scanner.get_game_details("snes", rom)
    assert done["success"] and game.name == "My Own Name" and game.desc == "Theirs." and (folder / "Typed Name.png").read_bytes() == b"mine"


def test_a_source_with_a_small_allowance_that_fails_is_left_alone_for_a_while(monkeypatch):
    from backend.routes import fill
    asked = []

    def failing(source, *a):
        asked.append(source)
        raise OSError("allowance used up")
    monkeypatch.setattr(fill, "_match", failing)
    monkeypatch.setattr(fill, "_resting", {})
    for _ in range(3):
        assert fill._look_one('thegamesdb', 'snes', 'A.sfc', None, None)['match']['error']
        fill._look_one('screenscraper', 'snes', 'A.sfc', None, None)
    assert asked == ['thegamesdb'] + ['screenscraper'] * 3
    fill._look_one('thegamesdb', 'snes', 'A.sfc', None, {'source': 'thegamesdb', 'query': 'A'})   # asked again yourself
    assert asked[-1] == 'thegamesdb'


def test_add_games_fills_a_new_game_through_fill_the_gaps(client, root, monkeypatch):
    from backend.routes import fill
    data = b"\x10" * 4096
    started = client.post("/api/uploads", json={"name": "Brand New (USA).sfc", "size": len(data), "key": f"add|{len(data)}"}).get_json()
    client.put(f"/api/uploads/{started['id']}?offset=0", data=data, headers={"Content-Type": "application/octet-stream"})
    asked = []
    monkeypatch.setattr(fill, "_candidates", lambda source, match_id, system: asked.append((source, match_id)) or _picked(
        {'name': 'Brand New', 'desc': 'Added and filled.'}, {'box2d': 'http://pick.invalid/box.png'}))
    monkeypatch.setattr(fill, "look_game", lambda *a: {})
    monkeypatch.setattr(fill, "_download_one", lambda url, target_dir, stem: (target_dir.mkdir(parents=True, exist_ok=True), (target_dir / f"{stem}.png").write_bytes(b"box")))
    done = client.post("/api/import/commit", json={"refs": [f"upload:{started['id']}"], "system": "snes", "game_id": "ra:4242",
                                                   "media": ["box2d", "not-a-kind"]}).get_json()
    assert done["success"] and done["rom_path"] == "Brand New (USA).sfc" and done["downloaded"] == ["box2d"], done
    assert asked == [("retroachievements", "retroachievements:4242")]
    game = client.get("/api/systems/snes/games").get_json()
    entry = next(g for g in (game.get("games") or game) if g["path"].endswith("Brand New (USA).sfc"))
    assert entry["name"] == "Brand New" and entry["desc"] == "Added and filled."
