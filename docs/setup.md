# Setting up RetroManager

Where the library goes, the settings, running and updating it, how the folders are laid out, and what to do when something is wrong. The [README](../README.md) has the quick start.

## Setup

### 1. Paths

With nothing set, the library is `RetroGames/` beside `docker-compose.yml`, made the first time it starts, with `roms/`, `media/` and the rest inside. That's all a new library needs.

To use folders you already have, copy `.env.example` to `.env` and set `RETRO_DIR` to the folder that holds `roms/`, `media/` and the rest on your machine. This is the one thing the first-run page can't do for you: which folders of the machine a container may see is decided where it's started. `docker-compose.yml` mounts everything from there:

```yaml
volumes:
  - ${RETRO_DIR:-./RetroGames}/roms:/roms
  - ${RETRO_DIR:-./RetroGames}/media:/media
```

Both mounts must be writable: the app writes `gamelist.xml`, backups, uploads and downloaded media.

**Folders in different places.** A folder that isn't inside `RETRO_DIR` (another share on a NAS, a different disk) has a setting of its own in `.env`, used instead of the one inside `RETRO_DIR`:

| In `.env` | Instead of | Holds |
|---|---|---|
| `ROMS_DIR` | `RETRO_DIR/roms` | The games, a folder per system, with each system's `gamelist.xml` |
| `MEDIA_DIR` | `RETRO_DIR/media` | Pictures, videos and manuals |
| `SAVES_DIR` | `RETRO_DIR/saves` | In-game saves, a folder per person |
| `SAVESTATES_DIR` | `RETRO_DIR/savestates` | Save states, a folder per person |
| `BIOS_DIR` | `RETRO_DIR/BIOS` | BIOS files (optional) |
| `INBOX_DIR` | `RETRO_DIR/inbox` | New games waiting to be added |
| `RETROMANAGER_DIR` | `RETRO_DIR/retromanager` | RetroManager's own files and settings |
| `SAVE_BACKUPS_DIR` | `RETRO_DIR/save-backups` | Save backups |

With every one of them set, `RETRO_DIR` isn't needed (set it to anything). `PORT` changes the port from 5000. After changing `.env`, run `docker compose up -d` again.

The saves mounts are optional. They're writable so [sync conflicts](library.md#saves-tool) can be resolved (add `:ro` to only view saves), and `save-backups` holds zipped backups and the versions set aside when resolving conflicts:

```yaml
  - ${RETRO_DIR}/saves:/saves
  - ${RETRO_DIR}/savestates:/savestates
  - ${RETRO_DIR}/save-backups:/save-backups
  - ${RETRO_DIR}/inbox:/inbox
  - ${RETRO_DIR}/retromanager:/data
```

Syncthing shares all of `roms`, `media`, `saves` and `savestates`, so RetroManager keeps its own files in `retromanager`, `inbox` and `save-backups`, which aren't synced. Gamelist backups (`gamelist_<date>.xml`) and `media/<system>/_orphaned/` do sit in synced folders.

### 2. Configuration

All settings are environment variables in `docker-compose.yml`:

