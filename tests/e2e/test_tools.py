"""The newer screens in a browser (see conftest.py): Fill the gaps, the background scrape's review,
a game's ROM replaced or patched, the picture view, and the Console's Playing and Backlog. The
scraping sources are stood in for in the page, so nothing goes out to the internet."""

import re
from urllib.parse import quote

from playwright.sync_api import expect

from test_pages import api, home_rows

STAND_IN = {
    "igdb": {"match": {"confidence": "exact", "id": "igdb:1", "name": "Stand-in", "alternatives": []},
             "candidates": {"media": {}, "fields": {"desc": "Told by IGDB.", "developer": "IGDB Studio"}}},
    "thegamesdb": {"match": {"confidence": "likely", "id": "thegamesdb:2", "name": "Stand-in", "alternatives": []},
                   "candidates": {"media": {}, "fields": {"desc": "Told by TheGamesDB.", "developer": "TGDB Studio"}}},
}


def _stand_in_sources(page):
    """IGDB and TheGamesDB set up, and what they say about any game."""
    page.route("**/api/fill/look", lambda route: route.fulfill(json={"success": True, "sources": STAND_IN}))

    def sources(route):
        listed = route.fetch().json()
        listed["sources"] = [dict(s, available=True) if s["id"] in STAND_IN else s for s in listed["sources"]]
        route.fulfill(json=listed)
    page.route("**/api/scrape-sources", sources)


def _open_tool(page, tool, options):
    # (once the Library is up and listening)
    page.wait_for_selector(".system-item")
    page.evaluate("([tool, options]) => window.dispatchEvent(new CustomEvent('retromanager:open-tool', {detail: {tool, options}}))", [tool, options])


def _games(server, system):
    return sorted((g for g in api(server, f"/api/systems/{system}/games")["games"] if g.get("has_metadata")), key=lambda g: g["path"])


def test_fill_the_gaps_chooses_with_the_keys_and_applies(page, server):
    game = _games(server, "nes")[0]
    _stand_in_sources(page)
    page.goto("/")
    _open_tool(page, "fill", {"games": [{"system": "nes", "path": game["path"]}], "kinds": ["desc", "developer"], "replace": True, "start": True})
    expect(page.locator(".fill-kb-row")).to_have_attribute("data-row", "desc")
    page.keyboard.press("3")                      # Now, IGDB, TheGamesDB: TheGamesDB's description
    page.keyboard.press("ArrowDown")
    expect(page.locator(".fill-kb-row")).to_have_attribute("data-row", "developer")
    page.keyboard.press("2")                      # IGDB's developer
    expect(page.get_by_text(re.compile(r"2 changes across 1 game"))).to_be_visible()
    page.keyboard.press("a")
    expect(page.locator(".fill-report")).to_contain_text("Description replaced from TheGamesDB")
    saved = api(server, f"/api/systems/nes/games/{quote(game['path'].lstrip('./'))}")["game"]
    assert saved["desc"] == "Told by TheGamesDB." and saved["developer"] == "IGDB Studio"


def test_what_the_background_scrape_found_opens_in_fill_the_gaps(page, server):
    # (a game with no details: what the background scrape looks for, and what Review shows, are gaps)
    game = next(g for g in api(server, "/api/systems/psx/games")["games"] if not g.get("has_metadata"))
    rom = game["path"].lstrip("./")
    page.route("**/api/fill/background", lambda route: route.fulfill(json={
        "success": True, "running": False, "stopping": False, "total": 1, "done": 1, "current": None, "found": 1, "found_now": 1,
        "skipped_recent": 0, "started": None, "finished": None, "stopped_reason": None,
        "systems": [{"system": "psx", "system_name": "Sony PlayStation", "games": [{"rom": rom, "name": game["name"], "offered": ["developer"], "at": 0}]}]}))
    page.route("**/api/fill/found?*", lambda route: route.fulfill(json={"success": True, "sources": STAND_IN, "at": 0}))
    looked = []
    page.route("**/api/fill/look", lambda route: (looked.append(1), route.fulfill(json={"success": True, "sources": {}})))
    _stand_in_sources_only_list(page)
    page.goto("/")
    _open_tool(page, "scrape", {})
    expect(page.get_by_text("Found, to check")).to_be_visible()
    page.get_by_role("button", name="Review", exact=True).click()
    expect(page.locator(".fill-field[data-row=developer]")).to_contain_text("IGDB Studio")
    assert not looked                              # what was found, not asked again


