"""The pieces that work without the app: names, checksums, settings, stored state."""

import hashlib
from pathlib import Path

from backend import systems
from backend.library_state import LibraryState
from backend.libretro_thumbs import candidate_names
from backend.retroachievements import rom_hashes, split_title
from backend.rom_hashes import HashCache
from backend.rom_index import name_matches
from backend.scraper import text_date_to_es, to_es_date
from backend.settings import SettingsStore


def test_system_lookups_ignore_case_and_punctuation():
    assert systems.screenscraper_system_id("Super Nintendo") == systems.screenscraper_system_id("snes") == 4
    assert systems.igdb_platform_id("sg-1000") == systems.igdb_platform_id("SG1000")
    assert systems.retroachievements_console_id("gbc") == 6
    assert systems.libretro_thumbnail_folder("megadrive") == "Sega - Mega Drive - Genesis"
    assert systems.screenscraper_system_id("not-a-system") is None


def test_browser_playable_needs_a_known_system_and_a_usable_file():
    assert systems.browser_playable("gba", "Game.gba")
    assert systems.browser_playable("psx", "Game.cue")
    assert not systems.browser_playable("psx", "Game.m3u")
    assert not systems.browser_playable("ps2", "Game.iso")
    # Sega CD needs a BIOS, and the tests' BIOS folder is empty
    assert not systems.browser_playable("segacd", "Game.cue")


def test_dates():
    assert to_es_date("1991-08-13") == "19910813T000000"
    assert to_es_date("1991") == "19910101T000000"
    assert text_date_to_es("18 Apr, 2011") == "20110418T000000"
    assert text_date_to_es("March 11, 1995") == "19950311T000000"
    assert text_date_to_es("Coming soon") == ""


def test_retroachievements_titles():
    assert split_title("~Hack~ Pokemon - Ash Gray") == {"name": "Pokemon - Ash Gray", "tags": ["Hack"]}
    assert split_title("Advance Wars")["tags"] == []


def test_name_matches_tolerates_tags_and_alternate_titles():
    assert name_matches("Chrono Trigger", "Chrono Trigger (USA).sfc", "Chrono Trigger")
    assert name_matches("Another Code: Two Memories", "Another Code - Two Memories.nds", "Trace Memory | Another Code: Two Memories")
    assert not name_matches("Advance Wars: Dual Strike", "Advance Wars - Dual Strike.nds", "Advance Wars - Dark Conflict")


def test_thumbnail_names_try_regions_only_for_untagged_names():
    assert candidate_names(["Advance Wars"])[:2] == ["Advance Wars", "Advance Wars (USA)"]
    assert candidate_names(["Advance Wars (Europe)"]) == ["Advance Wars (Europe)"]


def test_hash_cache_and_header_skipping(tmp_path):
    cache = HashCache(tmp_path)
    plain = tmp_path / "plain.gba"
    plain.write_bytes(b"abc" * 100)
    assert cache.hashes(plain)["md5"] == hashlib.md5(b"abc" * 100).hexdigest()
    assert cache.hashes(tmp_path / "missing.gba") is None
    # An iNES header isn't part of the checksum RetroAchievements uses
    body = b"\x07" * 2048
    nes = tmp_path / "game.nes"
    nes.write_bytes(b"NES\x1a" + b"\x00" * 12 + body)
    assert rom_hashes("nes", nes, cache)[0] == hashlib.md5(body).hexdigest()
    # Arcade sets are known by their file name
    assert rom_hashes("arcade", tmp_path / "pacman.zip", cache) == [hashlib.md5(b"pacman").hexdigest()]


def test_settings_keep_secrets_out_of_what_the_panel_gets(tmp_path, monkeypatch):
    monkeypatch.setenv("IGDB_CLIENT_ID", "from-environment")
    store = SettingsStore(tmp_path)
    assert store.get("igdb_client_id") == "from-environment"
    assert store.get("libretro_thumbnails") == "fallback"
    assert store.update({"steamgriddb_api_key": "s3cret", "libretro_thumbnails": "first", "hasheous": "maybe", "nonsense": "x"}) == ["steamgriddb_api_key", "libretro_thumbnails"]
    described = {f["key"]: f for group in store.describe() for f in group["fields"]}
    assert described["steamgriddb_api_key"]["set"] and "value" not in described["steamgriddb_api_key"]
    assert "s3cret" not in str(store.describe())
    assert SettingsStore(tmp_path).get("libretro_thumbnails") == "first"
    store.update({"steamgriddb_api_key": ""})
    assert not {f["key"]: f for group in store.describe() for f in group["fields"]}["steamgriddb_api_key"]["set"]


