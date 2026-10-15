"""
Settings that can be changed from the app (Tools > Settings): the accounts and
keys for the scraping sources, and how matching and media behave.

They live in settings.json in DATA_PATH, not in docker-compose.yml. A setting
that hasn't been saved yet takes its value from its environment variable, if
there is one, so an existing docker-compose.yml keeps working until its values
are saved here.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# (group title, group help, [fields]). A field: key, env (the variable it falls
# back to), label, and optionally secret, choices, default, help.
SCHEMA = [
    ("ScreenScraper", "Developer credentials identify RetroManager to screenscraper.fr; the user account is yours, and gives a larger quota.", [
        {"key": "screenscraper_login", "env": "SCREENSCRAPER_LOGIN", "label": "Developer ID"},
        {"key": "screenscraper_password", "env": "SCREENSCRAPER_PASSWORD", "label": "Developer password", "secret": True},
        {"key": "screenscraper_debug_password", "env": "SCREENSCRAPER_DEBUG_PASSWORD", "label": "Developer debug password", "secret": True},
        {"key": "screenscraper_user", "env": "SCREENSCRAPER_USER", "label": "User name (optional)"},
        {"key": "screenscraper_user_password", "env": "SCREENSCRAPER_USER_PASSWORD", "label": "User password", "secret": True},
    ]),
    ("IGDB", "A Twitch application's credentials (dev.twitch.tv > Applications).", [
        {"key": "igdb_client_id", "env": "IGDB_CLIENT_ID", "label": "Client ID"},
        {"key": "igdb_client_secret", "env": "IGDB_CLIENT_SECRET", "label": "Client secret", "secret": True},
    ]),
    ("RetroAchievements", "retroachievements.org > Settings > Keys > Web API Key. The user is whose earned achievements are shown.", [
        {"key": "retroachievements_api_key", "env": "RETROACHIEVEMENTS_API_KEY", "label": "Web API key", "secret": True},
        {"key": "retroachievements_user", "env": "RETROACHIEVEMENTS_USER", "label": "User name"},
        {"key": "retroachievements_people", "env": "RETROACHIEVEMENTS_PEOPLE", "label": "Other people (name=user name, ...)"},
    ]),
    ("SteamGridDB", "steamgriddb.com > Preferences > API.", [
        {"key": "steamgriddb_api_key", "env": "STEAMGRIDDB_API_KEY", "label": "API key", "secret": True},
    ]),
    ("TheGamesDB", "thegamesdb.net: an API key is asked for on its forums. Each search and each game opened counts against the key's monthly allowance.", [
        {"key": "thegamesdb_api_key", "env": "THEGAMESDB_API_KEY", "label": "API key", "secret": True},
    ]),
    ("EmulationStation", "Play statuses and collections are written as EmulationStation custom collections (custom-<name>.cfg, in the collections folder of RetroManager's data folder), listing each ROM as the device that runs EmulationStation sees it.", [
        {"key": "es_roms_path", "env": "ES_ROMS_PATH", "label": "ROM folder on the device", "default": "/home/pi/RetroPie/roms"},
    ]),
    ("Playing in the browser", "Games are played with EmulatorJS. RetroManager fetches each part of it from this address the first time it's needed and keeps a copy in its data folder, so a system that has been played once plays again without the internet.", [
        {"key": "emulatorjs_url", "env": "EMULATORJS_URL", "label": "Where EmulatorJS is fetched from", "default": "https://cdn.emulatorjs.org/stable/data/"},
    ]),
    ("Housekeeping", "RetroManager's own data (settings, play statuses and collections, the ROM check's results) is backed up every night to the backups folder in its data folder.", [
        {"key": "rom_check_nightly", "env": "ROM_CHECK_NIGHTLY", "label": "Run the ROM check every night",
         "default": "on", "choices": [["on", "On (only new and changed files are looked at)"], ["off", "Off"]]},
    ]),
    ("Saves", "Where RetroArch keeps saves and save states. Usually in folders of their own (the saves and savestates folders), which is what RetroArch does on its own and what lets each person have their own. RetroPie, and RetroArch's \"write saves to the content directory\", keep them beside the games instead; then everyone shares them.", [
        {"key": "save_location", "env": "SAVE_LOCATION", "label": "Saves and save states are kept",
         "default": "folders", "choices": [["folders", "In the saves and savestates folders"], ["roms", "Beside the games, in the ROM folders (shared by everyone)"]]},
    ]),
    ("Appearance", "Each system's picture on the Console, Library and Bookcase pages. RetroManager draws a tile of its own for every system. The pictures in frontend/imgs/, where they're installed, are from Lilbud's Switch theme for EmulationStation (CC BY-NC-SA: credit, no commercial use, changes shared alike) and show the consoles' own logos. Anyone can choose the other for their own browser or phone in the Console's settings.", [
        {"key": "system_pictures", "env": "SYSTEM_PICTURES", "label": "System pictures",
         "default": "drawn", "choices": [["drawn", "RetroManager's drawn tiles"], ["theme", "The Switch theme's pictures, where a system has one"]]},
    ]),
    ("Matching and media", "", [
        {"key": "libretro_thumbnails", "env": "LIBRETRO_THUMBNAILS", "label": "libretro thumbnails in bulk and library scrapes",
         "default": "fallback", "choices": [["fallback", "When ScreenScraper has no image of that kind"],
                                            ["first", "Before ScreenScraper (saves its quota)"], ["off", "Never"]]},
        {"key": "gametdb", "env": "GAMETDB", "label": "Disc and cartridge pictures from GameTDB (GameCube, Wii, DS, 3DS, PS3), found by the ID in the ROM",
         "default": "on", "choices": [["on", "When nothing else has one"], ["off", "Never"]]},
        {"key": "launchbox", "env": "LAUNCHBOX", "label": "Pictures from the LaunchBox Games Database, cartridges and discs among them",
         "default": "off", "choices": [["on", "When nothing else has one (fetches its list of games, about 110 MB, once a month, and keeps an index of about 120 MB)"], ["off", "Never"]]},
        {"key": "hasheous", "env": "HASHEOUS", "label": "Recognise ROMs by checksum through hasheous.org",
         "default": "on", "choices": [["on", "On"], ["off", "Off (no checksums are sent)"]]},
    ]),
]

FIELDS: Dict[str, Dict] = {field["key"]: field for _, _, fields in SCHEMA for field in fields}


class SettingsStore:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "settings.json"
        self._lock = threading.Lock()
        try:
            saved = json.loads(self.path.read_text())
            self._saved: Dict[str, str] = {k: str(v) for k, v in saved.items() if k in FIELDS}
        except (OSError, ValueError):
            self._saved = {}

    def _source(self, key: str) -> str:
        if key in self._saved:
            return "settings"
        return "environment" if os.environ.get(FIELDS[key]["env"], "").strip() else "default"

    def get(self, key: str) -> str:
        """The setting's value: what was saved here, else its environment
        variable, else its default ("" for accounts and keys)."""
        field = FIELDS[key]
        with self._lock:
            value = self._saved.get(key)
        if value is None:
            value = os.environ.get(field["env"], "")
        value = value.strip()
        choices = [choice for choice, _ in field.get("choices") or []]
        if choices and value.lower() not in choices:
            return field["default"]
        if not value and not field.get("secret") and field.get("default") and key not in self._saved:
            return field["default"]
        return value.lower() if choices else value

    def update(self, values: Dict[str, Any]) -> List[str]:
        """Save the given settings (unknown keys are ignored; "" clears one).
        Returns the keys whose value changed."""
        changed = []
        with self._lock:
            for key, value in (values or {}).items():
                if key not in FIELDS or value is None:
                    continue
                value = str(value).strip()
                choices = [choice for choice, _ in FIELDS[key].get("choices") or []]
                if choices and value not in choices:
                    continue
                if self._saved.get(key) != value:
                    self._saved[key] = value
                    changed.append(key)
            if changed:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._saved, indent=2))
                try:
                    os.chmod(tmp, 0o600)  # it holds passwords and keys
                except OSError:
                    pass
                tmp.replace(self.path)
        return changed

    def describe(self) -> List[Dict]:
        """The settings for the Settings panel. Passwords and keys are never
        included: a secret only says whether it's set."""
        groups = []
        for title, help_text, fields in SCHEMA:
            described = []
            for field in fields:
                value = self.get(field["key"])
                item = {
                    "key": field["key"], "label": field["label"], "secret": bool(field.get("secret")),
                    "set": bool(value), "source": self._source(field["key"]) if value else None,
                    "env": field["env"],
                }
                if field.get("choices"):
                    item["choices"] = field["choices"]
                if not field.get("secret"):
                    item["value"] = value
                described.append(item)
            groups.append({"title": title, "help": help_text, "fields": described})
        return groups