def _stand_in_sources_only_list(page):
    def sources(route):
        listed = route.fetch().json()
        listed["sources"] = [dict(s, available=True) if s["id"] in STAND_IN else s for s in listed["sources"]]
        route.fulfill(json=listed)
    page.route("**/api/scrape-sources", sources)


def _open_rom_file(page, system, path):
    page.goto(f"/?system={system}&game={path}")
    head = page.locator(".gd-section-head", has_text="ROM file")
    expect(head).to_be_visible()
    if head.get_attribute("aria-expanded") != "true":
        head.click()
    expect(page.get_by_role("button", name="Replace with an updated ROM…")).to_be_visible()


def test_a_rom_is_replaced_under_its_name_with_its_version(page, server):
    game = _games(server, "gba")[2]
    rom = game["path"].lstrip("./")
    _open_rom_file(page, "gba", game["path"])
    page.get_by_role("button", name="Replace with an updated ROM…").click()
    page.locator(".gd-replace input[type=file]").set_input_files({"name": "Updated (Rev 1).gba", "mimeType": "application/octet-stream", "buffer": b"UPDATED ROM " * 100})
    page.locator(".gd-replace input.gd-input").fill("Rev 1")
    expect(page.locator(".gd-replace")).to_contain_text(f"It's saved as {rom}")
    page.get_by_role("button", name="Replace the ROM").click()
    expect(page.locator(".gd-romfile")).to_contain_text("Before")
    record = api(server, f"/api/systems/gba/rom-version?rom={quote(rom)}")
    assert record["version"] == "Rev 1" and record["history"]


def _ips(changes):
    return b"PATCH" + b"".join(o.to_bytes(3, "big") + len(d).to_bytes(2, "big") + d for o, d in changes) + b"EOF"


def test_a_patch_makes_a_new_game_beside_the_old(page, server):
    game = _games(server, "gba")[3]
    _open_rom_file(page, "gba", game["path"])
    page.get_by_role("button", name="Apply a patch…").click()
    page.locator(".gd-replace input[type=file]").set_input_files({"name": "Browser Test Hack.ips", "mimeType": "application/octet-stream", "buffer": _ips([(0, b"HACK")])})
    expect(page.locator(".gd-replace input.gd-input").first).to_have_value("Browser Test Hack")
    page.get_by_role("button", name="Apply the patch").click()
    expect(page.locator(".gd-title")).to_have_text("Browser Test Hack")
    # (the section stays as it was left: open)
    expect(page.locator(".gd-romfile")).to_contain_text("Made from")
    assert any(g["path"] == "./Browser Test Hack.gba" for g in api(server, "/api/systems/gba/games")["games"])


def test_a_games_picture_opens_fitted_to_a_phones_screen_and_back_closes_it(phone, server):
    game = _games(server, "psx")[0]
    phone.goto(f"/?system=psx&game={game['path']}")
    phone.locator(".gd-art a").click()
    picture = phone.locator(".gd-picture-view img")
    expect(picture).to_be_visible()
    box, size = picture.bounding_box(), phone.viewport_size
    assert box["width"] <= size["width"] and box["height"] <= size["height"]
    url = phone.url
    phone.go_back()
    expect(phone.locator(".gd-picture-view")).to_have_count(0)
    assert phone.url == url                        # still on the game


def test_the_console_has_playing_and_backlog_lists(page, server):
    game = _games(server, "megadrive")[0]
    api(server, "/api/play-status", {"system": "megadrive", "rom_path": game["path"].lstrip("./"), "status": "playing"}, method="PUT")
    try:
        home_rows(page)
        expect(page.locator(".console-group-name", has_text="Your lists")).to_be_visible(timeout=30000)
        expect(page.locator(".console-tile", has_text="Playing")).to_contain_text("1 game")
    finally:
        api(server, "/api/play-status", {"system": "megadrive", "rom_path": game["path"].lstrip("./"), "status": None}, method="PUT")