def test_library_state_follows_a_renamed_game(tmp_path):
    state = LibraryState(tmp_path)
    state.set_status("snes/Old.sfc", "playing")
    collection = state.create_collection("Favourites of mine")
    state.set_membership(collection["id"], ["snes/Old.sfc", "snes/Other.sfc"], True)
    state.move_game("snes/Old.sfc", "snes/New.sfc")
    assert state.for_game("snes/New.sfc") == {"play_status": "playing", "collections": [collection["id"]]}
    assert state.for_game("snes/Old.sfc") == {"play_status": None, "collections": []}
    state.move_game("snes/New.sfc", None)
    assert LibraryState(tmp_path).snapshot()["collections"][0]["games"] == ["snes/Other.sfc"]
    files = state.export("/home/pi/RetroPie/roms")
    assert files == ["custom-Favourites of mine.cfg"]
    assert (Path(tmp_path) / "collections" / files[0]).read_text() == "/home/pi/RetroPie/roms/snes/Other.sfc\n"


def _retroarch_state(snapshot, compressed=True):
    """A state file as RetroArch writes it: its container, optionally compressed."""
    import struct
    import zlib
    padded = snapshot + b'\0' * (-len(snapshot) % 8)
    raw = b'RASTATE\x01' + b'MEM ' + struct.pack('<I', len(snapshot)) + padded + b'ACHV' + struct.pack('<I', 4) + b'abcd\0\0\0\0' + b'END ' + struct.pack('<I', 0)
    if not compressed:
        return raw
    out = b'#RZIPv\x01#' + struct.pack('<IQ', 16, len(raw))
    for i in range(0, len(raw), 16):
        chunk = zlib.compress(raw[i:i + 16])
        out += struct.pack('<I', len(chunk)) + chunk
    return out


def test_pi_states_unpack_and_identify(tmp_path):
    from backend import pi_states
    snapshot = b'GENPLUS-GX 1.7.6' + bytes(range(200))
    for compressed in (True, False):
        path = tmp_path / f"game.state{int(compressed)}"
        path.write_bytes(_retroarch_state(snapshot, compressed))
        assert pi_states.snapshot(path) == snapshot
        assert pi_states.describe(path) == ('Genesis Plus GX', 'genesis_plus_gx')
    # A state from before RetroArch's container is the snapshot itself
    bare = tmp_path / "old.state"
    bare.write_bytes(b'NST\x1a' + b'\x01' * 40)
    assert pi_states.snapshot(bare)[:4] == b'NST\x1a'
    assert pi_states.describe(bare) == ('Nestopia', 'nestopia')
    assert pi_states.identify(b'\x09\x00\x00\x01rest') == ('mGBA', 'mgba')          # Game Boy Advance
    assert pi_states.identify(b'\x03\x00\x40\x00rest') == ('mGBA', 'mgba')          # Game Boy
    assert pi_states.identify(b'MDFNSVST') == ('Beetle (Mednafen)', None)           # recognised, no browser core
    assert pi_states.identify(b'something else') == (None, None)


