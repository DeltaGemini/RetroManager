"""
What every part of the backend shares: configuration, the Flask app, the
scanner, gamelist manager and scraping clients, and helpers the routes use.
The routes themselves are in backend/routes/.
"""

from flask import Flask, jsonify, request
import os
from urllib.parse import urlparse
import logging
from pathlib import Path
import mimetypes
from backend.scanner import SystemScanner
from backend.gamelist_manager import GamelistManager
from backend.folder_games import is_game_folder
from backend.scraper import ScreenscraperAPI
from backend.igdb_scraper import IGDBAPI
from backend.hasheous import HasheousAPI, HasheousError
from backend.libretro_thumbs import LibretroThumbnails
from backend.retroachievements import GameIdCache as RaGameIdCache
from backend.retroachievements import RetroAchievementsAPI, RetroAchievementsError
from backend.retroachievements import rom_hashes as ra_rom_hashes
from backend.rom_hashes import HashCache
from backend.steam import SteamAPI
from backend.steamgriddb import SteamGridDBAPI
from backend.gametdb import GameTDB
from backend.launchbox import LaunchBoxIndex
from backend.media_sources import MediaSources
from backend.thegamesdb import TheGamesDBAPI
from backend.systems import is_arcade, retroachievements_console_id
from backend.systems import set_bios_dir
from backend.media_index import strip_dot_slash
from backend.saves import SaveFinder
from backend.settings import SettingsStore
from backend.library_state import LibraryState
from backend.bulk_scrape import BulkMatcher, JeuCache
from backend.mix_jobs import MixProvenance

"""
RetroManager Backend API
Flask application providing REST API for EmulationStation metadata management
"""
mimetypes.add_type('application/manifest+json', '.webmanifest')


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
ROMS_BASE = os.environ.get("ROMS_PATH", "/roms")
MEDIA_BASE = os.environ.get("MEDIA_PATH", "/media")
# In-game saves and save states (mounted read-only; viewed, never changed)
SAVES_BASE = os.environ.get("SAVES_PATH", "/saves")
SAVESTATES_BASE = os.environ.get("SAVESTATES_PATH", "/savestates")
# BIOS files, for systems that need one to play in the browser (optional mount)
BIOS_BASE = Path(os.environ.get("BIOS_PATH", "/bios"))
# Per-person folders inside them
INBOX_BASE = os.environ.get("INBOX_PATH", "/inbox")


def _data_dir():
    """RetroManager's own files (library-scrape memory, moved duplicates): DATA_PATH,
    kept out of the ROM folders so they don't sync to other devices. Falls back to
    ROMS_PATH/.retromanager when DATA_PATH isn't mounted."""
    configured = Path(os.environ.get("DATA_PATH", "/data"))
    try:
        if configured.is_dir() and os.access(configured, os.W_OK):
            return configured
    except OSError:
        pass
    return Path(os.environ.get("ROMS_PATH", "/roms")) / ".retromanager"
DATA_DIR = _data_dir()
SAVE_BACKUP_BASE = Path(os.environ.get("SAVE_BACKUP_PATH", "/save-backups"))
# The people saves are kept apart for: none to begin with (one shared set, where
# RetroArch itself keeps them). People are added in the app (Tools > Profiles and
# login), which remembers them; this setting only names the ones to start with.
SAVE_PROFILES = [p.strip() for p in os.environ.get("SAVE_PROFILES", "").split(",") if p.strip()]
# Accounts, keys and scraping options are set in the app (Tools > Settings) and
# kept in DATA_PATH/settings.json; see backend/settings.py
set_bios_dir(BIOS_BASE)
settings = SettingsStore(DATA_DIR)
# Play status and collections (favourites are the gamelist's own <favorite>)
library_state = LibraryState(DATA_DIR)
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
app = Flask(__name__)
# No CORS: the pages are RetroManager's own and the phone app asks it directly, so no other
# site's page needs to reach it (and with login off, one that could would have the run of it).


@app.before_request
def _not_from_other_sites():
    """A request that would change something, sent by another site's page (a form, or a
    script) the browser was showing: refused. The browser says where a request came from
    (Sec-Fetch-Site, else Origin); what isn't a browser (the phone app, curl) says nothing."""
    if request.method in ('GET', 'HEAD', 'OPTIONS') or not request.path.startswith('/api/'):
        return None
    fetched_from = request.headers.get('Sec-Fetch-Site')
    if fetched_from:
        # (not 'same-site': that takes in another app on the same machine, on another port)
        allowed = fetched_from in ('same-origin', 'none')
    else:
        origin = request.headers.get('Origin')
        allowed = not origin or urlparse(origin).netloc == request.host
    if allowed:
        return None
    logger.warning(f"Refused {request.method} {request.path} from another site ({request.headers.get('Origin') or fetched_from})")
    return jsonify(success=False, error="Refused: that came from another site's page"), 403

