"""Fill the gaps: looking a game up on the sources, choosing, and remembering the matches.
The sources are stood in for here, and so is downloading: nothing goes out."""

from pathlib import Path

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
