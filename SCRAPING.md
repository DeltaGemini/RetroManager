# Scraping

RetroManager can pull metadata and artwork from **ScreenScraper** (screenscraper.fr) and **IGDB** (igdb.com, via Twitch).

## In the UI

1. Select a game and click **Scrape**.
2. Adjust the search text if needed, then click **Search ScreenScraper** or **Search IGDB**. Searches are filtered to the game's system when RetroManager recognises the ROM folder name (see [System matching](#system-matching)).
3. Click a result. Results show the release year and regions, and ROM hacks and mods are marked **Hack / mod** and listed after the originals. The **Compare Metadata** view shows each field, current against scraped. Tick the fields to import.
4. Under **Assign Media**, each image the game doesn't have yet is already set to its matching folder (IGDB: cover → Box 2D, first screenshot → Screenshot, first artwork → Fanart). Where the game already has that image, the card starts on **Skip** and shows **Current** and **New** side by side (**Compare** shows both full size); choose the folder to replace it. Videos start on **Skip** because they're large. Each folder holds one file per game, so if two images go to the same folder the first one wins.
5. Click **Apply Selected Changes**. Assigned media is downloaded straight away and the form is filled in, including any empty Image, Thumbnail and Video fields (what EmulationStation displays).
6. Click **Save** to write the metadata to `gamelist.xml`. Downloaded media is already on disk whether or not you save.

