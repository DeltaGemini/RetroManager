# API

The HTTP API the pages use. Everything is JSON unless said otherwise.

## API

All routes are under `http://<host>:5000`.

### Systems and games

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/systems` | List discovered systems |
| POST | `/api/systems/<system>/scan` | Everything the Scan panel shows: `relink`, `media_links`, `new_roms`, `orphaned_metadata`, `orphaned_media` |
| POST | `/api/systems/<system>/names/fix` | `{paths?: [...]}`: restore names cut off at the start (all when omitted) |
| POST | `/api/systems/<system>/saves-in-roms/move` | `{paths?: [...]}`: move save files out of the ROM folder to `save-backups/in-rom-folders/` |
| POST | `/api/systems/<system>/game-folders/rename` | `{paths?: [...]}`: rename PS3 game folders to `<game>.ps3` (every finished one when omitted) |
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

### Generating Mix pictures

Games are named by `{system, rom_path}`; a preview is named by its job and its index in the job's `items`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/mix/templates` | The layouts available, and the default |
| POST | `/api/mix/inventory` | `{system}`, `{systems}` or `{games: [{system, rom_path}]}`, optional `template`: per system, how many are `full`, `partial` and `ineligible`, and per game its tier and `reason` (`no_screenshot`, `screenshot_only`, `no_box_or_wheel`). With a system, only games without a Mix; with `generated: true`, the games whose Mix was generated instead. Writes nothing |
| POST | `/api/mix/jobs` | Same body, plus `options` (and per game `template`, `options`): start drawing previews |
| GET | `/api/mix/jobs` | Sets of previews still around |
| GET | `/api/mix/jobs/<job>` | Progress (`running`, `done`, `total`, `failed`) and each game's `status` (`pending`, `rendering`, `ready`, `failed`, `ineligible`, `committed`, `rejected`), `reason`, `used` media and `warnings` |
| GET | `/api/mix/preview/<job>/<index>` | A preview PNG |
| POST | `/api/mix/jobs/<job>/regenerate` | `{items: [{index, template?, options?}]}`. Options: `box`, `media`, `wheel` (`false` leaves it out), `box_type` (`3d`, `2d`), `screenshot` (`screenshot`, `title`) |
| POST | `/api/mix/jobs/<job>/commit` | `{approve: [index], reject?: [index], overwrite?: true}`: per index `committed`, `needs_overwrite`, `not_ready` or `failed`; `backup` names the tarball of replaced files |
| DELETE | `/api/mix/jobs/<job>` | Throw the previews away |

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
| GET | `/api/systems/<system>/achievements?rom=<path>` | The game's RetroAchievements list and what the RetroAchievements user has earned (`refresh=1` skips the 5-minute cache) |
| GET | `/api/achievements/overview` | Every game the RetroAchievements user has progress in, most complete first, with its library game |
| GET | `/api/library-state` | Every game's play status, and the collections |
| PUT | `/api/play-status` | `{system, rom_path, status}`: set or clear a game's play status |
| PUT | `/api/favorite` | `{system, rom_path, favorite}`: set the gamelist's `<favorite>` |
| GET, POST, PUT, DELETE | `/api/collections[/<id>]` | List the collections with their games, or make, rename or delete one; `PUT /api/collections/<id>/games` adds or removes a game (`{system, rom_path, member}`) or several (`{games: [...], member}`) |
| GET | `/api/rom-index` | ROM check progress and report; `POST /api/rom-index/start` (`{recheck?}`) and `/stop` |
| POST | `/api/rom-index/rename` | `{items: [{system, rom_path}]}`: rename misnamed ROMs to the database's name, with everything that follows them |
| POST | `/api/rom-index/duplicates/resolve` | `{keep, remove: [...]}`: move the other copies of a file out of the library |
| POST | `/api/systems/<system>/empty-roms/move` | `{paths}`: move empty ROM files out of the library |
| GET, POST | `/api/data-backups` | List the backups of RetroManager's own data, or make one now |
| GET | `/api/achievements/unlocks` | `?who=`: a person's latest unlocks and their running total by month |
| GET | `/api/play/phone-states?system=&rom=&profile=&core=` | The person's RetroArch save states for the game, as the phone app carries them: name, date, checksum, and whether `core` loads each |
| GET, PUT | `/api/play/phone-state?system=&rom=&profile=&name=` | One of them, as RetroArch wrote it (`modified=` on PUT is its date) |
| GET, PUT | `/api/play/state?system=&rom=&profile=` | Read or write a person's browser save state |
| GET | `/api/play/pi-states?system=&rom=` | The game's RetroArch save states, each with the core that made it and the browser core that loads it |
| GET | `/api/play/pi-state?system=&rom=&path=` | One of them, unpacked to what the emulator core loads |
| PUT | `/api/play/pi-state?system=&rom=&profile=&slot=` | Write the browser's state as the person's RetroArch save state (`slot`: `auto` or a number) |
| GET | `/api/phone/info?system=&rom=` | What the phone app needs to start a game in RetroArch: its cores, the files it's made of (with sizes) and its save's name |
| GET | `/api/phone/rom/<system>/<path>` | One of those files (takes a `Range`) |
| GET | `/api/phone/bios/<system>/<name>` | One of a system's BIOS files, for RetroArch's system folder |
| POST | `/api/phone/played` | `{system, rom, at}`: the signed-in person started this game on a phone (counts for Continue playing) |
| GET, POST | `/api/phone/setup` | The RetroArch setup kept for other phones: its files, and which phone it came from. POST `{device, base, package, files}` makes it the files just sent |
| GET, PUT | `/api/phone/setup/file?path=` | One file of it, by its path in the RetroArch folder |
| GET | `/api/phone/cores` | The library's systems RetroArch can play, each with its cores |
| GET | `/api/console/home` | The Console page's recent games, Favourites and collections (`pending` while first being worked out) |
| GET | `/api/systems/<system>/rom-files?rom=[&hash=1]` | The files a game is made of, with their checksums (`hash=1` works out the missing ones) |
| GET | `/api/series/game?system=&rom=` | The game's series: every game in it, the library games that are each, and your marks |
| GET | `/api/series/list?key=` | One series, the same way |
| GET | `/api/series/overview` | Every series the library has games from, the want list, and the matching's progress |
| POST | `/api/series/run` | Match the whole library in the background (`{redo: true}` looks every game up again) |
| PUT | `/api/series/mark` | `{id, mark}`: mark a game you don't have as `want` or `skip`; null clears it |
| PUT | `/api/series/platform` | `{series, platform, skip}`: hide or show a platform's games within a series |
| GET | `/api/series/candidates?system=&rom=&q=` | IGDB games a library game could be |
| PUT | `/api/series/match` | `{system, rom_path, id}`: say which IGDB game a library game is |
| GET | `/emulatorjs/<path>` | EmulatorJS's files, fetched once and kept |
| GET | `/api/systems/<system>/rom-info?rom=<path>` | What the ROM check knows about one file |
| GET | `/api/systems/<system>/achievement-badges` | Which of a system's games have achievements, and how many are earned |
| GET | `/api/play/info?system=&rom=` | Whether a game can be played in the browser, and what the player needs |
| GET | `/api/rom/<system>/<path>` | The ROM file, for the browser emulator |
| GET, PUT | `/api/play/save?system=&rom=&profile=` | Read or write a person's battery save for browser play |
| GET | `/api/settings` | The settings in groups; passwords and keys only say whether they're set |
| PUT | `/api/settings` | `{values: {key: value}}`: save and apply settings (`""` clears one) |
| GET | `/api/scrape-sources` | Which sources the Scrape popup can use, and which need a key |
| POST | `/api/sources/<source>/search` | Search `retroachievements`, `steam`, `steamgriddb` or `libretro` |
| POST | `/api/sources/<source>/game-info` | Normalised metadata and media for one result from that source |
| POST | `/api/bulk-scrape/match` | `{system_name, rom_path, query?}`: best match (ScreenScraper, or RetroAchievements by checksum), confidence and alternatives |
| POST | `/api/bulk-scrape/apply` | `{system_name, rom_path, game_id, media}`: fill empty fields, download missing media, link and save |
| GET | `/api/scrape-queue` | Library scrape progress: `running`, `total`, `done`, `current`, `applied`, `review`, `failed` |
| POST | `/api/scrape-queue/start` | `{systems?, include_media?, media?, recheck?}`: start a library scrape |
| POST | `/api/scrape-queue/stop` | Stop after the current game |