| Variable | Default | Purpose |
|---|---|---|
| `ROMS_PATH` | `/roms` | ROM root inside the container |
| `MEDIA_PATH` | `/media` | Media root inside the container |
| `SAVES_PATH` | `/saves` | In-game saves |
| `SAVESTATES_PATH` | `/savestates` | Save states |
| `SAVE_BACKUP_PATH` | `/save-backups` | Zipped save backups and set-aside conflict versions |
| `DATA_PATH` | `/data` | RetroManager's own files: library-scrape memory, duplicates moved aside. Keep it outside synced folders (falls back to `roms/.retromanager`) |
| `INBOX_PATH` | `/inbox` | Folder for new games to add; uploads are staged in its hidden `.uploads/` |
| `SAVE_PROFILES` | *(none)* | People to start with, each with a folder inside the two save folders, e.g. `alice,bob`. Usually left out: saves are shared until people are added in the app. See [PROFILES.md](profiles.md) |
| `NAME_STYLE_SERIES` | *(empty)* | Extra series names that get a colon after them in the Name style fix, comma separated |
| `MIX_WORKERS` | `2` | How many Mix previews are drawn at once (see [Generating Mix pictures](library.md#generating-mix-pictures)) |
| `MIX_STAGING_HOURS` | `24` | How long Mix previews nobody committed are kept |

| `LOG_LEVEL` | `INFO` | How much the container logs (`DEBUG` also logs every request to a scraping source, addresses included) |

#### Accounts and keys

The scraping sources' accounts and keys aren't in `docker-compose.yml`. Set them in the app, in **🧰 Tools › Settings**:

- **ScreenScraper**: developer ID, password and debug password (they identify the software), and optionally your own user account. A user account is recommended: without it, requests count against the anonymous quota, and ScreenScraper shuts anonymous access off when its servers are busy.
- **IGDB**: a Twitch application's client ID and secret.
- **RetroAchievements**: your web API key, and the user whose earned achievements are shown.
- **SteamGridDB**: your API key.
- **TheGamesDB**: your API key (asked for on its forums).
- **Matching and media**: when libretro thumbnails are used in bulk and library scrapes, and whether ROMs are recognised by checksum through hasheous.org.

Settings take effect as soon as you save. They're kept in `settings.json` in `DATA_PATH` (`RetroGames/retromanager/`), readable only by the container's user. Saved passwords and keys are never sent back to the browser: the panel only says whether one is saved, and lets you replace or remove it. A source with nothing set is greyed out in the Scrape popup.

The old environment variables (`SCREENSCRAPER_LOGIN`, `IGDB_CLIENT_ID`, `RETROACHIEVEMENTS_API_KEY`...) still work as a starting value for anything not yet saved in Settings, so an older `docker-compose.yml` keeps working.

### 3. Build and run

```bash
docker compose up -d --build
```

Open `http://<NAS IP>:5000`.

### 4. Check it's up

```bash
curl http://localhost:5000/api/health
```

```json
{
  "status": "healthy",
  "roms_path": "/roms",
  "media_path": "/media",
  "roms_accessible": true,
  "media_accessible": true
}
```

### Updating

Code is copied into the image at build time, so rebuild after any change:

```bash
docker compose up -d --build
```

## Folder structure

### ROMs

```
roms/
├── snes/
│   ├── gamelist.xml
│   └── Super Mario World (USA).sfc
└── psx/
    ├── gamelist.xml
    └── Final Fantasy VII (Disc 1).cue
```

Recognised ROM extensions are listed in `ROM_EXTENSIONS` in `backend/scanner.py`; `.zip` and `.7z` aren't included. A disc game is its `.cue`: the files a `.cue` names (its track `.bin` files), and any smaller `.cue` covering only some of them, count as parts of that one game. Likewise the discs an `.m3u` playlist lists are parts of the playlist's game.

**PC systems** (`dos`, `pc`, `winxp`, `scummvm`…, see `backend/folder_games.py`): each top-level folder with programs in it is one game, not every `.exe` inside. The game's launch file is the one its gamelist entry points at, or else the likeliest program: named like the folder, never setup, install, uninstall, DOSBox or config tools. Change it under **Launch file** in the game's details. The game is named after its folder. Folders without programs (a folder of disc images) keep each file as its own game.

**PS3**: a disc game is a folder (`PS3_GAME/`, `PS3_DISC.SFB`), not a file. Name the folder `<game>.ps3` and it is one game: RetroManager lists the folder as the ROM (`./Catherine (Europe).ps3`) and never looks inside, so its data files aren't taken for ROMs or saves, and media is named after the folder. Batocera and ES-DE use the same name, and RPCS3 opens the folder directly. A PS3 folder without the `.ps3` name is ignored until **Scan › Rename to .ps3** renames it. `.iso` games are ordinary files. Deleting a game from RetroManager never deletes a game folder.

### Media

```
media/
└── <media system folder>/
    └── <type>/
        └── <ROM file name without extension>.<ext>
```

Example: the box art for `roms/snes/Super Mario World (USA).sfc` is `media/Super Nintendo/box2d/Super Mario World (USA).png`.

- **Type folders the scanner reads**: `box2d`, `box3d`, `boxside`, `support` (the cartridge or disc), `wheel`, `screenshot`, `screenshottitle`, `fanart`, `posters`, `images`, `thumbnail`/`thumbnails`, `mix`, `manuals`, `videos`.
- **Matching**: files match on the ROM file name, ignoring case, or failing that on the same title with the `(region)`/`[version]` tags removed. Nothing looser is accepted, so a game with no matching file shows a placeholder rather than another game's art.
- **Media system folder**: the media folder doesn't need the same name as the ROM folder. The scanner resolves it in this order:
  1. Built-in aliases: `psx` → `Playstation`, `ps2` → `Playstation 2`, `ps3` → `Playstation 3`, `gc` → `Gamecube`, `snes` → `Super Nintendo`, `nds` → `Nintendo DS`, `n64` → `Nintendo 64`, `nsw` → `Nintendo Switch`, `pokemini` → `Pokémon mini`
  2. Exact or case-insensitive name
  3. Same name ignoring punctuation and spaces
  4. Initials (`gba` → `Game Boy Advance`)
  5. Substring
  6. Otherwise the ROM folder name itself

### gamelist.xml

Standard EmulationStation format. Writes are atomic, so a crash can't leave a half-written file.

```xml
<gameList>
  <game>
    <path>./Super Mario World (USA).sfc</path>
    <name>Super Mario World</name>
    <desc>...</desc>
    <image>../../media/Super Nintendo/images/Super Mario World (USA).png</image>
    <thumbnail>../../media/Super Nintendo/screenshottitle/Super Mario World (USA).png</thumbnail>
    <video>../../media/Super Nintendo/videos/Super Mario World (USA).mp4</video>
    <developer>Nintendo</developer>
    <publisher>Nintendo</publisher>
    <genre>Platform</genre>
    <releasedate>19901121T000000</releasedate>
    <players>1-2</players>
    <rating>0.85</rating>
  </game>
</gameList>
```

Release dates use `YYYYMMDDT000000`. Ratings are `0`–`1`.

EmulationStation only shows the media set in `<image>`, `<thumbnail>` and `<video>`; files in the media folders aren't enough on their own. RetroManager writes these as `../../media/<media system folder>/<type>/<file>` (`XML_MEDIA_PREFIX` in `backend/media_index.py`). EmulationStation reads them relative to the system's ROM folder, so from `roms/<system>/` they reach the `media/` folder beside `roms/`: `RetroGames/media` on the NAS (the one RetroManager mounts) and `~/RetroPie/media` on the Pi. Older `../media/...` paths are still read. `roms/media/` isn't used.

When they're empty, RetroManager fills them from the game's media in this order (`LINK_PREFERENCES` in `backend/media_index.py`):

| Field | Folders, first match wins |
|---|---|
| `image` | `images`, `mix`, `box2d`, `screenshot` |
| `thumbnail` | `screenshottitle`, `screenshot`, `box2d`, `wheel` |
| `video` | `videos` |

## Troubleshooting

| Problem | Check |
|---|---|
| Container won't start | `docker compose logs retromanager`; confirm the host paths in `docker-compose.yml` exist |
| Page won't load | `curl http://localhost:5000/api/health`; check nothing else uses port 5000 (change the left side of `"5000:5000"` if so) |
| No systems | `roms_accessible` in `/api/health`; the ROM mount must contain one folder per system |
| Changes not saving | Write permission on the ROM folder; errors in the container log |
| Media not showing in RetroManager | The file name must match the ROM file name (or its title without tags), in a type folder listed above. `/api/debug/media-list/...` shows what the backend sees. |
| Media not showing in EmulationStation | Run **Scan** and use **Link media**; the gamelist must reference the file |
| Media in the wrong system folder | See how the media system folder is resolved above; rename the folder or add an alias in `_resolve_media_system` in `backend/scanner.py` |
| Scraper errors | See [SCRAPING.md](scraping.md#troubleshooting) |
