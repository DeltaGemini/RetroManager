# The Library and its tools

Browsing and editing games, adding them, and every tool under **🧰 Tools**.

## Using it

1. Pick a system in the left sidebar. The count shows ROMs, and systems with missing metadata are highlighted. The header shows library totals and when this browser last scanned the system.
2. Pick a game. Games without a gamelist entry show a **Missing Metadata** badge. Region and version tags such as `(USA) (Rev 1)` are shown under the title.
3. The game's [details](#game-details) open. Click **✏** to change its name, facts, rating and description where they are, or **Scrape** to pull metadata and artwork from ScreenScraper or IGDB (see [SCRAPING.md](scraping.md)).
4. Click **Save** to write `gamelist.xml`. Scraped fields aren't saved until you do this. **Preview the gamelist.xml entry** (under **Gamelist**) shows exactly what Save writes.

Each game card shows the game's screenshot (or its title screen) behind the name. **🎨 Theme** in the header picks the site's colours on every page: Midnight (the original dark), Daylight (the original light), Black, Slate, Terminal, Sepia, Switch, Switch Light, and three after TV science fiction's starship computers: **Starship Panels** and **Starship Panels · Blue** (black, flat colour blocks with round ends, each column's heading an "elbow", pill buttons with black lettering, tall condensed capitals in Antonio; in oranges and lilacs, or steel blues and amber) and **Starship Bridge · 1960s** (square lit buttons in red, gold, blue and green, a striped console rule under the header, wide capitals in Michroma). Their fonts are in `frontend/themes/starship/` (SIL Open Font License). The menu's **System pictures** chooses what the systems' tiles show, for every page in that browser (the same choice as the Console's settings and the phone app's): RetroManager's **drawn tiles**, the **Switch theme pictures** (where they're installed), or **logos in the theme's colours**. That last draws each system's monochrome logo (from HVR88's [Monochrome Gaming Logos](https://github.com/HVR88/Monochrome-Gaming-Logos)) on the theme's own colours, so the tiles change with the theme: an elbow on the Starship Panels themes, a row of lit buttons on the 1960s bridge. The logos are their brands' trade marks and don't come with RetroManager: `python tools/fetch_system_logos.py` fetches them into `frontend/logos/`, and a system without one keeps its drawn tile. The choice is remembered in each browser. The two Switch themes follow the Switch Master EmulationStation theme: its colours, the Oxygen font, its logo in the header, hairlines under headings, a slim bar on the selected game and its star icons, and (Switch only) its background picture behind see-through panels. Their files, and their licence, are in `frontend/themes/switch/`. Themes are listed in `frontend/common/theme.js` and their colours are in `frontend/common/header.css`.

The same menu (and **Language** in the phone app's settings) picks the language: **English**, or **Cockney** for a laugh ("'Ave a Go", "Me Machines", "Gettin' Round To It"). Like the theme, it's remembered in each browser. A language other than English is a phrasebook in `frontend/common/language.js`: the interface's words (menus, buttons, headings, labels) are swapped as the page draws them, and only text that is exactly a known phrase changes, so game names, descriptions and anything you've typed stay as they are. A part of a page can opt out with `translate="no"`. To add a language, add it to `LANGUAGES` with its `PHRASES` (and `PATTERNS`, for phrases with a number in them), or keep it apart in `frontend/common/language-packs.js` (loaded just before, and empty as RetroManager comes); text it hasn't a phrase for stays in English.

**Systems** (left): the search box finds systems and also games in every system (by name, developer or genre; click one to open it). **Filters** narrows the list by maker (Nintendo, Sega, Sony, Atari, computers) and type (consoles, handhelds, computers, arcade), to systems missing metadata, or shows empty systems. Sort by name, most games, most missing metadata, maker (grouped) or console generation (grouped with its years, oldest first: handhelds sit with the home consoles of their time, and arcade, computers and anything else follow; `SYSTEM_GENERATIONS` in `frontend/index.html`).

**Games** (middle): the search box matches name, file, description, genre, developer, publisher and series. **Filters** opens a panel: show only (missing metadata, ROM missing, no image, no description, favourites), series, genre, decade, region (from the file name's tags), missing media, players, minimum rating, developer and publisher. Within a filter any ticked option matches; different filters must all match. Filters in use show as chips under the search box; click one to remove it. Series, genre, developer and publisher filters clear when you change system; the rest stay. Sort by name, oldest or newest first, rating, developer, series or file name (remembered in the browser).

| Key | Does |
|---|---|
| `↑` `↓` | Previous / next game in the list (also from the search box) |
| `/` | Jump to the search box (`Esc` leaves it) |
| `Ctrl`+`S` / `⌘`+`S` | Save the open game |

**Delete** removes only the gamelist entry by default. You can also tick the ROM file and its media (files named exactly after the ROM); deleting files asks you to type the game's name first.

If you switch game or system with unsaved edits, RetroManager asks whether to save, discard or keep editing.

**Auto-fill** (under **Gamelist**, while editing) fills an empty Image, Thumbnail or Video from the game's media files. Applying scraped metadata does the same.

**+** (or **⟳**, to replace) on a tile in the **Media** section picks a file. It's saved straight away, without Save, into the media folder named after the ROM (like scraped media, replacing that game's file in another format), and linked where the gamelist's image, thumbnail or video used that media type. A replaced picture can't be brought back.

On phones the app goes systems → games → details, with **‹ Back** under the header; the phone's own Back gesture works too. The header shows icons, with the current page's name.

The header's row below shows library totals, when this browser last scanned the system, and the keyboard shortcuts. **🧰 Tools** works on every page: on the Bookcase or Timeline it opens the library with that tool (`/?tool=health`, `scrape`, `media`, `history`, `saves` or `backups`).

### Game details

A game looks the same wherever you open it: beside the Library's game list, on the Console page, and in the popup the Bookcase and the Timeline show (`frontend/src/common/game-details.jsx`).

- **At the top**: the name and system, **▶ Play** where the game runs in the browser, **📖 Manual** (read in place) when it has one, the page's own buttons, and for admins **✏** (edit), **🗑** (delete) and **Scrape**.
- **The picture** is the Mix image unless you change **Picture:** under it (2D box, 3D box, image, screenshot, title screen, fan art or poster). The choice is for every game on every page, kept in this browser; a game without that picture shows another one it has.
- **Beside it** (below it when the panel is narrow): developer, publisher, release date, genre, players, rating, the favourite star, play status and collections, then the description.
- **ROM file**, folded and last, has the file's name, what the [ROM check](#rom-check) made of it and its SHA-1, MD5 and CRC32, each with **Copy**. A disc game, which the ROM check doesn't hash, lists its `.cue` and every track instead, with **Work out the checksums** (each file is read whole, then the result is kept). It also has the ROM's **Version** (shown with the developer and the rest too, and changed in **Edit** like them, for a ROM hack's or an indie game's version), as you note it (kept in `DATA_PATH/rom-versions.json`, not the gamelist, which EmulationStation rewrites), and **Replace with an updated ROM…** (admins): choose the new file and its version, and it's uploaded (in pieces, resuming if the connection drops) and put in under the old file's name, so the game's saves, save states and pictures still go with it. A different kind of file (a `.zip` for a `.nds`) keeps the old name with its own extension, and the gamelist follows. The old file is kept in `DATA_PATH/replaced-roms/` (Tools › Storage), and **Before** lists the versions it replaced. Not for disc games, which are several files. **Apply a patch…** (admins) applies an IPS, UPS or BPS patch, the way ROM hacks and translations come, to the game's ROM: **as a new game beside this one** (named as you choose, the base game left as it is, and its ROM file section saying what it was made from), or **in place of this ROM** (a hack's next version over the last, kept as Replace keeps it). UPS and BPS patches carry the checksums of the ROM they're for and of the result, so one for another ROM (another region or revision) is refused and the result is checked; IPS patches carry none. An SNES ROM with the 512-byte header some dumps have is patched without it when the patch is for a ROM without one. The uploaded patch file isn't kept: it's deleted once it's been applied or refused (its name is noted in the game's version record). After a replace or a patch (with a RetroAchievements key in Settings), RetroManager says whether RetroAchievements still recognises the game: still the same game, no longer recognised (so it won't earn that game's achievements: a patched or updated ROM often isn't a file RetroAchievements lists), or now recognised (a known hack's file); the game's Achievements section goes by it.
- **Series** (with IGDB set up) is a third such line: see [Missing in series](#missing-in-series).
- **Achievements** and **Saves** are one line each with a summary (`6 of 83 · 7%`, `3 files · latest 2 days ago`); click one to unfold it, and it stays that way for the next game.

**Editing happens in the panel itself**, on every page, for admins:

- **✏** turns the name, developer, publisher, release date, genre, players, rating and description into fields where they sit. **✏** and **🗑** become **Save** and **Cancel** until you're done. Leaving a game with unsaved changes asks first.
- **🗑** removes the game: its gamelist entry and, if you tick them, its ROM file and media (typing the name confirms).
- **Scrape** looks the game up and fills the fields for you to save. On the Console, Bookcase and Timeline it opens the game in the Library with the scraper ready.
- **Media** is a section like Saves: every picture, the manual and the video, each with **+** to add one or **⟳** to replace it.
- **Gamelist**, for admins, has what EmulationStation is told: which media the image, thumbnail and video use (changed while editing), a PC game's launch file, and a preview of the entry.

### Housekeeping

Every night (after 3 a.m., server time) RetroManager backs up its own data (settings, play statuses and collections, the ROM check's results, what scraping has already looked at) to `RetroGames/retromanager/backups/`, keeping the latest 14, and runs the ROM check on new and changed files. **Settings** shows the latest backup and has **Back up now**. The backups hold the same passwords and keys as the settings. A background scrape or ROM check cut short by a restart starts again by itself.

### Adding games

**➕ Add games** in the header (or **Add** in the game list, or `/import`) opens a three-step wizard that works on a phone as well as a PC:

1. **Choose files.**
   - **From this device:** pick or drop files. They upload in 8 MB pieces with a progress bar; if the connection drops, the upload retries and carries on where it stopped (choosing the same file again later resumes it too). The screen is kept awake while uploading where the browser allows.
   - **From the inbox folder:** anything copied to `RetroGames/inbox` on the NAS (over the network, Syncthing...). Put games in a folder named after the system (`inbox/snes/`) to skip choosing it.
2. **Check details**, one card per game:
   - **Grouping:** a `.cue` and the tracks it names are one game (missing tracks are pointed out); several discs of one game become one game with an `.m3u` playlist.
   - **System:** from the file extension, or for disc images (`.iso`, `.bin`, `.chd`…) from markers inside the file (GameCube, Wii, PlayStation 1/2, PSP, Saturn, Sega CD, PC Engine CD). Only systems you have folders for are offered.
   - **Match:** ScreenScraper looks the file up by name, size and MD5 checksum (files up to 1 GB), so a known dump is an **Exact** match whatever it's called. Exact and Likely matches are picked; search another name, or choose **Don't scrape**.
   - **Name:** ScreenScraper's (put in your house style), or type your own.
   - **Warnings:** games that look like ones already in the library, and files that already exist in the system folder (those can't be added).
3. **Add:** moves the files into `roms/<system>/` with their own file names, adds the gamelist entry, and fills it from the match: empty fields, media (choose which; videos aren't offered) and Image/Thumbnail links. The games then show in the library, Bookcase and Timeline.

Uploads are staged in `inbox/.uploads/` rather than under `roms/`, so half-finished files don't sync to other devices. Unzip archives before adding them. PC game folders (DOS) are best copied to `roms/dos/` directly, then added with Scan.

**Share to RetroManager:** RetroManager can be installed as an app (it has a web app manifest and service worker). Installed on Android, it appears in the share menu, so a downloaded ROM can be shared straight into the wizard. Browsers only allow installing and sharing on **HTTPS**, so this starts working once RetroManager is behind a secure address (for example a reverse proxy with a certificate); over plain `http://` the wizard works the same, you just pick files inside it.

### Library health

**🧰 Tools › Library health** runs every system's Scan at once (a few seconds) and shows a table of issues per system. **Review** opens that system with its Scan panel.

**Fix safe issues everywhere** runs only the fixes that can't lose anything, across all systems: **Fix names**, **Link media** and **Merge into disc**. Each system's gamelist is backed up first. Relinking, creating or removing entries, renaming, duplicates, multi-disc playlists and moving unused media stay per system, in the Scan panel, where you review them.

### Background scrape

**🧰 Tools › Background scrape** looks every chosen system's games up on the server, the way [Fill the gaps](#fill-the-gaps) does: every source in the order set there (matches remembered there are used), one game at a time. Close the panel and keep working (the [strip under the header](#background-tasks), on every page, shows progress and reopens it). **It changes nothing.**

- **Which games:** those missing any of the kinds ticked (pictures, manuals and videos, text), on every system or the ones chosen.
- **What it finds** waits under **Found, to check**, by system, with the kinds found. **Review** (or **Review all**) opens Fill the gaps on its Choose step with those games looked up already: check each and apply, as there. A game applied there goes from the list; **Leave** takes a system's off it without changing anything.
- Games looked up are skipped for 30 days, so a later run doesn't use the sources' quotas again (tick **Look again** to include them). What's found is kept in `DATA_PATH/fill-found.json`, and a run cut short by a restart carries on.

### Background tasks

While the Background scrape, the ROM check or series matching is running, a strip appears under the header on every page: the task's name, a progress bar, how far along it is and what it's working on now. Click it to open that task's tool (where **Stop** is). With more than one running, the strip shows one and **+1 more** unfolds the rest. When a task ends the strip says how it went (`49 filled, 9 to review`, or why it stopped) for most of a minute, then goes; with nothing running it takes no room. It's shown to admins.

Work that runs in the browser tab rather than on the server (Fill the gaps, uploads on the Add games page, Mix previews) isn't in it: that stops when you leave the page.

### Fill the gaps

**🧰 Tools › 🧩 Fill the gaps** (also a system's **Bulk ▾ › Fill the gaps...**) is for many games missing several things at once, from whichever sources have them.

1. **Games.** Every game of one system, with what each is missing of the kinds being filled, or **✓ Complete**, and whether it was matched before. **Show** narrows it to the games with gaps or the complete ones. Pick the games.
2. **What to fill.** Choose **Only what each game is missing**, or **Everything ticked** (what each game has too, beside every source's, to keep or replace; the same switch is on the next step). Tick the images (Box 2D, Mix, Logo, screenshots, cart or disc...), manuals and videos (from ScreenScraper; off to begin with, being large) and the text (description, date, developer, publisher, genre, players, rating), with how many of the picked games miss each. Put the sources in the order you trust them (one that isn't set up is greyed); the order and the choices are remembered in the browser. Then **Let me choose**, or **Fill from the order** without choosing.
3. **Choose.** Each game is looked up on every source at once. For each gap: what it has now (**Now: keep it**, when replacing) beside every source's version, with how sure that source's match is, the first in your order picked already (not one whose match is Unsure), and **Leave it empty**. ⤢ shows one large beside what the game has, stepping through the sources. A manual or video is a tile to open with ⤢: the manual read, or the video played, beside the one the game has. Details are each source's text to tap. The source marks at the top show each match; tap one if it's the wrong game, to pick another of its results or search a different name. The Mix row also has **✨ Generate one**: a Mix made by the [Mix generator](#generating-mix-pictures) from the pictures the game has, shown beside the sources' to pick. The **Box 3D** and **Spine** rows have one too, made from the game's cover: a spine in the cover's edge colour with the game's logo along it (for a disc game, a Mega Drive, or a cover whose edge is busy, black like the system's case, with its band), and a 3D box of the cover turned with its spine (the game's own, or a made one) on the left, or underneath for a landscape box (SNES, N64), in its case's rim for a keep case, jewel case or clamshell. Where no source has a Mix, Box 3D or Spine for a game missing one, one is made for it and picked already (one at a time, the game on screen first; a box or spine only for a game with a cover; **Apply** waits until they're made). Made boxes and spines are kept for a day in `DATA_PATH/box-staging/` until applied. **Keys:** ↑ and ↓ (or J and K) move between rows, the row marked and its candidates numbered; 1–9 picks one (pressed while the game is still being looked up, it's picked when the sources answer; one being made keeps its number); ← and → (or P and N) go to the previous or next game; A applies. Each picture row (and Manual and Video) also has **From the web**: **🔎 Search Google** opens a Google Images search for the game, its system and that kind of picture in a new tab; copy the picture you want there and paste it into the box (or drag it in, or choose a file), or paste its address. It's shown beside the sources' and picked, and replaces what's there only when you apply. A manual or video takes an address only.
4. **Done.** What was filled or replaced, and from where; then what no source had, or you left empty, to look for by hand.

**From a game's page:** **Scrape** opens Fill the gaps for that game, straight to choosing with everything ticked (its name too): what it has beside every source's version, and its gaps filled from the order. A kind it has that no source offers another of isn't shown. Scrape isn't offered while the game's details are being edited (save or cancel first). Scrape on another page (the Console's, say) opens the game here and does the same.

**With the Media viewer:** **Fill picked** there opens Fill the gaps with the games picked (from any systems: the list is grouped by system), that kind of picture ticked and **Everything ticked**, straight to choosing; closing it goes back to the viewer. Each number in the viewer's **What each system is missing** table has a **Fill** link, for that system's games missing that kind. The other way, **See them as pictures** on Fill the gaps' first step opens the viewer on the same system and kind.

The gamelist is backed up first; a picture replaced is kept in `DATA_PATH/replaced-media/`. **Matches are remembered** (`DATA_PATH/matches.json`) when they're Exact or Likely, or picked by hand: a game isn't looked up on that source again, which is quicker and spares the sources' daily limits. They follow a game when its file is renamed.

### Media viewer

**🧰 Tools › Media viewer** shows one kind of media (Box 2D, Mix, Wheel, Screenshot... and manuals and videos, as a tile saying the game has one) for every game of every system side by side, so wrong ones (another region's box, a different game's art) stand out. Games without it show as a tile with their name.

**What each system is missing** opens a table of how many of each system's games lack each kind; click a number to see those games. Pictures ScreenScraper, libretro and IGDB don't have are looked for at GameTDB (discs and cartridges), LaunchBox (if it's turned on in Settings), TheGamesDB and SteamGridDB (if their keys are set) (see [SCRAPING.md](scraping.md#many-games-at-once)). On **Mix**, **Generate Mix** makes one for the picked games from their own media (below), and **Regenerate n generated** makes RetroManager's ones again.

 Narrow it to a system, to games with or without the picture, or by name. Click games to pick them (Shift-click picks a run), then **Fill n picked**: [Fill the gaps](#fill-the-gaps) opens with them, showing every source's version of that kind (pictures, manuals and videos alike) beside the one each game has, to choose from. Replaced files are kept in `DATA_PATH/replaced-media/`. The slider beside **Pick all shown** sets the picture size. The kind of picture and the size you last used are remembered in the browser.

### Generating Mix pictures

A game without a Mix picture can have one made from the media it does have: its screenshot, box, cartridge or disc, and logo, laid out like the Mix pictures scrapers make. Nothing is fetched and nothing is invented; it only arranges pictures already in the media folders.

In **🧰 Tools › Media viewer**, choose **Mix** (and **Without a Mix** to see the games that need one). Pick the games and press **Generate Mix**:

1. **What can be made.** RetroManager counts the games that have everything (**Full**: screenshot, box, cart or disc, logo), those with a screenshot and a box or a logo (**Partial**), and those that **can't be made** (no screenshot, or nothing to go with it), listing the reason for each. Nothing is written.
2. **Previews** are drawn in the background into `RetroGames/retromanager/mix-staging/`, not the media folders.
3. **Review** the grid: **Approve** or **Reject** each one, or **Approve all**. Click a preview to see it large with the pictures it was made from, and to make it again another way: without the box, cart or logo, with the 2D box instead of the 3D one, or with the title screen instead of the in-game screenshot.
4. **Commit** puts the approved ones in the library as `media/<media system folder>/mix/<ROM name>.png`, and sets the gamelist's `<image>` where it was empty (the gamelist is backed up first). Rejected previews are thrown away, as are any left when you close the panel; previews left behind by a closed browser are cleared after a day.

A Mix that's already there is never replaced unless you tick **Replace**, except one RetroManager generated itself. Whatever is replaced is first put in a tarball in `RetroGames/retromanager/mix-backups/`.

Generated pictures are marked **generated** in the game's details. Which ones they are is kept in `RetroGames/retromanager/mix-generated.json` (template, its version, the pictures used and when), and written into each PNG as text (`mix_source: generated`). Uploading or scraping a Mix over a generated one removes the mark.

**Making them again.** After changing a template, or once a game has gained a cartridge or a better screenshot, the generated ones can be redone: **Regenerate n generated** in the Media viewer on Mix (for every system, or the one chosen). It's the same review as before; the ones you approve replace the old ones, which are backed up first. Scraped Mix pictures aren't included.

**The cartridge or disc** comes from the `support` media folder, which the **Cart / disc** media type fills when scraping (ScreenScraper `support-2D`). Games scraped before this existed have none until they're scraped for it, so until then they're Partial.

**Layouts are templates**: JSON files in `backend/mix_templates/`. Positions and sizes are fractions of the canvas (960 × 960 in `classic`, square like ScreenScraper's own Mix), so the size can change without the layout changing. `classic` follows that Mix's arrangement: the screenshot on a framed screen across the top, the box at the bottom left, the cartridge or disc in front of it, and the logo low on the right. The header of `backend/mix_generator.py` describes the format. To change a layout or add one without rebuilding, put a template in `RetroGames/retromanager/mix_templates/`: one with the same `name` replaces the built-in one, and a `defaults.json` there (`{"default": "classic", "systems": {"psx": "discs"}}`) chooses each system's template. `screenshot_scaling` is `sharp` (pixel art is enlarged pixel for pixel) or `smooth`; `screenshot_fit` is `contain` or `cover`.

Two previews are drawn at a time (`MIX_WORKERS`), which keeps a Raspberry Pi responsive.

### Play status, favourites and collections

At the top of each game's page in the Library:

- **☆ Favourite** sets the gamelist's `<favorite>`, which EmulationStation shows too.
- **Playing / Backlog / Finished** is the game's play status; click the one that's set to clear it.
- **📁 Collections** opens a checklist of your own lists: tick the ones this game belongs in, or name a new one at the bottom. A game can be in several. **Bulk › Add to a collection**, above a system's game list, adds many games at once, and **🧰 Tools › Collections** renames and deletes collections and removes games from them.

They show as icons on game cards and as Library filters (**Filters › Show only**, and **Collection**), as Bookcase shelves (**Shelves: Play status** and **Shelves: Collections**) and as a **Yours** row of Timeline filters.

Statuses and collections are kept in `library-state.json` in the data folder, keyed by system and ROM file name. They follow a game when RetroManager renames or relinks it (the Scan panel, the ROM check, a new launch file) and go when its ROM is deleted; a file renamed outside RetroManager loses them. They're also written as EmulationStation custom collections, `custom-<name>.cfg`, in `RetroGames/retromanager/collections/`, listing each ROM under the folder set in **Settings › EmulationStation** (`/home/pi/RetroPie/roms` by default). The Pi's **Sync To Server** script copies them into EmulationStation's collections folder; switch a new one on in EmulationStation under Start › Game Collection Settings › Custom Game Collections.

### ROM check

**🧰 Tools › ROM check** works out every ROM's checksum in the background and looks it up in the ROM databases (No-Intro, Redump, TOSEC, through hasheous.org) and on RetroAchievements. Nothing in the library is changed.

- **Summary:** per system, how many files are **Verified** (a known good dump), **Recognised** (listed somewhere, but not as a verified dump), a **Hack**, **Not recognised** (a hack nobody lists, a patched or trimmed ROM, or a bad dump) or **Not checked** (folders, disc lists, files over 1 GB).
- **Duplicates:** files with the same contents under different names, tidied in [Duplicates](#duplicates).
- **Name doesn't match:** files whose name is unlike the game the databases say is inside.
- It only looks again at files that are new or changed; **Check everything again** redoes the lot. Results are kept in `rom-index.json` in the data folder. It runs by itself every night (switch that off in **Settings › Housekeeping**), and a check cut short by a restart starts again.

**Name doesn't match** can be acted on: tick the files that really are misnamed and **Rename to match**. Each gets the database's name, and its gamelist entry, media, saves, save states, play status and collections follow. A file is left alone if one with that name already exists (it's then a duplicate). Don't tick a different edition or translation of the same game: its name is right as it is.

An empty ROM file (0 bytes: a download or copy that failed) shows on **Library health** and in the system's Scan panel, where it can be moved out of the library.

Once it has run, each game's page shows a **ROM file** section (status and checksums), game cards show 🏆 with the number of achievements or the percentage earned, and the Achievement overview matches games by checksum.

### Stats

**📊 Stats** in the header (or `/stats`) adds up the library: totals and coverage, games by release year, system, generation, manufacturer, genre, franchise, developer, publisher and decade, the best-rated games, your play statuses and collections, achievement progress and the ROM check's results.

### Manuals

A game with a manual (a PDF in its `manuals` media folder, which scraping can download) has a **📖 Manual** button in its [details](#game-details), on every page, which opens it in place.

### Achievement overview

**🧰 Tools › Achievement overview** lists every game your RetroAchievements user (Tools › Settings) has earned a RetroAchievements achievement in, ranked by completion, with the overall percentage and totals above.

- **Recent unlocks** lists the latest 60 achievements earned, newest first. The Stats page charts the running total month by month.
- **Other people:** add them in **Settings › RetroAchievements › Other people** as `name=user name` pairs (`alice=AliceRA, bob=BobRA`). A picker then appears here and in each game's Achievements section. The trophies on game cards are always the main user's.

- **Rank by** most complete, closest to finishing, most earned, or earned most recently. **Only games in the library** hides the rest.
- Each row shows the percentage, earned out of total (and how many in hardcore), when one was last earned, and any award (Beaten, Completed, Mastered).
- A game that's in the library opens its page; any other opens on RetroAchievements. Games are matched by the ROM's checksum where its page has been opened before, otherwise by name on the same console, so a game named very differently may show as not in the library.
- Kept for 5 minutes; **Refresh** fetches it again.

### Missing in series

Which other games are in a game's series, which of them you have, and a list of the ones you want. The lists are [IGDB](https://www.igdb.com/)'s, so this needs its client ID and secret in **Tools › Settings**.

- **In a game's [details](#game-details)**, on every page, a **Series** row says how much of the series you have (`21 of 47`). Unfolded, it lists every game in release order with its cover, year and platforms: the ones you have are solid and link to your copy, the rest are faint, each with **☆ Want** and **✕** (not interested, which hides it and leaves it out of the count). **Hide a platform…** does that for everything on one platform within the series (arcade, mobile...).
- **🧰 Tools › Missing in series** lists every series the library has games from, most complete first, each unfolding to the same list, and has the **Want list** in one place.
- **Not found** in the tool lists the games IGDB had nothing for under their name, each with **Find it** to search and pick the right one.
- **Matching.** Each library game is matched to an IGDB game by its name and system (so *Sonic the Hedgehog* on the Master System and on the Mega Drive are different games, and a fan hack isn't taken for the original). A game is looked up the first time its details are opened; **Match the library** in the tool does them all in the background, then fetches each series' list (about a quarter of an hour for 600 games the first time, as IGDB allows four requests a second). New games are matched each night with the rest of the housekeeping, and a run cut short by a restart carries on by itself. **Wrong game?** under a Series list searches IGDB so you can pick the right one.
- **What's listed.** IGDB's *series* for the game where it has one, otherwise its broader *franchise* (which also takes in games the characters merely appear in). Originals, remakes, remasters and expanded editions each count as a game; ports, bundles, DLC and packs don't, and a port you have counts as having the game it's a port of. All platforms are included.
- It only reports: nothing is downloaded. Everything is kept in `series.json` in RetroManager's data folder (`backend/series_index.py`), which the nightly data backup includes.

### Play history

**🧰 Tools › Play history** shows what's been played, from when each game's saves and save states were last written: recently played (for everyone, or one person), and per-system counts for the last 30 days and ever. Play counts from the gamelists are shown too if EmulationStation writes them (it currently doesn't).

<a id="saves-tool"></a>
### Saves (tool)

**Where saves are kept.** RetroManager looks for saves and save states where RetroArch puts them. **Tools › Settings › Saves** says which of two ways that is (the first-run page suggests one from the files it finds):

- **In folders of their own**, `saves/` and `savestates/` (sorted by system, by core or not at all): what RetroArch does unless told otherwise, and Batocera, EmuDeck and the like. This is the only way each person can have their own saves (see [PROFILES.md](profiles.md)).
- **Beside the games**, in the ROM folders (`roms/snes/Game.srm`, `roms/snes/Game.state1`): RetroPie's way, and RetroArch's "write saves to the content directory". Saves are then everyone's: browser play, the phone app and the Saves tool all use the shared set whoever is signed in, profiles keep their own favourites and play status only, and Library health doesn't offer to move saves out of the ROM folders. The browser's own save states (which RetroArch can't load) still go in `savestates/<system>/Browser/`.

**🧰 Tools › Saves**:

- **Sync conflicts:** when Syncthing keeps two versions of a save (`… .sync-conflict-<date>-<device>.srm`), both are listed with their times, sizes and state screenshots. **Keep this** gives that version the normal name so the emulator loads it; the others move to `save-backups/conflicts/<time>/`, never deleted.
- **Backups:** zip everything, or one system, with or without save states, into `save-backups/zips/` (in the background), then download or delete them. A single game's saves download from its Saves section (**Download all (zip)**).

### Duplicates

**🧰 Tools › 👯 Duplicates** lists every game in the library more than once, found two ways: **Same name** (the same title apart from region and version tags, or the same gamelist name: the check in each system's Scan) and **Identical files** (the same contents, even under different names or in different systems: found by the [ROM check](#rom-check), once it has run). A group found both ways is marked with both. Narrow it to a system, pick the copy to keep in each (suggested: the one with an entry, more media, more plays and a USA, Europe or World tag), tick the games to tidy and **Move extra copies aside**. They go to `RetroGames/retromanager/duplicates/<system>/` (with a `.cue`'s tracks; nothing is deleted, see [Storage](#storage)), their gamelist entries are removed, and the kept copy takes over their play status and collections, and for a same-name group their details and any media it lacks. Logged in `duplicates/moved.log`.

### Storage

RetroManager sets things aside rather than deleting them. **🧰 Tools › 🧹 Storage** shows how much room each kind takes: pictures replaced by scraping (`DATA_PATH/replaced-media`), gamelist backups (each system's `gamelist_<date>.xml` and Syncthing conflict copies, and `DATA_PATH/gamelist-backups` from changes to every gamelist), duplicate games the duplicates tool moved out (`DATA_PATH/duplicates`), saves and states moved out of the way (`SAVE_BACKUP_PATH`: thinned states, sync conflicts, saves replaced while playing, clean-ups, save zips), Mix pictures replaced by generated ones, unfinished Mix previews and the nightly copies of RetroManager's own data, plus two caches that are made again when needed (small pictures, and disc games zipped for the browser).

Each area can delete everything older than a week, a month, 3 or 6 months or a year, or everything. Open an area to see its items (each dated folder, or each file), with their dates and sizes, and tick some to delete just those. You're asked first, with how much it frees; deleting is for good. What was deleted is noted in `DATA_PATH/storage-cleanup.log`. Only admins can delete.

**Compare** beside an item shows its files next to the library's own: the same path in the media, saves or save states folder (a picture in another format counts), the system's `gamelist.xml` for a gamelist copy, or the copy kept for a duplicate game. Pictures are side by side; each file is marked the same as now or different, or not in the library now. For a gamelist copy, **Show what's different** lists what putting it back would change, entry by entry (games it would bring back or remove, and each changed field, now → then), and **Put this copy back** does it (the gamelist now is backed up first); a text file shows its changed lines. A system's settings button opens Storage on that system's gamelist backups.

### Saves

The **Saves** section of a game lists its in-game saves and save states:

- **One group per person** (`savestates/<person>/…` and `saves/<person>/…`), newest first, showing the slot, when it was saved, size and path. States that RetroArch saved with a screenshot show it; click to enlarge.
- **In-game saves (shared)**: `saves/<system>/…`, which isn't split by person.
- **Old save states, not in a person's folder** (collapsed): anything in `savestates/<system>/…` or other loose folders.

Files are matched by name: the ROM file name (or its title without tags) followed by `.srm`, `.sav`, `.dsv`, `.state`, `.state<N>`, `.state.auto` and similar. Syncthing conflict copies are included and marked (resolve them in [Tools › Saves](#saves-tool)). Emulator-named folders such as `mGBA/` are searched too. Saves named by game ID (PSP `SAVEDATA`, GameCube memory cards) can't be matched to a ROM and aren't shown.

### Achievements

With a RetroAchievements API key set in Tools › Settings, each game's page in the Library has an **Achievements** section under Saves:

- **Completion:** the percentage earned, a progress bar, the number earned out of the total, points, and how many were earned in hardcore mode. These are for the RetroAchievements user in Settings; without one only the list is shown.
- **The list:** every achievement in RetroAchievements' order with its badge, description and points. Earned ones are in colour with a green outline, a tick and the date; the rest are dimmed with the locked badge. **Earned** and **Not yet** filter it; the first 12 show until you click **Show all**.
- **Matching:** the game is found from the ROM's checksum (see [SCRAPING.md](scraping.md#checksum-matching)), so the file's name doesn't matter, and the answer is remembered in `RetroGames/retromanager/retroachievements/rom-games.json`. A ROM RetroAchievements doesn't recognise says so, with **Check again**. PC game folders and files over 1 GB can't be matched.
- Progress is kept for 5 minutes; **Refresh** fetches it again.

### Scan

**Scan** in the game list header checks the selected system and lists what it finds, each with a fix you can apply to all or selected items:

| Section | Fix |
|---|---|
| Multi-disc games without a playlist | **Create .m3u**: writes `<game>.m3u` listing the discs (`… (Disc 1).cue`, `… (Disc 2).cue`) next to them, and makes it the game's one entry: the disc entries' details are kept and disc 1's media is renamed to match. Swap discs from the emulator's menu. Disc files aren't moved. |
| PS3 game folders not named .ps3 | **Rename to .ps3**: renames `Game/` to `Game.ps3/` so the folder is one game (see [ROMs](setup.md#roms)). Nothing inside changes. A gamelist entry pointing inside it (its `EBOOT.BIN`, usually named "Eboot") becomes the folder's entry, named after the folder. A folder still being copied (anything in it changed in the last two minutes) is marked and can't be renamed, since that would break the copy; one with no `PARAM.SFO` or `EBOOT.BIN` is marked unfinished and left unticked. |
| Saves inside the ROM folder | **Move out of roms**: saves and save states belong only in the top-level `saves/` and `savestates/` folders. Ones found next to ROMs (an emulator whose save folder setting is missing) move to `save-backups/in-rom-folders/<time>/<system>/`, where nothing syncs them. PC systems are skipped (their game folders keep their own saves). |
| Possible duplicates | The same game more than once (same file name apart from tags, or the same gamelist name). **Open Duplicates** tidies them in [Duplicates](#duplicates). |
| Names missing their first letters | **Fix names**: an entry whose name is its ROM file name (or that name without tags) with the first 1–2 characters cut off (a Skraper glitch, e.g. `arry Potter` for `Harry Potter`) gets them back. Nothing else changes. |
| Names not in house style | **Rename**: series and subtitle split by a colon, later dashes kept (`Star Wars - Rogue Leader - Rogue Squadron II` → `Star Wars: Rogue Leader - Rogue Squadron II`); `Legend of Zelda, The - X` → `The Legend of Zelda: X`; region, language, revision and 3DS product-code tags removed; Title Case (small words like *of*, *the*, *and* lower case; existing capitals such as `NBA`, `II`, `WarioWare` kept; ALL CAPS names converted); `Pokemon` → `Pokémon`. A known series with no dash before its subtitle (`Star Wars Episode I - Racer`) gets the colon too; add series with `NAME_STYLE_SERIES=Series One,Series Two`. Untick exceptions before renaming. Scraped names and new entries use the same style. Rules live in `backend/name_style.py`. |
| Disc track files listed as games | **Merge into disc**: folds gamelist entries for a disc's track files (the files its `.cue` names, e.g. `… (Track 03).bin`) into the `.cue`'s entry, copying any details the disc entry lacks. Files aren't touched. |
| Entries pointing at a wrong file name | **Relink**: points the entry at the ROM with the nearly identical name and renames media saved under the wrong name. Catches Skraper's habit of dropping the first letter (`./ario Kart Wii.iso`). Suggestions need the same extension and folder, and the same numbers in the name, so *Part 1* never pairs with *Part 2*. |
| Media not linked in the gamelist | **Link media**: fills empty or broken `<image>`/`<thumbnail>`/`<video>` |
| ROMs without a gamelist entry | **Create entries**: adds an entry named after the file, with media linked |
| Gamelist entries with no ROM | **Remove from gamelist**: deletes the entry only, never files |
| Media files nothing uses | **Move to _orphaned**: moves files to `<media system folder>/_orphaned/<type>/` so they can be restored |

Every change to `gamelist.xml` first saves a backup next to it as `gamelist_YYYYMMDD_HHMMSS.xml`. Compare and put them back in [Tools › Storage](#storage) (or from the system's settings button).
