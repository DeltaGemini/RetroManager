"""Matching on a source other than ScreenScraper, for Fill the gaps (stood in for here: nothing goes out)."""

from backend.thegamesdb import TheGamesDBError


def _stand_in(monkeypatch, found, info):
    from backend.routes import sources
    monkeypatch.setitem(sources._OTHER_SOURCES, 'thegamesdb', ('TheGamesDB', (TheGamesDBError,), lambda data, name: found(name), lambda data: info(data)))


def test_a_game_is_matched_on_another_source(client, root, monkeypatch):
    (root / "roms" / "snes" / "Source Quest (USA).sfc").write_bytes(b"\x08" * 4096)
    asked = []

    def found(name):
        asked.append(name)
        return [{'id': 9, 'name': 'Source Quest II', 'cover_url': None, 'platform_names': 'SNES', 'year': '1994', 'is_hack': False, 'hash_match': False},
                {'id': 7, 'name': 'Source Quest', 'cover_url': 'http://example.invalid/c.png', 'platform_names': 'SNES', 'year': '1993', 'is_hack': False, 'hash_match': False}]

    def info(data):
        assert data['game_id'] == '7'
        return {'name': 'Source Quest', 'desc': 'A quest, from another source.', 'developer': 'Somebody', 'media': {'box2d_1': None}}

    _stand_in(monkeypatch, found, info)
    from backend.routes import fill
    monkeypatch.setattr(fill, 'available_sources', lambda: [{'id': 'thegamesdb', 'available': True}])
    looked = client.post("/api/fill/look", json={"system_name": "snes", "rom_path": "Source Quest (USA).sfc", "sources": ["thegamesdb"]}).get_json()
    match = looked["sources"]["thegamesdb"]["match"]
    assert asked == ["Source Quest"]                                   # its title, without the tags
    assert match["confidence"] == "likely" and match["id"] == "thegamesdb:7"   # the sequel isn't taken
    assert match["alternatives"][0]["id"] == "thegamesdb:7"
    assert looked["sources"]["thegamesdb"]["candidates"]["fields"]["desc"] == "A quest, from another source."


def test_a_source_whose_key_isnt_set_says_so(client, root, monkeypatch):
    def found(name):
        raise TheGamesDBError("Add your TheGamesDB API key in Tools > Settings")
    _stand_in(monkeypatch, found, lambda data: {})
    from backend.routes import fill
    monkeypatch.setattr(fill, 'available_sources', lambda: [{'id': 'thegamesdb', 'available': True}])
    answer = client.post("/api/fill/look", json={"system_name": "snes", "rom_path": "Game Two.sfc", "sources": ["thegamesdb"]}).get_json()
    match = answer["sources"]["thegamesdb"]["match"]
    assert match["confidence"] == "none" and "key" in match["error"]


def test_each_sources_pictures_are_put_in_retromanagers_folders():
    from backend.routes.scraping import _as_folders
    assert _as_folders({'cover': 'c', 'screenshot_2': 's2', 'screenshot_1': 's1', 'artwork_1': 'a'}) == {'box2d': 'c', 'screenshot': 's1', 'fanart': 'a'}
    assert _as_folders({'grid_1': 'g', 'hero_1': 'h', 'logo_1': 'l', 'video': 'v'}) == {'box2d': 'g', 'fanart': 'h', 'wheel': 'l'}
