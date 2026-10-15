# Developing and releasing RetroManager

How it is built, where things are in the code, and how a release is made.

## Stack

| Part | Details |
|---|---|
| Backend | Python 3.11, Flask, lxml, requests (`backend/`) |
| Frontend | React 18 + Babel from a CDN, a single `frontend/index.html`, no build step |
| Storage | The filesystem: `gamelist.xml` in each ROM folder, media in the media mount. No database. |
| Deployment | One container, `docker compose`, port 5000 |

The frontend loads React and Babel from unpkg/jsDelivr, so the browser viewing the app needs internet access.

## Project layout

```
RetroManager/
├── backend/
│   ├── app.py               # Entry point: imports the route modules (gunicorn backend.app:app)
│   ├── core.py              # Configuration, the Flask app, shared clients and helpers
│   ├── routes/              # The API routes, one file per area (systems, games, scraping, saves...)
│   ├── scanner.py           # System/ROM discovery, media matching, scans
│   ├── gamelist_manager.py  # gamelist.xml read/write (atomic writes)
│   ├── models.py            # Game, System, MediaAsset, ScanResult
│   ├── scraper.py           # ScreenScraper client
│   ├── igdb_scraper.py      # IGDB client (Twitch OAuth)
│   ├── retroachievements.py # RetroAchievements client and its ROM checksums
│   ├── steam.py             # Steam store client (PC games)
│   ├── steamgriddb.py       # SteamGridDB client (artwork)
│   ├── thegamesdb.py        # TheGamesDB client (metadata and artwork)
│   ├── libretro_thumbs.py   # libretro thumbnails (artwork by ROM name)
│   ├── hasheous.py          # Hasheous: ROM checksum -> IDs on the other sources
│   ├── rom_hashes.py        # ROM checksums, remembered in DATA_PATH
│   ├── settings.py          # Accounts, keys and options set in Tools > Settings
│   ├── rom_index.py         # The ROM check: a checksum index of the library
│   ├── library_state.py     # Play status and collections
│   ├── maintenance.py       # Nightly housekeeping: data backups, the ROM check
│   ├── mix_generator.py     # Draws a Mix picture from a game's other media, to a template
│   ├── mix_jobs.py          # Mix inventory, previews in the background, commit, what was generated
│   ├── mix_templates/       # Mix layouts as JSON (classic.json), and each system's default
│   └── requirements.txt
├── frontend/
│   ├── index.html           # The library page: styles, and the list of script files it loads
│   ├── src/library/         # The library page's components (JSX), one file per area
│   ├── src/bookcase/        # The Bookcase page's components (shelf.html loads them)
│   ├── timeline.html, stats.html, import.html, play.html   # The other pages, each in one file
│   ├── src/common/          # The game list and the Game Details panel (and its editing) every page shares
│   ├── common/              # Shared by every page: header, each system's maker, kind and generation, series detection
│   ├── imgs/                # System artwork shown in the sidebar (from an EmulationStation theme: not for passing on)
│   ├── tiles/               # A drawn tile per system, used where imgs/ has no picture (tools/make_system_tiles.py)
│   └── favicon.ico
├── android/                 # The phone app: the Console page as a launcher for the phone's RetroArch (./build.sh)
├── homepage-widget/         # Dashboard widget experiments (see its README)
├── tools/build_frontend.js  # Run by the Dockerfile: compiles the pages and bundles React
├── tools/make_system_tiles.py  # Draws frontend/tiles/
├── tools/make_logo.py       # Draws frontend/open/retromanager-logo.svg
├── tools/make_icon.py       # Draws the app's icon and the tab's (frontend/icons/, favicon.ico)
├── tests/                   # pytest suite, on a throwaway library (no network): python -m pytest tests
├── Dockerfile
├── docker-compose.yml
├── dev-ssh.ps1              # Run a docker compose command on the Pi over SSH
├── test_igdb.py             # Manual IGDB smoke test (run inside the container)
├── SCRAPING.md
└── PROFILES.md              # Profiles: what they are, and setting RetroArch up for them
```

`frontend/scraperComponents.jsx` and `frontend/index 2.html` are old copies and aren't loaded by the app.

### System pictures, and a copy for others

Each system's picture is asked for as `/imgs/<folder>.jpg`. RetroManager has a tile of its own for every system in `frontend/tiles/`: a colour for its maker, a plain drawing of the kind of machine, its name and year, drawn by `tools/make_system_tiles.py` from shapes alone. **Those are what it shows**, by the folder's name, or the system that name is another for, or a plain "Games" one.

`frontend/imgs/` can also hold a picture per system from Lilbud's Switch-Light theme for EmulationStation. They are an optional extra under another licence (**CC BY-NC-SA**: credit, no commercial use, changed copies shared alike) and show the consoles' own logos; `frontend/imgs/README.md` has the credit and terms. **Tools › Settings › Appearance › System pictures** makes them the ones shown (a system the theme has no picture for keeps its tile), and anyone can choose either kind for their own browser or phone under **⚙ Console settings › System tiles show**, which is only there when the pictures are installed. A copy of RetroManager without `frontend/imgs/*.jpg` simply shows tiles throughout, and `SYSTEM_TILES=1` allows nothing else.

The Switch colour themes' background works that way too: the photograph this installation has isn't passed on (its source isn't recorded), and a copy without it shows a night sky drawn by `tools/make_background.py` (`frontend/open/background.svg`). The header's logo works the same way: the one in the Switch themes (lettered in a Sega logo font) gives way to `frontend/open/retromanager-logo.svg`, the name in blocks on a grid, drawn by `tools/make_logo.py` with no font, where the other isn't there or `OPEN_ARTWORK=1` is set. (The app's icon and the browser tab's are RetroManager's own already: a cartridge with RM on its label, drawn by `tools/make_icon.py`, which also makes `frontend/icons/icon-*.png` and `frontend/favicon.ico` from it.) To add or change a tile, edit `SYSTEMS` in the script and run it again.

### Making a release

`tools/export_public.sh <folder>` makes the copy that's given to others in another checkout (the public repository): everything that's in git here and nothing that isn't, plus the Android app as last built. Look over `git status` and `git diff` there, commit, and tag it (`v1.2.3`): the tag starts `.github/workflows/release.yml`, which builds the image for PCs and 64-bit Raspberry Pis, publishes it to `ghcr.io`, and makes a GitHub release with the app attached. The app is built and signed beforehand with `android/build.sh`, never in the workflow: its key stays with whoever makes the releases.

### Deploying to the Pi from Windows

`dev-ssh.ps1` runs a command in the project folder on the Pi. Copy `dev-ssh.example.ps1` to `dev-ssh.ps1` and put your host, port and folder in it (it isn't kept in git):

```powershell
.\dev-ssh.ps1 "docker compose up -d --build"
.\dev-ssh.ps1 "docker compose logs -f --tail 100"
```

## Notes

- **Local network only**: there's no authentication, CORS is open, and debug routes are exposed, so anyone on the network can use the app, including changing (but not reading) the keys in Settings. Don't publish the port to the internet.
- **`/api/stats` is cached**: it's recounted after any change made through RetroManager, and at least every 10 minutes (`STATS_MAX_AGE` in `backend/app.py`) to catch changes made directly on the NAS.
- **Logging**: set to `DEBUG`, so `docker compose logs` is verbose.