def test_series_matching_prefers_the_right_platform_and_avoids_hacks():
    from backend.series_index import MAIN, MOD, choose_match, plain
    assert plain("The Legend of Zelda (USA) [!]") == plain("Legend of Zelda")
    results = [
        {'id': 1, 'name': 'Chrono Trigger+', 'alternative_names': [{'name': 'Chrono Trigger'}], 'game_type': MOD, 'platforms': [19]},
        {'id': 2, 'name': 'Chrono Trigger', 'game_type': MAIN, 'platforms': [19, 20]},
    ]
    assert choose_match(results, 'Chrono Trigger (USA)', 19)[0]['id'] == 2
    # Same name on two systems: the one on this system's platform
    sonic = [{'id': 10, 'name': 'Sonic the Hedgehog', 'game_type': MAIN, 'platforms': [29]},
             {'id': 11, 'name': 'Sonic the Hedgehog', 'game_type': MAIN, 'platforms': [64]}]
    assert choose_match(sonic, 'Sonic The Hedgehog (UE) [!]', 64) == (sonic[1], 'exact')
    # A shortened name is a loose match; an unrelated one is none
    assert choose_match([{'id': 3, 'name': "Rhythm Thief & the Emperor's Treasure", 'game_type': MAIN}], 'Rhythm Thief', None)[1] == 'loose'
    assert choose_match([{'id': 4, 'name': 'Something Else', 'game_type': MAIN}], 'Rhythm Thief', None) == (None, None)


def test_series_view_counts_and_marks(tmp_path):
    from backend.series_index import SeriesIndex

    class NoIGDB:
        configured = True
    index = SeriesIndex(tmp_path / 'series.json', NoIGDB(), lambda system: None)
    import time
    index._data['series']['c1'] = {'name': 'Test', 'kind': 'series', 'fetched': time.time(), 'games': [
        {'id': 1, 'name': 'One', 'date': 1, 'platforms': ['NES'], 'type': None, 'cover': None},
        {'id': 2, 'name': 'Two', 'date': 2, 'platforms': ['Arcade'], 'type': None, 'cover': None},
        {'id': 3, 'name': 'Three', 'date': 3, 'platforms': ['SNES'], 'type': 'Remake', 'cover': None},
    ]}
    index._data['games']['nes/one.nes'] = {'id': 1, 'series': 'c1', 'owns': [1]}
    view = index.view('c1')
    assert (view['have'], view['total']) == (1, 3) and view['games'][0]['have'] == ['nes/one.nes']
    index.set_mark(3, 'want')
    index.skip_platform('c1', 'Arcade', True)
    view = index.view('c1')
    assert view['total'] == 2 and view['games'][1]['platform_skipped'] and view['games'][2]['mark'] == 'want'
    assert [g['name'] for g in index.overview()['wanted']] == ['Three']
    index.game_moved('nes/one.nes', 'nes/uno.nes')
    assert index.view('c1')['games'][0]['have'] == ['nes/uno.nes']
    # Kept on disk
    assert SeriesIndex(tmp_path / 'series.json', NoIGDB(), lambda system: None).view('c1')['total'] == 2


def test_series_matching_puts_the_system_before_an_exact_name():
    from backend.series_index import MAIN, choose_match
    results = [{'id': 1, 'name': "Disney's Aladdin", 'alternative_names': [{'name': 'Aladdin'}], 'game_type': MAIN, 'platforms': [411]},
               {'id': 2, 'name': "Disney's Aladdin", 'game_type': MAIN, 'platforms': [35, 64]}]
    assert choose_match(results, 'Aladdin  ', 64)[0]['id'] == 2


def test_series_picks_the_group_named_in_the_title(tmp_path):
    from backend.series_index import SeriesIndex

    class NoIGDB:
        configured = True
    index = SeriesIndex(tmp_path / 'series.json', NoIGDB(), lambda system: None)
    record = index._record_for({'id': 5, 'name': "Disney's Aladdin", 'franchises': [{'id': 1, 'name': 'Disney'}, {'id': 2, 'name': "Disney's Aladdin"}]}, 'exact')
    assert record['series'] == 'f2'
    assert index._record_for({'id': 6, 'name': 'Mickey Mania', 'franchises': [{'id': 1, 'name': 'Disney'}, {'id': 3, 'name': 'Mickey Mouse'}]}, 'exact')['series'] == 'f1'