Request and response shapes are in [SCRAPING.md](scraping.md).

### Profiles and login

| Method | Path | What it does |
|--------|------|--------------|
| GET | `/api/accounts/me` | Whether login is on, who this device is signed in as, the profiles, and that person's preferences |
| POST | `/api/accounts/login` | `{profile, pin}`: sign this device in (a player needs no PIN) |
| POST | `/api/accounts/logout` | Sign this device out |
| PUT | `/api/accounts/prefs` | `{prefs}`: the signed-in person's preferences |
| PUT | `/api/accounts/profile` | `{name, role, pin}`: a profile's role or PIN (admin) |
| POST | `/api/accounts/people` | `{name}`: a new profile and its folders (admin) |
| POST, GET | `/api/accounts/photo` | Set a profile's photo (form: `name`, `file`; admin), or fetch one by file name |
| PUT | `/api/accounts/enabled` | `{enabled, profile, pin}`: switch login on (as that admin) or off (admin) |

With login on, every other `/api/` request needs a signed-in device (401 otherwise), and a player's may only read, plus set their own play status, saves and want list, and favourites (403 otherwise).

### Status and debugging

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/tasks` | Background tasks running or just ended (library scrape, ROM check, series matching): `label`, `running`, `done`, `total`, `current`, `summary`, `problem`. Empty for players |
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