Media downloads one file at a time with a progress bar. If a search, lookup or download fails, a message at the top of the popup says why (see [Troubleshooting](#troubleshooting)); if some downloads fail, everything else is still applied and the popup stays open to list the failures.

## Bulk scraping

**Bulk scrape** (in the game list header) scrapes many games of one system at once, from ScreenScraper:

1. **Choose games.** Start from a group (Missing metadata, No description, No image in gamelist, All) and untick any you want to skip. Choose which media to download; videos aren't offered, because they're large and slow.
2. **Find matches.** Each game is looked up by its ROM file name, which ScreenScraper recognises for most No-Intro/Redump-named ROMs. If that fails or looks wrong, it falls back to a title search. Each result gets a confidence:

   | Confidence | Meaning | Ticked? |
   |---|---|---|
   | **Exact** | ScreenScraper recognised this exact ROM file | Yes |
   | **Likely** | The game's name closely matches the ROM's title | Yes |
   | **Unsure** | A game was found but the names differ | No |
   | **No match** | Nothing found | No |

   Matching takes 1–4 seconds per game and can be stopped at any time.
3. **Review.** Pick another result from the dropdown, or for Unsure/No match rows search a different name. **Needs attention** shows only the rows to check.
4. **Apply.** The gamelist is backed up once, then each ticked game gets:
   - **Empty fields filled.** Fields that already have a value are never replaced. A game without an entry gets its name from ScreenScraper.
   - **Missing media downloaded.** Types the game already has a file for are skipped.
   - **Image, Thumbnail and Video linked** in the gamelist where they're empty or broken.

Each media file is a ScreenScraper request, so a large batch uses a noticeable part of the daily quota; a ScreenScraper user account (`SCREENSCRAPER_USER`) raises it. If the quota runs out, the batch stops and says so, and everything applied so far is kept.

## Library scrape

**🧰 Tools › Library scrape** runs the same matching over every system in the background, without a review step: **Exact** and **Likely** matches are applied straight away (empty fields and missing media only), and **Unsure** and **No match** games are listed under **Needs a look** for you to scrape by hand. Optionally it also covers games that have metadata but lack some media. Games it has checked are skipped for 30 days. Details are in the [README](README.md#library-scrape).

Names from ScreenScraper and IGDB are put in the house name style (`Series: Subtitle`, see the README's Scan section) before they're shown or saved.

PC games (DOS and similar) are matched by their folder name rather than the program's file name.

## What each source provides

| Field | ScreenScraper | IGDB |
|---|---|---|
| name | ✓ (US → World → EU → … name) | ✓ |
| desc | ✓ English synopsis | ✓ summary |
| genre | ✓ first genre, English | ✓ all genres, comma-separated |
| developer / publisher | ✓ | ✓ |
| releasedate | ✓ first regional date, US preferred | ✓ first release |
| players | ✓ | — |
| rating | ✓ (out of 20, scaled to 0–1) | ✓ (out of 100, scaled to 0–1) |

Dates are converted to EmulationStation's `YYYYMMDDT000000`.

### Media

**ScreenScraper** results are already sorted into RetroManager folders, using the US image first, then World, EU, generic, UK, JP:

| ScreenScraper type | Offered as |
|---|---|
| `box-2D` | box2d |
| `box-3D` | box3d |
| `box-2D-side` | boxside (the spine, used by the Shelf) |
| `ss` | screenshot |
| `sstitle` | screenshottitle |
| `wheel-hd`, else `wheel` | wheel |
| `fanart` | fanart |
| `mixrbv2`, else `mixrbv1` | mix |
| `video-normalized`, else `video` | videos |
| `manuel` | manuals |

**IGDB** offers `cover`, `screenshot_1`–`screenshot_3` and `artwork_1`–`artwork_2`. Assign them to folders yourself (typically cover → Box 2D, a screenshot → Screenshot, artwork → Fanart).

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

`backend/systems.py` maps ROM or media folder names to ScreenScraper system IDs and IGDB platform IDs. Matching ignores case, spaces and punctuation, so `snes`, `SNES`, `sfc` and `Super Nintendo` all work. The IDs were checked against both APIs.

- If a filtered search finds nothing, RetroManager retries without the system filter.
- For an unrecognised folder name, add its alias to the right entry in `_SYSTEMS`.

## Configuration

Set these in `.env` (see `.env.example` and [Setup](README.md#2-configuration)). None are built in: without them, scraping says it isn't set up and everything else works.

| Variable | Purpose |
|---|---|
| `SCREENSCRAPER_LOGIN`, `SCREENSCRAPER_PASSWORD`, `SCREENSCRAPER_DEBUG_PASSWORD` | Developer credentials (identify the software) |
| `SCREENSCRAPER_USER`, `SCREENSCRAPER_USER_PASSWORD` | Optional user account (identifies you) |
| `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET` | Twitch application credentials |

Without a ScreenScraper user account, requests use the anonymous quota, and ScreenScraper blocks anonymous use when it's busy. A free account removes most of the failures listed below.

## Troubleshooting

Transient failures (timeouts, busy servers, rate limits) are retried once automatically. The messages you might still see:

| Message | Meaning / fix |
|---|---|
| ScreenScraper didn't respond within 30 seconds | Its servers are slow; retry |
| closed the API to non-members | ScreenScraper is overloaded; set `SCREENSCRAPER_USER` or wait |
| daily quota is used up | Wait until tomorrow or set `SCREENSCRAPER_USER` |
| thread limit was reached | Wait a moment and retry |
| isn't set up | Add the `SCREENSCRAPER_*` or `IGDB_*` variables to `.env`, then `docker compose up -d` |
| rejected the developer credentials / Erreur de login | Check the `SCREENSCRAPER_*` developer variables |
| found nothing for "…" | Shorten the search text: drop region tags, subtitles and punctuation |
| the source has no file for this media type | ScreenScraper lists the type but has no file for it; pick another |
| rejected the IGDB credentials | Check `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` |
| IGDB rate limit hit | IGDB allows 4 requests a second; retry |

The container log (`docker compose logs -f retromanager`) has the full response for every failure.

### Known limits

- **IGDB ranking**: IGDB's search ranking can put ROM hacks and fan games above the original. Check the release year and platform before picking a result.
- **Previews use quota**: ScreenScraper media URLs go through its API, so opening previews in the popup (and match thumbnails in Bulk scrape) counts against the quota.

## API

Every route takes JSON and returns `{"success": bool, ...}`. On failure `error` holds the message shown in the UI.

### `POST /api/scraper/search` · `POST /api/igdb/search`

```json
{ "name": "Super Mario World", "system_name": "snes" }
```

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

### `POST /api/scraper/game-info` · `POST /api/igdb/game-info`

ScreenScraper: `{ "game_data": <a search result> }` (no API call), or `{ "game_id": 2144, "system_id": 4 }`.

IGDB: `{ "game_id": 1070 }`.

Both return `metadata` with gamelist field names:

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

### `POST /api/scraper/download-media` · `POST /api/igdb/download-media`

The two routes behave identically.

```json
{
  "system_name": "snes",
  "rom_path": "./Super Mario World (USA).sfc",
  "game_name": "Super Mario World",
  "media_types": { "box2d": "<url>", "wheel": "<url>" }
}
```

- `media_types` keys must be media folders: `box2d`, `box3d`, `boxside`, `wheel`, `screenshot`, `screenshottitle`, `fanart`, `posters`, `images`, `mix`, `thumbnail`, `manuals`, `videos`.
- `game_name` is only used to name files when `rom_path` is missing.

```json
{
  "success": true,
  "saved_media": { "box2d": "Super Nintendo/box2d/Super Mario World (USA).png" },
  "errors": ["wheel: the source has no file for this media type"]
}
```

`saved_media` paths are relative to the media mount, the same form the rest of the app uses.
