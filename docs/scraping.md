# Scraping

RetroManager can pull metadata and artwork from seven sources:

| Source | Needs | Good for |
|---|---|---|
| **ScreenScraper** (screenscraper.fr) | developer credentials | Everything retro: the fullest metadata and media |
| **IGDB** (igdb.com, via Twitch) | Twitch credentials | Descriptions and covers, including many ROM hacks |
| **RetroAchievements** | your API key | Recognising a ROM by its checksum, ROM hacks included |
| **Steam** | nothing | PC games: store details and library artwork |
| **SteamGridDB** | your API key | Community covers, heroes and logos for any system (artwork only) |
| **TheGamesDB** (thegamesdb.net) | your API key (asked for on its forums) | Descriptions, release dates, players and genres, with box art, fan art, screenshots, title screens and clear logos |
| **LaunchBox** (gamesdb.launchbox-app.com) | turning it on in Tools › Settings (it fetches a 110 MB list of games) | Pictures of every kind, cartridges and discs among them; fan-made ones for many ROM hacks (artwork only) |
| **GameTDB** (gametdb.com) | nothing | The disc or cartridge, cover and 3D box of this very game, by the ID in its ROM: GameCube, Wii, DS, 3DS, PS3 (artwork only) |
| **libretro thumbnails** | nothing | Box art, screenshots, title screens and logos by No-Intro name (artwork only), with no quota |

Behind these, **Hasheous** (hasheous.org, no account) turns a ROM's checksum into the same game's ID on ScreenScraper, IGDB, RetroAchievements and SteamGridDB, so the right game is found whatever the file is called.

## In the UI