def test_thegamesdb_turns_its_answers_into_gamelist_fields(tmp_path):
    from backend.thegamesdb import TheGamesDBAPI, TheGamesDBError, _to_es_date
    from backend.systems import thegamesdb_platform_id
    assert thegamesdb_platform_id("Super Nintendo") == 6 and thegamesdb_platform_id("nope") is None
    assert _to_es_date("1991-11-21") == "19911121T000000" and _to_es_date("soon") == ""

    asked = []
    answers = {
        "Games/ByGameName": {"data": {"count": 1, "games": [{"id": 12, "game_title": "Super Game", "release_date": "1991-11-21", "platform": 6}]},
                             "include": {"boxart": {"base_url": {"small": "https://cdn/small/"}, "data": {"12": [{"type": "boxart", "side": "back", "filename": "b.jpg"}, {"type": "boxart", "side": "front", "filename": "f.jpg"}]}},
                                         "platform": {"data": {"6": {"id": 6, "name": "Super Nintendo (SNES)"}}}}},
        "Games/ByGameID": {"data": {"games": [{"id": 12, "game_title": "Super Game", "release_date": "1991-11-21", "players": 2, "overview": " A game. ",
                                               "developers": [5], "publishers": [7], "genres": [1, 2]}]}},
        "Games/Images": {"data": {"base_url": {"original": "https://cdn/original/"}, "images": {"12": [
            {"type": "boxart", "side": "front", "filename": "f.jpg"}, {"type": "boxart", "side": "back", "filename": "b.jpg"},
            {"type": "screenshot", "filename": "s1.jpg"}, {"type": "screenshot", "filename": "s2.jpg"}, {"type": "clearlogo", "filename": "l.png"}]}}},
        "Genres": {"data": {"genres": {"1": {"id": 1, "name": "Action"}, "2": {"id": 2, "name": "Platform"}}}},
        "Developers": {"data": {"developers": {"5": {"id": 5, "name": "Dev Co"}}}},
        "Publishers": {"data": {"publishers": {"7": {"id": 7, "name": "Pub Co"}}}},
    }

    class Answer:
        status_code = 200
        text = ""
        def __init__(self, body): self.body = body
        def json(self): return self.body

    class Session:
        def get(self, url, params=None, timeout=None):
            asked.append((url.split("/v1/")[1], dict(params)))
            return Answer(answers[url.split("/v1/")[1]])

    api = TheGamesDBAPI("", tmp_path)
    try:
        api.search_game("x")
        assert False, "a search without a key should say so"
    except TheGamesDBError as e:
        assert "Settings" in str(e)
    api.api_key, api.session = "key", Session()
    hit = api.summarize_search_result(api.search_game("super", "snes")[0])
    assert hit["id"] == 12 and hit["year"] == "1991" and hit["cover_url"] == "https://cdn/small/f.jpg" and hit["platform_names"] == "Super Nintendo (SNES)"
    assert asked[0] == ("Games/ByGameName", {"apikey": "key", "name": "super", "fields": "platform", "include": "boxart,platform", "filter[platform]": 6})
    data = api.extract_game_data(api.get_game_info(12))
    assert (data["desc"], data["releasedate"], data["players"]) == ("A game.", "19911121T000000", "2")
    assert (data["developer"], data["publisher"], data["genre"]) == ("Dev Co", "Pub Co", "Action, Platform")
    assert data["media"] == {"box2d": "https://cdn/original/f.jpg", "boxback": "https://cdn/original/b.jpg", "screenshot": "https://cdn/original/s1.jpg",
                             "screenshot_2": "https://cdn/original/s2.jpg", "wheel": "https://cdn/original/l.png"}
    # The names are kept, so another game doesn't ask for the lists again
    before = len(asked)
    TheGamesDBAPI("key", tmp_path)._name_lists()
    assert len(asked) == before and (tmp_path / "thegamesdb-names.json").exists()


def test_a_manual_is_taken_from_an_english_speaking_region_before_europe():
    from backend.scraper import ScreenscraperAPI
    medias = [{"type": "manuel", "region": "eu", "url": "eu.pdf"}, {"type": "manuel", "region": "uk", "url": "uk.pdf"},
              {"type": "box-2D", "region": "uk", "url": "uk.png"}, {"type": "box-2D", "region": "eu", "url": "eu.png"}]
    media = ScreenscraperAPI('', '').extract_media({"medias": medias})
    assert media["manuals"] == "uk.pdf" and media["box2d"] == "eu.png"
    assert ScreenscraperAPI('', '').extract_media({"medias": medias[:1] + [{"type": "manuel", "region": "fr", "url": "fr.pdf"}]})["manuals"] == "eu.pdf"


