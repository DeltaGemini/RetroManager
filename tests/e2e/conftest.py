"""
Browser tests: RetroManager running against a demo library of made-up games
(tools/make_demo_library.py), driven by Playwright in a real browser, for the
pages' own behaviour (the API tests above can't see that).

They're skipped where Playwright or a browser isn't there. The browser is
RM_BROWSER (a Chromium-family program, e.g. /usr/bin/chromium), else
Playwright's own Chromium (`playwright install chromium`).
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
# The pages here aren't the built ones: each compiles its JSX in the browser as it loads,
# which takes a few seconds, so what the tests look for is waited for as long as a page is
playwright_api.expect.set_options(timeout=15000)

ROOT = Path(__file__).resolve().parents[2]
PORT = int(os.environ.get("RM_E2E_PORT", "5099"))
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="session")
def demo():
    folder = Path(tempfile.mkdtemp(prefix="retromanager-demo-"))
    made = subprocess.run([sys.executable, str(ROOT / "tools" / "make_demo_library.py"), str(folder)],
                          cwd=ROOT, capture_output=True, text=True, env={k: v for k, v in os.environ.items() if not k.endswith("_PATH")})
    assert made.returncode == 0, made.stderr
    yield folder
    shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture(scope="session")
def server(demo):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("SCREENSCRAPER", "IGDB", "RETROACHIEVEMENTS", "STEAMGRIDDB", "THEGAMESDB")) and not k.endswith("_PATH")}
    env.update(ROMS_PATH=str(demo / "roms"), MEDIA_PATH=str(demo / "media"), DATA_PATH=str(demo / "retromanager"),
               SAVES_PATH=str(demo / "saves"), SAVESTATES_PATH=str(demo / "savestates"), SAVE_BACKUP_PATH=str(demo / "save-backups"),
               INBOX_PATH=str(demo / "inbox"), BIOS_PATH=str(demo / "BIOS"), THUMB_DIR=str(demo / "retromanager" / "thumbs"),
               SAVE_PROFILES="", RETROMANAGER_NO_BACKGROUND="1", LOG_LEVEL="WARNING", HASHEOUS="off")
    process = subprocess.Popen([sys.executable, "-c", f"from backend.app import app; app.run(port={PORT})"], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            urllib.request.urlopen(f"{BASE}/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.25)
    else:
        process.kill()
        pytest.fail("RetroManager didn't start for the browser tests")
    yield BASE
    process.terminate()
    process.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    executable = os.environ.get("RM_BROWSER") or next((p for p in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome", "/usr/bin/brave") if Path(p).exists()), None)
    with playwright_api.sync_playwright() as p:
        try:
            launched = p.chromium.launch(executable_path=executable, headless=True) if executable else p.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"No browser for the browser tests: {e}")
        yield launched
        launched.close()


def _page(browser, server, size):
    context = browser.new_context(viewport=size, base_url=server)
    page = context.new_page()
    page.set_default_timeout(15000)
    yield page
    context.close()


@pytest.fixture
def page(browser, server):
    """A desktop-sized page."""
    yield from _page(browser, server, {"width": 1440, "height": 900})


@pytest.fixture
def phone(browser, server):
    """A phone-sized page."""
    yield from _page(browser, server, {"width": 390, "height": 844})
