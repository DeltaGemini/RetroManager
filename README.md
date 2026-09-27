# RetroManager

A self-hosted web app for managing EmulationStation `gamelist.xml` metadata and media on a NAS. It runs as a single Docker container on the local network and has no login.

## Features

- **System discovery**: every folder under the ROMs mount is treated as a system. Nothing is hard-coded.
- **Missing metadata**: ROMs without a `gamelist.xml` entry are flagged per system and in the game list.
- **Metadata editing**: name, description, developer, publisher, genre, release date, players and rating.
- **Add games**: a wizard at `/import` for uploading games from a phone or PC (resumable), or adding what you've copied to the inbox folder: it groups the files, detects the system, identifies the game and files it in. See [Adding games](#adding-games).
- **Delete games**: removes the gamelist entry, and optionally the ROM file and its media (typing the name confirms).
- **Scan**: finds problems and offers a fix for each: multi-disc games without an `.m3u`, duplicate copies, cut-off or badly styled names, entries pointing at a mistyped ROM name (relink), media not linked in the gamelist, ROMs without an entry, entries without a ROM, and unused media. See [Scan](#scan).
- **One header on every page**: RetroManager, then **Library · Bookcase · Timeline**, then library-scrape progress, **➕ Add games**, **🧰 Tools** and the theme. The page's own controls sit in the row below it. Tools: [Library health](#library-health), [Library scrape](#library-scrape), [Missing media](#missing-media), [Play history](#play-history), [Saves](#saves-tool) and [Gamelist backups](#gamelist-backups).
- **Gamelist backups**: every change backs up `gamelist.xml` first; see what a backup would change and restore it.
- **Saves**: a game's saves and states per person, Syncthing conflict resolution, and zipped backups.
- **PC games**: DOS/Windows game folders count as one game each, with a choice of launch program.
- **Scraping**: search ScreenScraper or IGDB, compare fields side by side, import selected fields and download artwork, one game at a time or in bulk. See [SCRAPING.md](SCRAPING.md).
- **Bookcase**: the collection as a bookcase at `/shelf`, one shelf per system. See [Bookcase](#bookcase).
- **Timeline**: every game on one timeline at `/timeline`, filtered by system or series. See [Timeline](#timeline).
- **Dashboard stats**: `/api/stats` feeds a Homepage dashboard tile. See [homepage-widget/README.md](homepage-widget/README.md).

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
│   ├── app.py               # Flask app and every API route
│   ├── scanner.py           # System/ROM discovery, media matching, scans
│   ├── gamelist_manager.py  # gamelist.xml read/write (atomic writes)
│   ├── models.py            # Game, System, MediaAsset, ScanResult
│   ├── scraper.py           # ScreenScraper client
│   ├── igdb_scraper.py      # IGDB client (Twitch OAuth)
│   └── requirements.txt
├── frontend/
│   ├── index.html           # Library page
│   ├── shelf.html           # Bookcase
│   ├── timeline.html        # Timeline
│   ├── import.html          # Add games wizard
│   └── common/              # Shared header
├── homepage-widget/         # Homepage dashboard tile setup
├── Dockerfile
├── docker-compose.yml
├── .env.example             # Copy to .env: your paths and API keys
├── test_igdb.py             # Manual IGDB smoke test (run inside the container)
└── SCRAPING.md
```

## Setup

### 1. Paths and keys

Copy `.env.example` to `.env` and fill it in. `.env` is ignored by git, so your paths and keys stay out of the repository.

`RETRO_DIR` is the folder holding your library, in the EmulationStation/RetroPie layout:

```
RetroGames/            <- RETRO_DIR
├── roms/              # one folder per system, each with its gamelist.xml
├── media/             # pictures, videos and manuals (see Folder structure)
├── saves/             # optional: in-game saves
└── savestates/        # optional: save states
```

RetroManager also creates three folders of its own there: `inbox/` (new games to add), `retromanager/` (its own files: library-scrape memory, duplicates moved aside, picture thumbnails) and `save-backups/`. If you sync your library to other devices (Syncthing, rsync...), leave these three out of the sync.

`roms` and `media` must be writable: the app writes `gamelist.xml`, backups, uploads and downloaded media. The saves folders are writable so [sync conflicts](#saves-tool) can be resolved; add `:ro` to their lines in `docker-compose.yml` to only view them.

### 2. Configuration

Set in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `RETRO_DIR` | *(required)* | Your library folder (above) |
| `RETROMANAGER_PORT` | `5000` | Port to open RetroManager on |
| `SAVE_PROFILES` | *(empty)* | Per-person folders inside `saves/` and `savestates/`, comma separated (`saves/<person>/<system>/`). Leave empty if saves aren't split by person |
| `SCREENSCRAPER_LOGIN` | *(empty)* | ScreenScraper developer ID (`devid`) |
| `SCREENSCRAPER_PASSWORD` | *(empty)* | ScreenScraper developer password |
| `SCREENSCRAPER_DEBUG_PASSWORD` | *(empty)* | ScreenScraper developer debug password (optional) |
| `SCREENSCRAPER_USER` | *(empty)* | Your ScreenScraper user account (optional, see below) |
| `SCREENSCRAPER_USER_PASSWORD` | *(empty)* | Password for that account |
| `IGDB_CLIENT_ID` | *(empty)* | Twitch application client ID |
| `IGDB_CLIENT_SECRET` | *(empty)* | Twitch application client secret |
| `NAME_STYLE_SERIES` | *(empty)* | Extra series names that get a colon after them in the Name style fix, comma separated |

Everything except scraping works without the API keys. To scrape:

- **ScreenScraper** needs developer credentials, which each app requests for itself on the [screenscraper.fr](https://www.screenscraper.fr/) forum. A ScreenScraper **user** account on top is optional but recommended: requests then count against your own quota, and keep working when ScreenScraper shuts anonymous access off at busy times.
- **IGDB** needs a free Twitch application: create one at [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps) and copy its client ID and secret.

The folders inside the container (`ROMS_PATH=/roms`, `MEDIA_PATH=/media`, `SAVES_PATH`, `SAVESTATES_PATH`, `SAVE_BACKUP_PATH`, `INBOX_PATH`, `DATA_PATH`, `THUMB_DIR`) are set in `docker-compose.yml` and don't normally need changing.

### 3. Build and run

```bash
docker compose up -d --build
```

Open `http://<server IP>:5000`.

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

### Media

```
media/
└── <media system folder>/
    └── <type>/
        └── <ROM file name without extension>.<ext>
```

Example: the box art for `roms/snes/Super Mario World (USA).sfc` is `media/Super Nintendo/box2d/Super Mario World (USA).png`.

- **Type folders the scanner reads**: `box2d`, `box3d`, `wheel`, `screenshot`, `screenshottitle`, `fanart`, `posters`, `images`, `thumbnail`/`thumbnails`, `mix`, `manuals`, `videos`.
- **Matching**: files match on the ROM file name, ignoring case, or failing that on the same title with the `(region)`/`[version]` tags removed. Nothing looser is accepted, so a game with no matching file shows a placeholder rather than another game's art.
- **Media system folder**: the media folder doesn't need the same name as the ROM folder. The scanner resolves it in this order:
  1. Built-in aliases: `psx` → `Playstation`, `ps2` → `Playstation 2`, `gc` → `Gamecube`, `snes` → `Super Nintendo`, `nds` → `Nintendo DS`, `n64` → `Nintendo 64`, `nsw` → `Nintendo Switch`, `pokemini` → `Pokémon mini`
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

EmulationStation only shows the media set in `<image>`, `<thumbnail>` and `<video>`; files in the media folders aren't enough on their own. RetroManager writes these as `../../media/<media system folder>/<type>/<file>` (`XML_MEDIA_PREFIX` in `backend/media_index.py`). EmulationStation reads them relative to the system's ROM folder, so from `roms/<system>/` they reach the `media/` folder beside `roms/`: the same one RetroManager mounts, and `~/RetroPie/media` on a RetroPie. Older `../media/...` paths are still read.

When they're empty, RetroManager fills them from the game's media in this order (`LINK_PREFERENCES` in `backend/media_index.py`):

| Field | Folders, first match wins |
|---|---|
| `image` | `images`, `mix`, `box2d`, `screenshot` |
| `thumbnail` | `screenshottitle`, `screenshot`, `box2d`, `wheel` |
| `video` | `videos` |

## Using it

1. Pick a system in the left sidebar. The count shows ROMs, and systems with missing metadata are highlighted. The header shows library totals and when this browser last scanned the system.
2. Pick a game. Games without a gamelist entry show a **Missing Metadata** badge. Region and version tags such as `(USA) (Rev 1)` are shown under the title.
3. Edit fields, or click **Scrape** to pull metadata and artwork from ScreenScraper or IGDB (see [SCRAPING.md](SCRAPING.md)).
4. Click **Save** to write `gamelist.xml`. Scraped fields aren't saved until you do this. **Preview the gamelist.xml entry** (under XML Metadata) shows exactly what Save writes.

Each game card shows the game's screenshot (or its title screen) behind the name. The **☀️ Light / 🌙 Dark** button in the header switches theme; the choice is remembered in each browser.

**Systems** (left): the search box finds systems and also games in every system (by name, developer or genre; click one to open it). **Filters** narrows the list by maker (Nintendo, Sega, Sony, Atari, computers) and type (consoles, handhelds, computers, arcade), to systems missing metadata, or shows empty systems. Sort by name, most games, most missing metadata, or maker (grouped).

**Games** (middle): the search box matches name, file, description, genre, developer, publisher and series. **Filters** opens a panel: show only (missing metadata, ROM missing, no image, no description, favourites), series, genre, decade, region (from the file name's tags), missing media, players, minimum rating, developer and publisher. Within a filter any ticked option matches; different filters must all match. Filters in use show as chips under the search box; click one to remove it. Series, genre, developer and publisher filters clear when you change system; the rest stay. Sort by name, oldest or newest first, rating, developer, series or file name (remembered in the browser).

| Key | Does |
|---|---|
| `↑` `↓` | Previous / next game in the list (also from the search box) |
| `/` | Jump to the search box (`Esc` leaves it) |
| `Ctrl`+`S` / `⌘`+`S` | Save the open game |

**Delete** removes only the gamelist entry by default. You can also tick the ROM file and its media (files named exactly after the ROM); deleting files asks you to type the game's name first.

If you switch game or system with unsaved edits, RetroManager asks whether to save, discard or keep editing.

**Auto-fill** (next to XML Metadata) fills an empty Image, Thumbnail or Video from the game's media files. Applying scraped metadata does the same.

**+** on a media tile picks a file to add; **Save** uploads it into the media folder named after the ROM (like scraped media, replacing that game's file in another format) and links it where the XML fields used that media type.

On phones the app goes systems → games → details, with **‹ Back** under the header; the phone's own Back gesture works too. The header shows icons, with the current page's name.

The header's row below shows library totals, when this browser last scanned the system, and the keyboard shortcuts. **🧰 Tools** works on every page: on the Bookcase or Timeline it opens the library with that tool (`/?tool=health`, `scrape`, `media`, `history`, `saves` or `backups`).

### Bookcase

**📚 Bookcase** in the header (or `/shelf`) shows the collection as a bookcase, one shelf per system, without changing the library page.

- **Boxes** are sized like the real box or case for that system (`BOX_SIZES` in `frontend/shelf.html`), so SNES boxes stand tall and PlayStation jewel cases are short and thin.
- **Spines** use the game's `boxside` image. Download spines with the **Spine** media type in single or bulk scraping (ScreenScraper `box-2D-side`). Without one, the spine shows the left edge of the cover with the title down it.
- **Hover** (or keyboard focus) turns the box to face you: it widens to its Box 2D cover, the boxes beside it slide over to make room, and the game's name and year show underneath. Boxes without a cover enlarge the spine instead.
- **Click** (or tap, or Enter) pulls the box out: it slides up out of the shelf, leaving a gap, and swings towards you. Then a card opens with the 3D box render (`box3d`, or the cover), details and **Open in RetroManager**. **Put it back** (or Esc) slides it back into its gap. With reduced motion switched on, the card opens straight away.
- **Keyboard:** ← → along a shelf, ↑ ↓ between shelves, Enter opens.
- Shelves are in system-name order. Pick one system from the system menu (remembered in the browser), or show all.
- Search dims boxes that don't match and hides shelves with none. By default only games with a gamelist entry are shown.

- **⚙ Options** (remembered in the browser):
  - **Popup picture:** what the card shows when you take a box out: 2D box, 3D box, poster, image or mix. A game without it shows another picture it has.
  - **Preload pictures:** fetches every shown game's cover (the hover picture) and popup picture in the background, 4 at a time, with progress in the menu, so hovering and opening are instant.

Images are served as small WebP thumbnails, made on first use and kept in `THUMB_DIR` (`/data/thumbs` in docker-compose.yml, so they survive rebuilds). Their addresses carry the source file's change time, so browsers keep them for a year and still pick up new art straight away.

### Adding games

**➕ Add games** in the header (or **Add** in the game list, or `/import`) opens a three-step wizard that works on a phone as well as a PC:

1. **Choose files.**
   - **From this device:** pick or drop files. They upload in 8 MB pieces with a progress bar; if the connection drops, the upload retries and carries on where it stopped (choosing the same file again later resumes it too). The screen is kept awake while uploading where the browser allows.
   - **From the inbox folder:** anything copied to the `inbox` folder on the server (over the network, Syncthing...). Put games in a folder named after the system (`inbox/snes/`) to skip choosing it.
2. **Check details**, one card per game:
   - **Grouping:** a `.cue` and the tracks it names are one game (missing tracks are pointed out); several discs of one game become one game with an `.m3u` playlist.
   - **System:** from the file extension, or for disc images (`.iso`, `.bin`, `.chd`…) from markers inside the file (GameCube, Wii, PlayStation 1/2, PSP, Saturn, Sega CD, PC Engine CD). Only systems you have folders for are offered.
   - **Match:** ScreenScraper looks the file up by name, size and MD5 checksum (files up to 1 GB), so a known dump is an **Exact** match whatever it's called. Exact and Likely matches are picked; search another name, or choose **Don't scrape**.
   - **Name:** ScreenScraper's (put in your house style), or type your own.
   - **Warnings:** games that look like ones already in the library, and files that already exist in the system folder (those can't be added).
3. **Add:** moves the files into `roms/<system>/` with their own file names, adds the gamelist entry, and fills it from the match: empty fields, media (choose which; videos aren't offered) and Image/Thumbnail links. The games then show in the library, Bookcase and Timeline.

Uploads are staged in `inbox/.uploads/` rather than under `roms/`, so half-finished files don't sync to other devices. Unzip archives before adding them. PC game folders (DOS) are best copied to `roms/dos/` directly, then added with Scan.

**Share to RetroManager:** RetroManager can be installed as an app (it has a web app manifest and service worker). Installed on Android, it appears in the share menu, so a downloaded ROM can be shared straight into the wizard. Browsers only allow installing and sharing on **HTTPS**, so this starts working once RetroManager is behind a secure address (for example a reverse proxy with a certificate); over plain `http://` the wizard works the same, you just pick files inside it.

### Timeline

**🕰️ Timeline** in the header (or `/timeline`) puts every game on one timeline by release year, as covers with a coloured edge for the system family (Nintendo, Sega, Sony, computers, Atari).

- **Layout:** each year's covers stack up from the axis and spill into more piles to the right, so the page stays one screen tall and scrolls sideways (the mouse wheel scrolls it too). Years without games are thin gaps. **Decades** switches to smaller covers grouped by decade; the **'90 '00 …** buttons jump along. Games without a release year sit in an **Unknown** column at the end.
- **Filters:** tick systems and series; everything else fades (or disappears, with **Hide others**). Search works the same way. Filters are kept in the address, so a view can be bookmarked (`/timeline?series=star wars&systems=n64`).
- **Series** come from the part of the name before the colon, so house-style names group themselves: `Star Wars: Rogue Squadron` is in *Star Wars*. Sequel numbers come off (`Castlevania II: …` is *Castlevania*), and names without a colon join a series they start with (`Pokémon Snap` is in *Pokémon*). A series needs two games; the twelve biggest are shown, **All series** lists the rest.
- **Series line:** a picked series is joined by a line in release order, each cover numbered, and the timeline scrolls to its first game. Several series get a line each, in different colours.
- **Hover** shows the name, year and system; **click** opens the game's card with **Open in RetroManager**.
- By default only games with a gamelist entry are shown.

### Library health

**🧰 Tools › Library health** runs every system's Scan at once (a few seconds) and shows a table of issues per system. **Review** opens that system with its Scan panel.

**Fix safe issues everywhere** runs only the fixes that can't lose anything, across all systems: **Fix names**, **Link media** and **Merge into disc**. Each system's gamelist is backed up first. Relinking, creating or removing entries, renaming, duplicates, multi-disc playlists and moving unused media stay per system, in the Scan panel, where you review them.

### Library scrape

**🧰 Tools › Library scrape** scrapes every system from ScreenScraper in the background, one game at a time; close the panel and keep working (a **⏳ Scraping n/total** chip in the header, on every page, shows progress and reopens it).

- **Which games:** every game missing metadata, and optionally games with metadata that lack any of the chosen media types.
- **Confident matches** (ScreenScraper recognised the ROM file, or the name matches closely) are applied like Bulk scrape: empty fields only, and only media the game doesn't have yet. Each gamelist is backed up before its first change.
- **Uncertain matches** and misses are listed under **Needs a look** with the best guess; **Open** takes you to the game to scrape it by hand.
- Checked games are remembered in `retromanager/scrape-queue.json` and skipped for 30 days, so reruns don't spend the ScreenScraper quota again (tick **Recheck** to include them).
- Quota or login errors stop the run with the reason.

### Missing media

**🧰 Tools › Missing media** counts, per system, the games missing each media type. Click a system for a grid of its games missing the chosen type (or any), linking to each game. **Scrape … for these** starts a library scrape of that system for that media.

### Play history

**🧰 Tools › Play history** shows what's been played, from when each game's saves and save states were last written: recently played (for everyone, or one person), and per-system counts for the last 30 days and ever. Play counts from the gamelists are shown too, where EmulationStation writes them.

<a id="saves-tool"></a>
### Saves (tool)

**🧰 Tools › Saves**:

- **Sync conflicts:** when Syncthing keeps two versions of a save (`… .sync-conflict-<date>-<device>.srm`), both are listed with their times, sizes and state screenshots. **Keep this** gives that version the normal name so the emulator loads it; the others move to `save-backups/conflicts/<time>/`, never deleted.
- **Backups:** zip everything, or one system, with or without save states, into `save-backups/zips/` (in the background), then download or delete them. A single game's saves download from its Saves section (**Download all (zip)**).

### Gamelist backups

**🧰 Tools › Gamelist backups** lists every copy of a system's gamelist: dated backups, Syncthing conflict copies and other copies. Pick one to see what restoring it would do, entry by entry: entries it would bring back, entries it would remove, and each changed field (now → then). **Restore this copy** backs up the current gamelist first. **Keep newest 10 backups** deletes older dated backups.

### Saves

The **Saves** section of a game lists its in-game saves and save states:

- **One group per person** (`savestates/<person>/…` and `saves/<person>/…`), newest first, showing the slot, when it was saved, size and path. States that RetroArch saved with a screenshot show it; click to enlarge.
- **In-game saves (shared)**: `saves/<system>/…`, which isn't split by person.
- **Old save states, not in a person's folder** (collapsed): anything in `savestates/<system>/…` or other loose folders.

Files are matched by name: the ROM file name (or its title without tags) followed by `.srm`, `.sav`, `.dsv`, `.state`, `.state<N>`, `.state.auto` and similar. Syncthing conflict copies are included and marked (resolve them in [Tools › Saves](#saves-tool)). Emulator-named folders such as `mGBA/` are searched too. Saves named by game ID (PSP `SAVEDATA`, GameCube memory cards) can't be matched to a ROM and aren't shown.

### Scan

**Scan** in the game list header checks the selected system and lists what it finds, each with a fix you can apply to all or selected items:

| Section | Fix |
|---|---|
| Multi-disc games without a playlist | **Create .m3u**: writes `<game>.m3u` listing the discs (`… (Disc 1).cue`, `… (Disc 2).cue`) next to them, and makes it the game's one entry: the disc entries' details are kept and disc 1's media is renamed to match. Swap discs from the emulator's menu. Disc files aren't moved. |
| Saves inside the ROM folder | **Move out of roms**: saves and save states belong only in the top-level `saves/` and `savestates/` folders. Ones found next to ROMs (an emulator whose save folder setting is missing) move to `save-backups/in-rom-folders/<time>/<system>/`, where nothing syncs them. PC systems are skipped (their game folders keep their own saves). |
| Possible duplicates | **Move extra copies aside**: the same game more than once (same file name apart from tags, or the same gamelist name). Pick the copy to keep (suggested: the one with an entry, more media, more plays and a USA/Europe/World tag); the others move to `retromanager/duplicates/<system>/` (with a `.cue`'s tracks), and their details, play counts and any media the kept copy lacks carry over. Logged in `duplicates/moved.log`. |
| Names missing their first letters | **Fix names**: an entry whose name is its ROM file name (or that name without tags) with the first 1–2 characters cut off (a Skraper glitch, e.g. `arry Potter` for `Harry Potter`) gets them back. Nothing else changes. |
| Names not in house style | **Rename**: series and subtitle split by a colon, later dashes kept (`Star Wars - Rogue Leader - Rogue Squadron II` → `Star Wars: Rogue Leader - Rogue Squadron II`); `Legend of Zelda, The - X` → `The Legend of Zelda: X`; region, language, revision and 3DS product-code tags removed; Title Case (small words like *of*, *the*, *and* lower case; existing capitals such as `NBA`, `II`, `WarioWare` kept; ALL CAPS names converted); `Pokemon` → `Pokémon`. A known series with no dash before its subtitle (`Star Wars Episode I - Racer`) gets the colon too; add series with `NAME_STYLE_SERIES=Series One,Series Two`. Untick exceptions before renaming. Scraped names and new entries use the same style. Rules live in `backend/name_style.py`. |
| Disc track files listed as games | **Merge into disc**: folds gamelist entries for a disc's track files (the files its `.cue` names, e.g. `… (Track 03).bin`) into the `.cue`'s entry, copying any details the disc entry lacks. Files aren't touched. |
| Entries pointing at a wrong file name | **Relink**: points the entry at the ROM with the nearly identical name and renames media saved under the wrong name. Catches Skraper's habit of dropping the first letter (`./ario Kart Wii.iso`). Suggestions need the same extension and folder, and the same numbers in the name, so *Part 1* never pairs with *Part 2*. |
| Media not linked in the gamelist | **Link media**: fills empty or broken `<image>`/`<thumbnail>`/`<video>` |
| ROMs without a gamelist entry | **Create entries**: adds an entry named after the file, with media linked |
| Gamelist entries with no ROM | **Remove from gamelist**: deletes the entry only, never files |
| Media files nothing uses | **Move to _orphaned**: moves files to `<media system folder>/_orphaned/<type>/` so they can be restored |

Every change to `gamelist.xml` first saves a backup next to it as `gamelist_YYYYMMDD_HHMMSS.xml`. See and restore them in [Tools › Gamelist backups](#gamelist-backups) (or the settings button).

## API

All routes are under `http://<host>:5000`.

### Systems and games

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/systems` | List discovered systems |
| POST | `/api/systems/<system>/scan` | Everything the Scan panel shows: `relink`, `media_links`, `new_roms`, `orphaned_metadata`, `orphaned_media` |
| POST | `/api/systems/<system>/names/fix` | `{paths?: [...]}`: restore names cut off at the start (all when omitted) |
| POST | `/api/systems/<system>/saves-in-roms/move` | `{paths?: [...]}`: move save files out of the ROM folder to `save-backups/in-rom-folders/` |
| POST | `/api/systems/<system>/multi-disc/create` | `{m3us?: [...]}`: write `.m3u` playlists and merge the disc entries (all when omitted) |
| POST | `/api/systems/<system>/duplicates/resolve` | `{groups: [{keep, remove: [...]}]}`: move extra copies to `DATA_PATH/duplicates/` |
| GET | `/api/systems/<system>/launch-files?rom=<path>` | PC games: every program in the game's folder, likeliest first |
| POST | `/api/systems/<system>/launch-file` | `{from, to}`: point a PC game at another program in its folder |
| POST | `/api/systems/<system>/names/style` | `{paths?: [...]}`: rename entries to the house name style (all when omitted) |
| POST | `/api/systems/<system>/relink` | `{pairs: [{from, to}]}`: repoint entries and rename their media |
| POST | `/api/systems/<system>/link-media` | `{paths?: [...]}`: fill empty or broken media fields (all when omitted) |
| POST | `/api/systems/<system>/entries/create` | `{rom_paths: [...]}`: add basic entries |
| POST | `/api/systems/<system>/entries/remove` | `{paths: [...]}`: remove entries (no files deleted) |
| POST | `/api/systems/<system>/orphaned-media/move` | `{files: ["<media system>/<type>/<file>"]}`: move to `_orphaned/` |
| GET | `/api/systems/<system>/games` | List games (gamelist entries plus ROMs without one) |
| GET | `/api/systems/<system>/games/<rom path>` | One game |
| POST | `/api/systems/<system>/games` | Create a game: JSON for an existing ROM, or multipart to upload a ROM plus media (older; the import wizard replaces it) |
| PUT | `/api/systems/<system>/games/<rom path>` | Update a game's gamelist entry |
| DELETE | `/api/systems/<system>/games/<rom path>` | Remove the entry. `?delete_rom=1` also deletes the ROM file, `?delete_media=1` its media |
| POST | `/api/systems/<system>/games/preview` | The `<game>` XML a save of the posted game would write (nothing is written) |

### Adding games

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/uploads` | `{name, size, key}`: start an upload, or resume the one with the same key. Returns `{id, received}` |
| PUT | `/api/uploads/<id>?offset=<byte>` | Raw chunk starting at `offset` |
| GET / DELETE | `/api/uploads/<id>` | Upload progress / discard it |
| GET | `/api/import/pending` | Uploads and inbox files waiting to be added |
| POST | `/api/import/analyze` | `{refs}`: group files into games, suggest systems and names |
| POST | `/api/import/identify` | `{refs, system, query?}`: ScreenScraper match, look-alikes in the library, file clashes |
| POST | `/api/import/commit` | `{refs, system, name?, game_id?, media}`: file the game in and add its entry |
| POST | `/share` | Share target: multipart `roms` files, staged, then redirects to `/import` |

Refs are `upload:<id>` or `inbox:<path in the inbox>`.

### Media

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/media/<media system>/<type>/<file>` | Serve a media file, falling back to a case-insensitive match on the file name |
| POST | `/api/systems/<system>/media/upload` | Multipart `rom_path`, `folder`, `file`: save as `<media system>/<folder>/<ROM name>.<ext>` |
| GET | `/api/missing-media` | Per system, games missing each media type. `?system=<name>` lists the games |

### Gamelist backups

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/systems/<system>/gamelist-backups` | Every copy of the gamelist, newest first, with entry counts |
| GET | `/api/systems/<system>/gamelist-backups/<name>/diff` | What restoring it would change: `added`, `removed`, `changed` (field by field) |
| POST | `/api/systems/<system>/gamelist-backups/<name>/restore` | Restore it (the current gamelist is backed up first) |
| DELETE | `/api/systems/<system>/gamelist-backups/<name>` | Delete one copy |
| POST | `/api/systems/<system>/gamelist-backups/prune` | `{keep: 10}`: delete older dated backups |

Older routes, taking a JSON body with `system`:

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/backup_gamelist` | Copy `gamelist.xml` to `gamelist_<timestamp>.xml` |
| POST | `/api/list_gamelist_backups` | List backups, newest first |
| POST | `/api/restore_gamelist_backup` | Restore the backup named in `backup` over `gamelist.xml` (current one backed up first) |

### Scraping

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/scraper/search` | ScreenScraper search |
| POST | `/api/scraper/game-info` | Normalised metadata for one ScreenScraper result |
| POST | `/api/scraper/download-media` | Download ScreenScraper media into the media folder |
| POST | `/api/igdb/search` | IGDB search |
| POST | `/api/igdb/game-info` | Normalised metadata for one IGDB game |
| POST | `/api/igdb/download-media` | Download IGDB media into the media folder |
| POST | `/api/bulk-scrape/match` | `{system_name, rom_path, query?}`: best ScreenScraper match, confidence and alternatives |
| POST | `/api/bulk-scrape/apply` | `{system_name, rom_path, game_id, media}`: fill empty fields, download missing media, link and save |
| GET | `/api/scrape-queue` | Library scrape progress: `running`, `total`, `done`, `current`, `applied`, `review`, `failed` |
| POST | `/api/scrape-queue/start` | `{systems?, include_media?, media?, recheck?}`: start a library scrape |
| POST | `/api/scrape-queue/stop` | Stop after the current game |

Request and response shapes are in [SCRAPING.md](SCRAPING.md).

### Status and debugging

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/systems/<system>/saves?rom=<rom path>` | A game's saves and states, with person, type, slot, size and date |
| GET | `/api/save-screenshot/<saves\|savestates>/<path>` | A save state's `.png` screenshot |
| GET | `/api/systems/<system>/saves/download?rom=<rom path>` | A zip of one game's saves and states |
| GET | `/api/save-conflicts` | Syncthing conflicts, each with every version |
| POST | `/api/save-conflicts/resolve` | `{id, keep}`: keep one version, move the others to `save-backups/conflicts/` |
| GET | `/api/save-backups` | Zipped save backups and the running job |
| POST | `/api/save-backups` | `{system?, include_states?}`: zip saves in the background |
| GET / DELETE | `/api/save-backups/<name>` | Download or delete a backup zip |
| GET | `/api/play-history` | Per game: last save time and by whom, from the save folders |
| GET | `/api/shelf` | Every system's games with what the Bookcase and Timeline draw. Cached like `/api/stats` |
| GET | `/api/thumb/<160\|320\|480>/<media path>` | A media image scaled to that height, as WebP. `?spine=1` turns landscape spines upright |
| GET | `/api/library-scan` | Every system's Scan, as counts per issue (for Library health) |
| GET | `/api/health` | Whether the ROM and media mounts are reachable |
| GET | `/api/stats` | `systems_with_roms`, `total_games`, `games_missing_metadata`. Cached; `?refresh=1` recounts |
| GET | `/api/debug/media-list/<media system>/<type>` | Files the backend can see in one media folder |
| GET | `/api/debug/gamelist-paths/<system>` | Every `<path>` in a system's gamelist |

## Troubleshooting

| Problem | Check |
|---|---|
| Container won't start | `docker compose logs retromanager`; check `RETRO_DIR` in `.env` exists |
| Page won't load | `curl http://localhost:5000/api/health`; check nothing else uses port 5000 (set `RETROMANAGER_PORT` in `.env` if so) |
| No systems | `roms_accessible` in `/api/health`; the ROM mount must contain one folder per system |
| Changes not saving | Write permission on the ROM folder; errors in the container log |
| Media not showing in RetroManager | The file name must match the ROM file name (or its title without tags), in a type folder listed above. `/api/debug/media-list/...` shows what the backend sees. |
| Media not showing in EmulationStation | Run **Scan** and use **Link media**; the gamelist must reference the file |
| Media in the wrong system folder | See how the media system folder is resolved above; rename the folder or add an alias in `_resolve_media_system` in `backend/scanner.py` |
| Scraper errors | See [SCRAPING.md](SCRAPING.md#troubleshooting) |

## Notes

- **Local network only**: there's no authentication, CORS is open, and debug routes are exposed. Don't publish the port to the internet.
- **`/api/stats` is cached**: it's recounted after any change made through RetroManager, and at least every 10 minutes (`STATS_MAX_AGE` in `backend/app.py`) to catch changes made directly in the folders.
- **Logging**: set to `DEBUG`, so `docker compose logs` is verbose.

## Licence

[MIT](LICENSE) © [DeltaGemini](https://github.com/DeltaGemini). Use it, change it and share it freely; copies and forks must keep the licence and credit.

The repository contains no artwork: box art, screenshots and videos come from your own library and the scrapers, and the app icon is drawn by the backend.