def test_gametdb_reads_a_games_id_from_its_rom(tmp_path):
    from backend import gametdb
    from backend.systems import gametdb_platform
    assert gametdb_platform("gc") == "wii" and gametdb_platform("nds") == "ds" and gametdb_platform("snes") is None

    def rom(name, at, data):
        path = tmp_path / name
        path.write_bytes(b"\0" * at + data + b"\0" * 64)
        return path
    assert gametdb.game_id("wii", rom("a.iso", 0, b"GALE01")) == "GALE01"
    assert gametdb.game_id("wii", rom("a.wbfs", 0x200, b"RMGE01")) == "RMGE01"
    assert gametdb.game_id("wii", rom("a.rvz", 0x58, b"RUUE01")) == "RUUE01"
    assert gametdb.game_id("wii", rom("a.gcz", 0, b"GALE01")) is None and gametdb.game_id("wii", rom("b.iso", 0, b"\x01\x02 junk")) is None
    assert gametdb.game_id("ds", rom("a.nds", 0x0C, b"AWRE")) == "AWRE"
    assert gametdb.game_id("3ds", tmp_path / "Game (CTR-P-AC3P) (E).cia") == "AC3P"
    card = bytearray(0x4200)
    card[0x100:0x104], card[0x120:0x124] = b"NCSD", (0x20).to_bytes(4, "little")
    card[0x4100:0x4104], card[0x4150:0x415A] = b"NCCH", b"CTR-P-AREE"
    assert gametdb.game_id("3ds", rom("a.3ds", 0, bytes(card))) == "AREE"
    assert gametdb.game_id("ps3", rom("a.iso", 0x800, b"PlayStation3\0\0\0\0BLES-00761")) == "BLES00761"
    (tmp_path / "Game.ps3/PS3_GAME").mkdir(parents=True)
    (tmp_path / "Game.ps3/PS3_GAME/PARAM.SFO").write_bytes(b"\0PSF junk TITLE_ID\0BLUS31146\0")
    assert gametdb.game_id("ps3", tmp_path / "Game.ps3") == "BLUS31146"
    assert gametdb._regions("wii", "GALP01") == ["EN", "US", "JA"] and gametdb._regions("ps3", "BLUS31146") == ["US", "EN", "JA"]

    # The picture is the first region's that's there
    tdb = gametdb.GameTDB()
    asked = []

    class Session:
        def head(self, url, **kw):
            asked.append(url)
            return type("R", (), {"status_code": 200 if "/US/" in url else 404})()
    tdb.session = Session()
    assert tdb.support_url("gc", rom("b.iso", 0, b"GALP01")) == "https://art.gametdb.com/wii/disc/US/GALP01.png"
    assert asked == ["https://art.gametdb.com/wii/disc/EN/GALP01.png", "https://art.gametdb.com/wii/disc/US/GALP01.png"]
    assert tdb.support_url("snes", rom("c.sfc", 0, b"GALP01")) is None
    # By hand: the disc, cover and 3D box of the game the ROM is
    assert tdb.find("wii", rom("d.iso", 0, b"RMGE01")) == "wii:RMGE01"
    assert tdb.game("wii:RMGE01") == {folder: f"https://art.gametdb.com/wii/{kind}/US/RMGE01.png" for folder, kind in (("support", "disc"), ("box2d", "cover"), ("box3d", "cover3D"))}
    import pytest
    for bad in (lambda: tdb.find("snes", None), lambda: tdb.find("wii", rom("e.gcz", 0, b"x")), lambda: tdb.game("wii:../x")):
        with pytest.raises(ValueError):
            bad()