# INFO by default: at DEBUG the HTTP library logs every request's address, and
# some sources take their key or password in the address
logging.basicConfig(level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO))
logger = logging.getLogger(__name__)
scanner = SystemScanner(ROMS_BASE, MEDIA_BASE)
# Which Mix pictures RetroManager generated itself (see backend/mix_jobs.py)
mix_provenance = MixProvenance(DATA_DIR)
scanner.generated_mix = mix_provenance.is_generated
gamelist_mgr = GamelistManager(MEDIA_BASE)
scraper = ScreenscraperAPI('', '')
igdb_scraper = IGDBAPI('', '')
hash_cache = HashCache(DATA_DIR)
hasheous = HasheousAPI()
ra_scraper = RetroAchievementsAPI('', DATA_DIR)
ra_game_ids = RaGameIdCache(DATA_DIR)
steam_scraper = SteamAPI()
steamgriddb_scraper = SteamGridDBAPI('')
thegamesdb_scraper = TheGamesDBAPI('', DATA_DIR)
libretro_thumbs = LibretroThumbnails()
gametdb = GameTDB()
launchbox_index = LaunchBoxIndex(DATA_DIR)
media_sources = MediaSources(DATA_DIR, MEDIA_BASE)


def apply_settings():
    """Give the scraping clients the accounts, keys and options from Settings.
    Called at start-up and whenever settings are saved."""
    value = settings.get
    scraper.dev_login = value('screenscraper_login')
    scraper.dev_password = value('screenscraper_password')
    scraper.dev_debug_password = value('screenscraper_debug_password')
    scraper.user = value('screenscraper_user')
    scraper.user_password = value('screenscraper_user_password')
    if (igdb_scraper.auth.client_id, igdb_scraper.auth.client_secret) != (value('igdb_client_id'), value('igdb_client_secret')):
        igdb_scraper.auth.client_id = value('igdb_client_id')
        igdb_scraper.auth.client_secret = value('igdb_client_secret')
        igdb_scraper.auth.invalidate()
    if (ra_scraper.api_key, ra_scraper.user) != (value('retroachievements_api_key'), value('retroachievements_user')):
        ra_scraper.api_key = value('retroachievements_api_key')
        ra_scraper.user = value('retroachievements_user')
        ra_scraper.forget_progress()
    steamgriddb_scraper.api_key = value('steamgriddb_api_key')
    thegamesdb_scraper.api_key = (value('thegamesdb_api_key') or '').strip()
    hasheous.enabled = value('hasheous') != 'off'
    libretro_thumbs.enabled = value('libretro_thumbnails') != 'off'
    gametdb.enabled = value('gametdb') != 'off'
    launchbox_index.enabled = value('launchbox') == 'on'
    if os.environ.get("RETROMANAGER_NO_BACKGROUND") != "1":
        launchbox_index.refresh_if_needed()  # (in the background; nothing if it's off or has its list)
apply_settings()


# Called with (system, old rom path, new rom path or None) when a game's file is
# renamed, replaced by another copy, or deleted
_game_moved_hooks = []


def game_moved(system_name, old_rom_path, new_rom_path=None):
    """Carry what's kept about a game (play status, collections, its ROM check
    record) over to its new file name, or drop it when the file is gone."""
    old = strip_dot_slash(old_rom_path)
    new = strip_dot_slash(new_rom_path) if new_rom_path else None
    if not old or old == new:
        return
    try:
        library_state.move_game(f"{system_name}/{old}", f"{system_name}/{new}" if new else None)
        for hook in _game_moved_hooks:
            hook(system_name, old, new)
    except Exception:
        logger.exception(f"Couldn't carry {system_name}/{old} over to its new name")


def _rom_system_folders():
    try:
        return {p.name for p in Path(ROMS_BASE).iterdir() if p.is_dir()}
    except OSError:
        return set()


def _hasheous_lookup(system_name, rom_file):
    """What Hasheous knows about a ROM file ({'name', 'platform', 'ids'}), or None.
    Never raises: a lookup that fails is the same as an unknown file."""
    try:
        rom_file = Path(rom_file)
        if not hasheous.enabled or not rom_file.is_file():
            return None
        # Arcade sets are listed as the .zip itself, other systems as the ROM inside
        return hasheous.lookup(hash_cache.hashes(rom_file, unzip=not is_arcade(system_name)))
    except (HasheousError, OSError) as e:
        logger.warning(f"Hasheous lookup failed for {rom_file}: {e}")
        return None


def ra_people():
    """Whose RetroAchievements progress can be shown: [{'name', 'user'}], the
    main user first, then "name=user name" pairs from Settings (a save
    profile's name beside its owner's account, say)."""
    people = []
    if ra_scraper.user:
        people.append({'name': ra_scraper.user, 'user': ra_scraper.user})
    for pair in settings.get('retroachievements_people').split(','):
        name, _, user = pair.partition('=')
        name, user = name.strip(), user.strip()
        if name and user and not any(p['name'].lower() == name.lower() for p in people):
            people.append({'name': name, 'user': user})
    return people


