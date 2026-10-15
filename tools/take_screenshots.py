"""
Takes the README's screenshots (docs/screenshots/*.webp) of RetroManager
running against the demo library of made-up games (tools/make_demo_library.py),
so they show no one else's games. Needs a Chromium-family browser on this
machine and Playwright for Python (it drives the browser that's there, and
downloads none):

    python tools/make_demo_library.py /tmp/demo
    python tools/take_screenshots.py /tmp/demo /usr/bin/chromium
"""

import io
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs' / 'screenshots'
PORT = 5077
SIZE = {'width': 1440, 'height': 900}


def serve(library: Path):
    env = dict(os.environ, ROMS_PATH=str(library / 'roms'), MEDIA_PATH=str(library / 'media'),
               DATA_PATH=str(library / 'retromanager'), SAVES_PATH=str(library / 'saves'),
               SAVESTATES_PATH=str(library / 'savestates'), SAVE_BACKUP_PATH=str(library / 'save-backups'),
               INBOX_PATH=str(library / 'inbox'), BIOS_PATH=str(library / 'BIOS'), THUMB_DIR=str(library / 'retromanager' / 'thumbs'),
               SAVE_PROFILES='', RETROMANAGER_NO_BACKGROUND='1', LOG_LEVEL='WARNING', SYSTEM_TILES='1')
    for name in [n for n in env if n.startswith(('SCREENSCRAPER', 'IGDB', 'RETROACHIEVEMENTS', 'STEAMGRIDDB', 'THEGAMESDB'))]:
        del env[name]
    code = f"from backend.app import app; app.run(port={PORT})"
    server = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, env=env)
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/health', timeout=1)
            return server
        except OSError:
            time.sleep(0.5)
    server.kill()
    sys.exit("RetroManager didn't start")


def save(page, name):
    picture = Image.open(io.BytesIO(page.screenshot()))
    picture.save(OUT / f'{name}.webp', quality=82, method=6)
    print('Wrote', OUT / f'{name}.webp')


def settle(page, seconds=2.5):
    page.wait_for_load_state('networkidle')
    time.sleep(seconds)


def main(library: Path, browser_path: str):
    first_gba = sorted((library / 'roms' / 'gba').glob('*.gba'))[3].name
    server = serve(library)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=browser_path, headless=True)
            page = browser.new_page(viewport=SIZE, device_scale_factor=1)
            page.goto(f'http://127.0.0.1:{PORT}/?system=gba&game=./{first_gba}')
            settle(page)
            save(page, 'library')
            page.goto(f'http://127.0.0.1:{PORT}/?tool=health')
            settle(page)
            save(page, 'library-health')
            page.goto(f'http://127.0.0.1:{PORT}/shelf')
            settle(page, 4)
            save(page, 'bookcase')
            # (the shelf works out which box was clicked from where: a click there, as a mouse makes it)
            spot = page.locator('.spine').nth(5).bounding_box()
            page.mouse.click(spot['x'] + spot['width'] / 2, spot['y'] + spot['height'] / 2)
            settle(page, 2)
            save(page, 'bookcase-open')
            page.goto(f'http://127.0.0.1:{PORT}/timeline')
            settle(page, 4)
            save(page, 'timeline')
            page.get_by_role('button', name='Decades').first.click()
            settle(page, 3)
            save(page, 'timeline-decades')
            browser.close()
    finally:
        server.terminate()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).resolve(), sys.argv[2])