def test_where_a_picture_came_from_is_remembered_until_the_file_changes(tmp_path):
    from backend.media_sources import MediaSources, source_of
    assert source_of("https://images.launchbox-app.com/a.png") == "LaunchBox" and source_of("https://neoclone.screenscraper.fr/api2/mediaJeu.php?x=1") == "ScreenScraper"
    assert source_of("https://example.org/a.png") == "example.org" and source_of("") is None
    media = tmp_path / "media"
    (media / "snes/box2d").mkdir(parents=True)
    sources = MediaSources(tmp_path, media)
    assert sources.for_paths(["snes/box2d/Game.png"]) == {}
    (media / "snes/box2d/Game.jpg").write_bytes(b"first")
    sources.record(media / "snes/box2d/Game.jpg", "IGDB")
    (media / "snes/box2d/Game.png").write_bytes(b"picture")
    sources.record(media / "snes/box2d/Game.png", "LaunchBox")
    found = sources.for_paths(["snes/box2d/Game.png", "snes/box2d/Game.jpg", None, "snes/box2d/Other.png"])
    assert list(found) == ["snes/box2d/Game.png"] and found["snes/box2d/Game.png"]["source"] == "LaunchBox"
    (media / "snes/box2d/Game.png").write_bytes(b"changed by hand")
    assert sources.for_paths(["snes/box2d/Game.png"]) == {}
    sources.record(tmp_path / "elsewhere.png", "x")  # not a media file: ignored


def test_launchbox_indexes_its_list_and_finds_a_game_by_title(tmp_path):
    import zipfile
    from backend.launchbox import LaunchBoxIndex

    def image(game, kind, region, name):
        return f"<GameImage><DatabaseID>{game}</DatabaseID><FileName>{name}</FileName><Type>{kind}</Type>" + (f"<Region>{region}</Region>" if region else "") + "</GameImage>"
    xml = ("<?xml version='1.0'?><LaunchBox>"
           "<Game><Name>Super Metroid</Name><DatabaseID>1</DatabaseID><Platform>Super Nintendo Entertainment System</Platform></Game>"
           "<Game><Name>Super Metroid</Name><DatabaseID>2</DatabaseID><Platform>Some Other Machine</Platform></Game>"
           "<Game><Name>Crazy Taxi</Name><DatabaseID>3</DatabaseID><Platform>Nintendo GameCube</Platform></Game>"
           "<GameAlternateName><AlternateName>Metroid 3</AlternateName><DatabaseID>1</DatabaseID></GameAlternateName>"
           + image(1, "Cart - Front", "Japan", "jp.png") + image(1, "Cart - Front", "North America", "us.png") + image(1, "Fanart - Cart - Front", "", "fan.png")
           + image(1, "Box - Front", "Europe", "box.jpg") + image(1, "Advertisement Flyer - Front", "", "ad.jpg")
           + image(2, "Cart - Front", "", "other.png") + image(3, "Fanart - Disc", "", "fandisc.png") + "</LaunchBox>")
    with zipfile.ZipFile(tmp_path / "Metadata.zip", "w") as archive:
        archive.writestr("Metadata.xml", xml)
    index = LaunchBoxIndex(tmp_path)
    assert index.pictures("snes", ["Super Metroid"]) == {}  # off, and no list yet
    index.enabled = True
    index.build(tmp_path / "Metadata.zip")
    assert index.ready and not index.stale and not index.refresh_if_needed()
    at = "https://images.launchbox-app.com/"
    assert index.pictures("snes", ["Nope", "Super Metroid (USA) [!]"]) == {"support": at + "us.png", "box2d": at + "box.jpg"}
    assert index.pictures("snes", ["Metroid 3"])["support"] == at + "us.png"
    assert index.pictures("gc", ["Crazy Taxi"]) == {"support": at + "fandisc.png"}
    # Searched by hand: every word, a game of exactly that title first, with the other pictures to choose from
    found = index.search("snes", "metroid (USA)")
    assert [(g["id"], g["name"]) for g in found] == [(1, "Super Metroid")] and found[0]["cover_url"] == at + "box.jpg"
    assert index.game(1) == {"name": "Super Metroid", "media": {"support": at + "us.png", "support_2": at + "jp.png", "support_3": at + "fan.png", "box2d": at + "box.jpg"}}
    assert index.search("gc", "metroid") == []
    assert index.pictures("gba", ["Super Metroid"]) == {} and index.pictures("snes", ["Super Metroid 2"]) == {} and index.pictures("nope", ["Super Metroid"]) == {}
