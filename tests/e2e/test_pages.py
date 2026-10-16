"""What the pages do, in a browser (see conftest.py)."""

import json
import re
import urllib.request

from playwright.sync_api import expect


def api(server, path, body=None, method=None):
    request = urllib.request.Request(server + path, data=json.dumps(body).encode() if body is not None else None,
                                     method=method or ("POST" if body is not None else "GET"), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request))


def home_rows(page):
    """The Console's first screen, once its rows have come (they're worked out in the background)."""
    page.goto("/console")
    expect(page.locator(".console-group-name", has_text="Recently added")).to_be_visible(timeout=30000)
    return page.locator(".console-group-name").all_inner_texts()


def test_the_console_shows_its_rows_and_every_system(page):
    rows = home_rows(page)
    assert "Recently added" in rows and "Systems" in rows
    expect(page.locator(".console-row.big .console-tile")).to_have_count(10)


def test_a_game_opened_on_the_first_screen_goes_back_there(phone):
    home_rows(phone)
    phone.keyboard.press("ArrowRight")
    phone.keyboard.press("e")   # its page, not playing it
    expect(phone.get_by_role("button", name="‹ Home")).to_be_visible()
    phone.keyboard.press("Escape")
    expect(phone.locator(".console-group-name").first).to_be_visible()
    assert "system=" not in phone.url


def test_a_game_opened_from_its_system_goes_back_to_the_list(phone):
    phone.goto("/console?system=snes")
    phone.locator(".game-card-content").first.click()
    expect(phone.get_by_role("button", name="‹ Games")).to_be_visible()
    phone.keyboard.press("Escape")
    expect(phone.locator(".game-card-content").first).to_be_visible()
    assert "system=snes" in phone.url


def test_a_game_taken_out_of_a_collection_leaves_it_at_once(page, server):
    made = api(server, "/api/collections", {"name": "Browser test"})["collection"]
    games = sorted(g["path"] for g in api(server, "/api/systems/nes/games")["games"] if g.get("has_metadata"))[:2]
    api(server, f"/api/collections/{made['id']}/games", {"games": [{"system": "nes", "rom_path": g} for g in games], "member": True}, "PUT")
    page.goto(f"/console?list={made['id']}&game=nes%2F{games[0][2:]}")
    page.locator(".gd-status .gd-chip", has_text="📁").click()
    box = page.locator(".gd-menu label", has_text="Browser test").locator("input")
    expect(box).to_be_checked()
    box.click()   # (it changes once RetroManager has answered)
    expect(box).not_to_be_checked()
    page.keyboard.press("Escape")   # the menu
    page.locator("body").click(position={"x": 5, "y": 300})
    page.keyboard.press("Escape")   # the list
    expect(page.locator(".console-tile-list", has_text="Browser test")).to_contain_text("1 game")
    assert len(next(c for c in api(server, "/api/library-state")["collections"] if c["id"] == made["id"])["games"]) == 1


def test_game_tiles_can_take_their_pictures_width_and_it_stays_so(page):
    home_rows(page)
    page.get_by_role("button", name="Console settings").click()
    page.get_by_role("menuitemradio", name=re.compile("As wide as the picture")).click()
    page.keyboard.press("Escape")
    expect(page.locator(".console-screen.fit-pictures")).to_have_count(1)
    page.reload()
    expect(page.locator(".console-screen.fit-pictures")).to_have_count(1)


def test_a_list_of_several_systems_puts_the_year_and_system_under_the_name(page, server):
    page.goto("/console")
    page.locator(".console-search input").fill("Derby")
    page.locator(".console-search input").press("Enter")
    # (a game with a year shows both: one without shows only its system)
    expect(page.locator(".game-sub", has_text=re.compile(r"^\d{4} · \w"))).not_to_have_count(0)
    expect(page.locator(".game-name", has_text=re.compile(r"\d{4}"))).to_have_count(0)


def test_the_library_opens_a_game_from_its_address(page, server):
    game = sorted(g["path"] for g in api(server, "/api/systems/gba/games")["games"] if g.get("has_metadata"))[0]
    page.goto(f"/?system=gba&game={game}")
    expect(page.locator(".gd-title")).to_have_text(re.compile(r"\w"))
    expect(page.locator(".game-card-content")).not_to_have_count(0)


def test_the_first_run_page_walks_through_its_steps(page):
    page.goto("/setup")
    expect(page.get_by_role("heading", name="Your library")).to_be_visible()
    page.get_by_role("button", name="Next").click()
    expect(page.get_by_role("heading", name=re.compile("ScreenScraper"))).to_be_visible()
    page.get_by_role("button", name="Skip for now").click()
    expect(page.get_by_role("heading", name=re.compile("Who can change things"))).to_be_visible()
    page.get_by_role("button", name="Not now").click()
    expect(page.get_by_role("heading", name="That's it")).to_be_visible()


def test_a_reload_comes_back_to_the_open_system_and_game(page, phone):
    # The Library: the address follows what's open, so a reload lands there
    page.goto("/")
    page.locator(".system-item", has_text="Nintendo Entertainment System").first.click()
    page.get_by_text("Cobalt Harbour", exact=True).first.click()
    expect(page).to_have_url(re.compile(r"system=nes&game=.*Cobalt"))
    page.reload()
    expect(page.locator(".gd-heading", has_text="Cobalt Harbour")).to_be_visible()

    # The Console on a phone: a game picked on the list comes back picked, not open
    phone.goto("/console?system=nes&at=Cobalt%20Harbour.nes")
    expect(phone.locator(".console-columns.list-only")).to_be_visible()
    phone.get_by_text("Cobalt Harbour", exact=True).first.click()
    expect(phone).to_have_url(re.compile(r"game=.*Cobalt"))
    phone.reload()
    expect(phone.get_by_role("button", name="‹ Games")).to_be_visible()


def test_cockney_changes_the_words_but_not_the_games(page):
    page.goto("/?system=nes&game=./Cobalt%20Harbour.nes")
    page.evaluate("localStorage.setItem('retromanager.language', 'cockney')")
    page.reload()
    expect(page.locator(".rm-label", has_text="Lib'ry")).to_be_visible()
    expect(page.get_by_text("Who Made It")).not_to_have_count(0)
    expect(page.locator(".gd-heading", has_text="Cobalt Harbour")).to_be_visible()   # a game's name is its own
    assert page.evaluate("document.documentElement.lang") == "en-GB"
    page.evaluate("localStorage.setItem('retromanager.language', 'en')")
    page.reload()
    expect(page.locator(".rm-label", has_text="Library")).to_be_visible()