1. Select a game and click **Scrape**.
2. Adjust the search text if needed, then click a source. A source that needs a key you haven't set is greyed out, and its tooltip names the variable. Searches are filtered to the game's system when RetroManager recognises the ROM folder name (see [System matching](#system-matching)).
3. Click a result. Results show the release year and regions, and ROM hacks and mods are marked **Hack / mod** and listed after the originals. A result marked **ROM match** was found from the file's checksum rather than its name, and is listed first (see [Checksum matching](#checksum-matching)). The **Compare Metadata** view shows each field, current against scraped. Tick the fields to import.
4. Under **Assign Media**, each image the game doesn't have yet is already set to its matching folder (IGDB: cover → Box 2D, first screenshot → Screenshot, first artwork → Fanart; SteamGridDB: first grid → Box 2D, first hero → Fanart, first logo → Wheel; TheGamesDB: front box → Box 2D, first fan art → Fanart, first screenshot → Screenshot, title screen → Title screen, clear logo → Wheel). Where the game already has that image, the card starts on **Skip** and shows **Current** and **New** side by side (**Compare** shows both full size); choose the folder to replace it. Videos start on **Skip** because they're large. Each folder holds one file per game, so if two images go to the same folder the first one wins.
5. Click **Apply Selected Changes**. Assigned media is downloaded straight away and the form is filled in, including any empty Image, Thumbnail and Video fields (what EmulationStation displays).
6. Click **Save** to write the metadata to `gamelist.xml`. Downloaded media is already on disk whether or not you save.

Media downloads one file at a time with a progress bar. If a search, lookup or download fails, a message at the top of the popup says why (see [Troubleshooting](#troubleshooting)); if some downloads fail, everything else is still applied and the popup stays open to list the failures.

## Bulk scraping

**Bulk scrape** (in the game list header) scrapes many games of one system at once, from ScreenScraper:

1. **Choose games.** Start from a group (Missing metadata, No description, No image in gamelist, All) and untick any you want to skip. Choose which media to download; videos aren't offered, because they're large and slow.
2. **Find matches.** Each game is looked up by its ROM file name, which ScreenScraper recognises for most No-Intro/Redump-named ROMs. If that fails, the file's checksum is looked up (see [Checksum matching](#checksum-matching)), which finds renamed files and, with a RetroAchievements key, ROM hacks. If that fails or looks wrong too, it falls back to a title search, using the title the checksum gave when there is one. Each result gets a confidence:

   | Confidence | Meaning | Ticked? |
   |---|---|---|
   | **Exact** | This exact ROM file was recognised, by its name or its checksum | Yes |
   | **Likely** | The game's name closely matches the ROM's title | Yes |
   | **Unsure** | A game was found but the names differ | No |
   | **No match** | Nothing found | No |

   Matching takes 1–4 seconds per game and can be stopped at any time.
3. **Review.** Pick another result from the dropdown, or for Unsure/No match rows search a different name. **Needs attention** shows only the rows to check.
4. **Apply.** The gamelist is backed up once, then each ticked game gets:
   - **Empty fields filled.** Fields that already have a value are never replaced. A game without an entry gets its name from ScreenScraper.
   - **Missing media downloaded.** Types the game already has a file for are skipped, unless **Replace the media these games already have** is ticked in step 1 (for pictures that are the wrong ones): then each ticked type is downloaded again where the match has one, and the old file is copied to `DATA_PATH/replaced-media/<date-time>/` first. Where ScreenScraper has no box art, screenshot, title screen or wheel (or the download fails), the libretro thumbnail is used if there is one; choose **Before ScreenScraper** in Tools › Settings to try libretro first for those four, which saves ScreenScraper quota, or `off` to never use it.
   - **Image, Thumbnail and Video linked** in the gamelist where they're empty or broken.

Each media file is a ScreenScraper request, so a large batch uses a noticeable part of the daily quota; a ScreenScraper user account (Tools › Settings) raises it. If the quota runs out, the batch stops and says so, and everything applied so far is kept.

## Library scrape

**🧰 Tools › Library scrape** runs the same matching over every system in the background, without a review step: **Exact** and **Likely** matches are applied straight away (empty fields and missing media only), and **Unsure** and **No match** games are listed under **Needs a look** for you to scrape by hand. Optionally it also covers games that have metadata but lack some media. Games it has checked are skipped for 30 days. Details are in the [README](library.md#library-scrape).

Names from ScreenScraper and IGDB are put in the house name style (`Series: Subtitle`, see the README's Scan section) before they're shown or saved.

PC games (DOS and similar) are matched by their folder name rather than the program's file name.

A match from RetroAchievements (a ROM hack ScreenScraper doesn't list, say) fills name, genre, developer, publisher and release date, and offers box art, a screenshot and a title screen.

**Filling the gaps.** Whatever the match leaves empty (a RetroAchievements match has no description) is filled from IGDB, when the ROM's checksum identifies the game there. The same goes for box art, a screenshot and fanart that neither the match nor libretro has. Only a checksum match is used, never a name search, since nobody reviews these.

**Then GameTDB**, for a disc or cartridge picture only, on GameCube, Wii, DS, 3DS and PS3. The game's own ID is read from the ROM (`.iso`, `.gcm`, `.ciso`, `.wbfs`, `.rvz`, `.wia`, `.nds`, `.3ds`, `.cci`, a `.cia` that isn't encrypted or has its code in its name, a PS3 `.iso` or game folder), so the picture is that game's and no other's. No account and no quota; **Tools › Settings › Matching and media** turns it off.

**Then the LaunchBox Games Database**, when it's turned on in the same place (it's off to begin with). It has pictures of every kind, cartridges and discs among them, and fan-made ones for many ROM hacks. It has no search to ask: RetroManager fetches its list of every game (about 110 MB) once a month and keeps an index of the platforms it knows in `launchbox.db` in `DATA_PATH` (about 120 MB); the strip under the header shows it being fetched, and a library scrape won't start until the first one is done. A game is found by title on the system's own platform (ignoring tags and punctuation), by any of the names LaunchBox knows it by. A real cartridge or disc is preferred to a fan-made one, and a North American or worldwide picture to another region's.

Both are sources in the **Scrape** popup as well: **LaunchBox** searches its list by the words of the name and offers every picture it has of the game to choose between; **GameTDB** has no search, so it shows the one game the ROM's ID is, or says why it can't tell.

**Then TheGamesDB and SteamGridDB**, where their API keys are set (Tools › Settings), for a picture none of the above has. TheGamesDB can give box art, the back of the box, fanart, a screenshot, a title screen, a wheel logo and a banner; SteamGridDB a cover (as box art), a hero (as fanart) and a logo (as the wheel). Neither can look a ROM up by its checksum, so only a game with the same title is used (ignoring tags and punctuation): on TheGamesDB it must also be on the system's own platform, and on SteamGridDB the game Hasheous identifies from the checksum is preferred when there is one. TheGamesDB is asked once per game and its allowance is by the month; a source that fails is left out for 15 minutes rather than asked for every game.

**Where a picture came from** is noted when it's downloaded (in `media-sources.db` in `DATA_PATH`), by any of these routes, and shown under it in a game's **Media** section ("from LaunchBox"), so a wrong one can be traced to its source. A picture you add yourself is "a file of yours"; one changed by other means since is no longer said to be from anywhere. Pictures downloaded before this was kept say nothing.

## Checksum matching

A ROM's checksums (MD5, SHA-1) identify the file whatever it's called. RetroManager works them out when a source needs them and remembers them in `rom-hashes.json` in `DATA_PATH` until the file changes. Files over 1 GB and PC game folders aren't hashed; a `.zip` holding one ROM is hashed as that ROM.

- **Hasheous** is asked what game the checksum belongs to. It answers with that game's ID on ScreenScraper, IGDB, RetroAchievements and SteamGridDB, and searches on those sources list that game first, marked **ROM match**. This is how IGDB finds the right game when its own search ranks hacks and fan games above it. Only the checksums are sent, never the file or its name. Tools › Settings turns this off.
- **RetroAchievements** lists the checksums of every ROM it supports, ROM hacks included, using its own method for some systems (headers skipped on NES, SNES, Lynx, 7800 and PC Engine; byte order fixed on N64; program sections on DS; the file name for arcade sets). RetroManager computes those and looks them up in the system's game list, which is downloaded once and kept for a week in `DATA_PATH/retroachievements/`. Disc systems are matched through Hasheous's RetroAchievements ID instead.

## What each source provides

| Field | ScreenScraper | IGDB | RetroAchievements | Steam |
|---|---|---|---|---|
| name | ✓ (US → World → EU → … name) | ✓ | ✓ | ✓ |
| desc | ✓ English synopsis | ✓ summary | — | ✓ store blurb |
| genre | ✓ first genre, English | ✓ all genres, comma-separated | ✓ | ✓ all genres |
| developer / publisher | ✓ | ✓ | ✓ | ✓ |
| releasedate | ✓ first regional date, US preferred | ✓ first release | ✓ | ✓ |
| players | ✓ | — | — | `1` for single-player-only games |
| rating | ✓ (out of 20, scaled to 0–1) | ✓ (out of 100, scaled to 0–1) | — | ✓ Metacritic score |

SteamGridDB gives a name and release date; libretro thumbnails give media only.

Dates are converted to EmulationStation's `YYYYMMDDT000000`.

### Media

**ScreenScraper** results are already sorted into RetroManager folders, using the US image first, then World, EU, generic, UK, JP:

| ScreenScraper type | Offered as |
|---|---|
| `box-2D` | box2d |
| `box-3D` | box3d |
| `box-2D-side` | boxside (the spine, used by the Shelf) |
| `support-2D` | support (the cartridge or disc, used when [generating a Mix](library.md#generating-mix-pictures)) |
| `ss` | screenshot |
| `sstitle` | screenshottitle |
| `wheel-hd`, else `wheel` | wheel |
| `fanart` | fanart |
| `mixrbv2`, else `mixrbv1` | mix |
| `video-normalized`, else `video` | videos |
| `manuel` | manuals |

**IGDB** offers `cover`, `screenshot_1`–`screenshot_3` and `artwork_1`–`artwork_2`. Assign them to folders yourself (typically cover → Box 2D, a screenshot → Screenshot, artwork → Fanart).

**RetroAchievements** offers its box art (box2d), in-game screenshot (screenshot), title screen (screenshottitle) and badge `icon`.

**Steam** offers the library cover (box2d, 600×900), logo (wheel), library hero (fanart), `screenshot_1`–`screenshot_3` and the store `header`.

**SteamGridDB** offers the best-voted `grid_1`–`grid_3` (portrait covers), `hero_1`–`hero_2` and `logo_1`–`logo_2`.

**libretro thumbnails** offers box2d, screenshot, screenshottitle and wheel (logo). They're filed by exact No-Intro/Redump name, so the ROM's name is tried first, then the text you typed, each also with the usual region tags added (`(USA)`, `(World)`, `(Europe)`...). Arcade sets, Steam and other PC games have none.

## Where downloads go

```
<media mount>/<media system folder>/<folder>/<ROM file name without extension>.<ext>
```

For example, box art for `roms/snes/Super Mario World (USA).sfc` goes to `media/Super Nintendo/box2d/Super Mario World (USA).png`.

- **File name**: files are named after the ROM, not the game title, so the scanner matches them.
- **Media system folder**: resolved the same way the scanner resolves it (see the README), so `psx` downloads land in `Playstation/`.
- **Replacing**: downloading into a folder replaces that game's existing file there, including one with a different extension (a new `.png` replaces an old `.jpg`).
- **Format**: taken from the response's `Content-Type`, falling back to the URL.
- **Safety**: only real media files are saved. A "no media" answer is reported as an error rather than saved as a broken image.

## System matching

`backend/systems.py` maps ROM or media folder names to ScreenScraper system IDs, IGDB platform IDs, RetroAchievements console IDs and libretro thumbnail folders. `steam`, `windows` and `winxp` folders are PC Windows. Matching ignores case, spaces and punctuation, so `snes`, `SNES`, `sfc` and `Super Nintendo` all work. The IDs were checked against both APIs.

- If a filtered search finds nothing, RetroManager retries without the system filter.
- For an unrecognised folder name, add its alias to the right entry in `_SYSTEMS`.

## Configuration

Accounts, keys and options are set in the app, in **🧰 Tools › Settings**, and take effect when you save (see the README's *Accounts and keys*):

| Setting | Purpose |
|---|---|
| ScreenScraper developer ID, password, debug password | Developer credentials (identify the software) |
| ScreenScraper user name and password | Optional user account (identifies you) |
| IGDB client ID and secret | Twitch application credentials |
| RetroAchievements web API key | retroachievements.org › Settings › Keys. Without it the source is off |
| RetroAchievements user name | Whose earned achievements each game's page shows |
| SteamGridDB API key | steamgriddb.com › Preferences › API. Without it the source is off |
| libretro thumbnails | When they're used in bulk and library scrapes: see [Bulk scraping](#bulk-scraping) |
| Recognise ROMs by checksum | Hasheous on or off: see [Checksum matching](#checksum-matching) |

Without a ScreenScraper user account, requests use the anonymous quota, and ScreenScraper blocks anonymous use when it's busy. A free account removes most of the failures listed below.

## Troubleshooting

Transient failures (timeouts, busy servers, rate limits) are retried once automatically. The messages you might still see:

| Message | Meaning / fix |
|---|---|
| ScreenScraper didn't respond within 30 seconds | Its servers are slow; retry |
| closed the API to non-members | ScreenScraper is overloaded; add your user account in Settings or wait |
| daily quota is used up | Wait until tomorrow or add your user account in Settings |
| thread limit was reached | Wait a moment and retry |
| rejected the developer credentials / Erreur de login | Check the ScreenScraper developer credentials in Settings |
| found nothing for "…" | Shorten the search text: drop region tags, subtitles and punctuation |
| the source has no file for this media type | ScreenScraper lists the type but has no file for it; pick another |
| rejected the IGDB credentials | Check the IGDB client ID and secret in Settings |
| IGDB rate limit hit | IGDB allows 4 requests a second; retry |
| Add ... in Tools > Settings | That source has no account or key yet; add it in Settings |
| rejected the API key | Check the key for that source |
| doesn't cover this system | RetroAchievements or libretro has nothing for that system, or the folder name isn't in `backend/systems.py` |
| Steam rate limit hit | Steam allows about 200 requests per 5 minutes; wait a few minutes |
| Steam has no store page for that app | The game is delisted or region-locked |

The container log (`docker compose logs -f retromanager`) has the full response for every failure.

### Known limits

- **IGDB ranking**: IGDB's search ranking can put ROM hacks and fan games above the original. A result marked **ROM match** is the file itself; otherwise check the release year and platform before picking a result.
- **Steam endpoints are unofficial**: the store search and details routes aren't a documented API, so Valve could change them.
- **Previews use quota**: ScreenScraper media URLs go through its API, so opening previews in the popup (and match thumbnails in Bulk scrape) counts against the quota.

## API

Every route takes JSON and returns `{"success": bool, ...}`. On failure `error` holds the message shown in the UI.

### `POST /api/scraper/search` · `POST /api/igdb/search` · `POST /api/sources/<source>/search`

`<source>` is `retroachievements`, `steam`, `steamgriddb` or `libretro`.

```json
{ "name": "Super Mario World", "system_name": "snes", "rom_path": "Super Mario World (USA).sfc" }
```

`rom_path` is optional. With it, the game recognised from the file's checksum comes first with `"hash_match": true`.

ScreenScraper also accepts `system_id` (a ScreenScraper `systemeid`) in place of `system_name`.

ScreenScraper results:

```json
{ "id": "2144", "nom": "Super Mario World", "systemeid": "4", "systemenom": "Super Nintendo",
  "image": "<box art url>", "releasedate": "1991-08-13", "jeu": { "...": "full ScreenScraper object" } }
```

IGDB results:

```json
{ "id": 1070, "name": "Super Mario World", "cover_url": "https://images.igdb.com/...",
  "platform_names": "Super Nintendo Entertainment System", "releasedate": "19901121T000000" }
```

### `POST /api/scraper/game-info` · `POST /api/igdb/game-info` · `POST /api/sources/<source>/game-info`

ScreenScraper: `{ "game_data": <a search result> }` (no API call), or `{ "game_id": 2144, "system_id": 4 }`.

IGDB and the other sources: `{ "game_id": 1070 }` (libretro also needs `system_name`).

All return `metadata` with gamelist field names:

```json
{
  "name": "Super Mario World",
  "desc": "...",
  "genre": "Platform / Run & Jump",
  "developer": "Nintendo",
  "publisher": "Nintendo",
  "releasedate": "19910813T000000",
  "players": "1-2",
  "rating": 0.85,
  "media": { "box2d": "<url>", "wheel": "<url>", "screenshot": "<url>" }
}
```

### `GET /api/scrape-sources`

```json
{ "sources": [ { "id": "retroachievements", "label": "RetroAchievements", "available": false,
                 "hint": "Add your RetroAchievements API key in Tools > Settings to use RetroAchievements" } ],
  "hasheous": true, "libretro_mode": "fallback" }
```

### `POST /api/scraper/download-media` · `POST /api/igdb/download-media`

The two routes behave identically, and download media from any source.

```json
{
  "system_name": "snes",
  "rom_path": "./Super Mario World (USA).sfc",
  "game_name": "Super Mario World",
  "media_types": { "box2d": "<url>", "wheel": "<url>" }
}
```

- `media_types` keys must be media folders: `box2d`, `box3d`, `boxside`, `support`, `wheel`, `screenshot`, `screenshottitle`, `fanart`, `posters`, `images`, `mix`, `thumbnail`, `manuals`, `videos`.
- `game_name` is only used to name files when `rom_path` is missing.

```json
{
  "success": true,
  "saved_media": { "box2d": "Super Nintendo/box2d/Super Mario World (USA).png" },
  "errors": ["wheel: the source has no file for this media type"]
}
```

`saved_media` paths are relative to the media mount, the same form the rest of the app uses.

## TheGamesDB

Set the key in **Tools › Settings › TheGamesDB** (or `THEGAMESDB_API_KEY`). It's a source in the **Scrape** popup, searched by name and kept to the game's system where RetroManager knows TheGamesDB's number for it (`_TGDB_PLATFORMS` in `backend/systems.py`; a system that isn't there is searched on every platform). It isn't used by bulk scraping or the library scrape.

Every request counts against the key's monthly allowance: a search is one, and opening a result is two (the game, then its pictures). The lists that turn its genre, developer and publisher numbers into names are fetched once and kept in the data folder (`thegamesdb-names.json`) for a month. Its age rating (an ESRB letter) isn't a score, so Rating is left alone. A back cover and a banner are offered but start on **Skip**, having no folder of their own.
