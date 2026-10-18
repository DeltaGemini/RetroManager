"""
A throwaway library for the tests: ROM, media, save and data folders in a
temporary directory, which the app is pointed at before it's imported. Nothing
here touches a real library, and nothing goes out to the internet.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(tempfile.mkdtemp(prefix="retromanager-tests-"))
for folder in ("roms/snes", "roms/gba", "roms/psx", "media", "data", "saves/guest/snes", "savestates", "save-backups", "inbox", "bios"):
    (ROOT / folder).mkdir(parents=True)
os.environ.update(
    ROMS_PATH=str(ROOT / "roms"), MEDIA_PATH=str(ROOT / "media"), DATA_PATH=str(ROOT / "data"),
    SAVES_PATH=str(ROOT / "saves"), SAVESTATES_PATH=str(ROOT / "savestates"), SAVE_BACKUP_PATH=str(ROOT / "save-backups"),
    INBOX_PATH=str(ROOT / "inbox"), BIOS_PATH=str(ROOT / "bios"), THUMB_DIR=str(ROOT / "data" / "thumbs"),
    SAVE_PROFILES="family,guest", LOG_LEVEL="WARNING", RETROMANAGER_NO_BACKGROUND="1",
)
# No accounts or keys: nothing can reach a scraping source by accident
for name in list(os.environ):
    if name.startswith(("SCREENSCRAPER_", "IGDB_", "RETROACHIEVEMENTS_", "STEAMGRIDDB_", "THEGAMESDB_")):
        del os.environ[name]
os.environ["HASHEOUS"] = "off"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

(ROOT / "roms/snes/Game One (USA).sfc").write_bytes(b"\x01" * 4096)
(ROOT / "roms/snes/Game Two.sfc").write_bytes(b"\x02" * 4096)
(ROOT / "roms/snes/Empty.sfc").write_bytes(b"")
(ROOT / "roms/gba/Pocket Game.gba").write_bytes(b"\x03" * 4096)
(ROOT / "roms/psx/Disc Game.cue").write_text('FILE "Disc Game (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
(ROOT / "roms/psx/Disc Game (Track 1).bin").write_bytes(b"\x04" * 2048)


@pytest.fixture(scope="session")
def root():
    return ROOT


@pytest.fixture(scope="session")
def client():
    from backend.app import app
    return app.test_client()


@pytest.fixture(autouse=True)
def _no_source_resting():
    """A source one test made fail isn't left out of the next test's look-ups."""
    from backend.routes import fill
    fill._resting.clear()