def ra_user_for(name):
    """The RetroAchievements user name for a person picked in the app (the main
    user for anyone not listed)."""
    wanted = (name or '').strip().lower()
    return next((p['user'] for p in ra_people() if p['name'].lower() == wanted), ra_scraper.user)


def _hasheous_lookup_raw(hashes):
    """Hasheous's answer for a ROM's checksums, or None when it's switched off
    or doesn't know the file. Raises HasheousError when it can't be reached."""
    return hasheous.lookup(hashes) if hasheous.enabled else None


def _ra_identify(system_name, rom_file, known=None):
    """The RetroAchievements game for a ROM file (a game-list entry), or None:
    by RetroAchievements' own checksums, else by the ID Hasheous has for it.
    Never raises."""
    if not ra_scraper.configured:
        return None
    try:
        rom_file = Path(rom_file)
        if rom_file.is_file() and retroachievements_console_id(system_name):
            game = ra_scraper.identify(system_name, ra_rom_hashes(system_name, rom_file, hash_cache))
            if game:
                return game
        ra_id = ((known or {}).get('ids') or {}).get('retroachievements')
        if ra_id:
            info = ra_scraper.get_game_info(ra_id)
            return {'id': info.get('ID') or ra_id, 'title': info.get('Title') or info.get('GameTitle') or '',
                    'console': info.get('ConsoleName') or '', 'icon': info.get('ImageIcon') or ''}
    except (RetroAchievementsError, OSError) as e:
        logger.warning(f"RetroAchievements lookup failed for {rom_file}: {e}")
    return None


def _identify_by_hash(system_name, rom_file):
    """For BulkMatcher: who a ROM is, going by its checksum."""
    known = _hasheous_lookup(system_name, rom_file)
    ra_game = _ra_identify(system_name, rom_file, known)
    return {
        'name': (known or {}).get('name') or '',
        'screenscraper_id': ((known or {}).get('ids') or {}).get('screenscraper'),
        'other': ra_scraper.summarize_search_result(ra_game) if ra_game else None,
    }
jeu_cache = JeuCache()
bulk_matcher = BulkMatcher(scraper, jeu_cache, _identify_by_hash)
def saves_beside_roms():
    """Whether RetroArch keeps saves and save states beside the games here, not
    in the saves and savestates folders (Settings > Saves). Then they're everyone's."""
    return settings.get('save_location') == 'roms'


save_finder = SaveFinder({"saves": SAVES_BASE, "savestates": SAVESTATES_BASE}, SAVE_PROFILES, _rom_system_folders,
                         roms_root=ROMS_BASE, beside_roms=saves_beside_roms)
scanner.saves_beside_roms = saves_beside_roms


# -----------------------------------------------------------------------------
# Scan panel actions. Each gamelist change makes a dated backup first.
# -----------------------------------------------------------------------------
def _system_path_or_none(system_name):
    """The system's ROM folder, or None if the name isn't a real system folder."""
    if not system_name or '/' in system_name or '\\' in system_name or system_name.startswith('.'):
        return None
    path = Path(ROMS_BASE) / system_name
    return path if path.is_dir() else None


def _rom_exists(system_path, rom_path):
    rom_rel = strip_dot_slash(rom_path)
    full = (system_path / rom_rel).resolve()
    return (rom_rel and str(full).startswith(str(system_path.resolve()) + os.sep)
            and (full.is_file() or is_game_folder(full)))


def _bulk_result(changed, backup):
    return jsonify(success=True, changed=changed, backup=backup)
# Fields a save writes to gamelist.xml. Media folder fields (box2d, wheel, ...)
# are display-only; only image, thumbnail and video go in the XML. favorite,
# playcount and lastplayed are passed through so a save doesn't drop them.
SAVEABLE_FIELDS = (
    'path', 'name', 'desc', 'genre', 'developer', 'publisher', 'releasedate',
    'players', 'rating', 'image', 'thumbnail', 'video', 'favorite', 'playcount', 'lastplayed',
)


def _saveable_fields(data):
    return {k: data[k] for k in SAVEABLE_FIELDS if data.get(k) is not None}
_stats_cache = {"value": None, "time": 0.0}


# -----------------------------------------------------------------------------
# Shelf view
# -----------------------------------------------------------------------------
_shelf_cache = {"value": None, "time": 0.0}


def _request_json():
    """Parse the JSON body even when the Content-Type header is missing."""
    return request.get_json(force=True, silent=True) or {}


def _request_rom_file(data):
    """The ROM file a search is for (body: system_name, rom_path), or None when
    it isn't given or isn't a file in that system's folder."""
    system_path = _system_path_or_none(data.get("system_name"))
    rom_path = strip_dot_slash(data.get("rom_path"))
    if not system_path or not rom_path or not _rom_exists(system_path, rom_path):
        return None
    rom_file = system_path / rom_path
    return rom_file if rom_file.is_file() else None


def _invalidate_caches():
    _stats_cache["value"] = None
    _shelf_cache["value"] = None
