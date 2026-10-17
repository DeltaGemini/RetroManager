# Console, Bookcase, Timeline and playing in the browser

The pages for looking through the collection and playing it.

## Console

**🕹️ Console** in the header (or `/console`) shows the library the way a console does, after the Switch Master theme's system screen: rows of square tiles.

- **Continue playing**, first, is the dozen games played most recently (going by their saves and save states). Enter (or **A** on a controller) starts one straight away where the browser can play it; **E** (or **X**) opens its details instead, as a click does.
- **Recently added** is the dozen newest files.
- **Favourites and collections**: Favourites and each collection with games in it are tiles of their own, opening the same game screen as a system, with games from every system together. **🎲 Surprise me** beside them opens a game picked at random (one the browser can play, where there is one).
- **Systems**: big tiles in one row, or with **View** a row per console generation or per maker. **Sort** is the Library sidebar's. **Tiles** chooses which of a game's pictures its tile shows (the Mix, a box, the logo, a screenshot...), kept in this browser.

Left and right (arrow keys or A and D) move along a row, up and down (or W and S) between rows, and Enter or a click opens a tile. On a touch screen, putting a finger on a tile chooses it (so dragging a row along shows what's under your finger) and a tap opens it. The chosen tile's name is in a bubble under it: a game's with its console's picture, a system's or a list's with how many games it has. Pointing at a tile doesn't choose it, so moving the mouse across a row doesn't send it scrolling.

**A game controller** works on this page: the D-pad or left stick moves, **A** opens or plays, **B** goes back, **X** edits (or shows a recent game's details), the shoulder buttons page through a game list and Start plays. The line at the bottom shows the controller's buttons once one is connected (press a button on it first: browsers only notice a controller then).

A system opens on the same game list the Library has (each game's logo over its screenshot, with search, **Filters** and **Sort**), beside the chosen game's [details](library.md#game-details). It's for browsing and playing, so it has none of the Library's Scan, Bulk or Add; a game is edited in its details (✏, or E), and the Library's **🕹️ Open in Console** comes back. The address follows what's open (`/console?system=<folder>&game=<rom path>`). On a phone the list and the details take turns.

**The game list's keys**, on both pages: up and down (arrow keys or W and S) choose a game, Page Up, Page Down, Home and End jump, Enter plays it in the browser where that's possible (otherwise it opens it for editing), **E** edits it, `/` jumps to the search box. In Console, Esc, Backspace or left goes back to the systems. Each game the browser can play has a round **▶** button at the right of its row, which starts it straight away.



## Bookcase

**📚 Bookcase** in the header (or `/shelf`) shows the collection as a bookcase, one shelf per system (or per franchise, generation or manufacturer), without changing the library page.

- **Boxes** are sized like the real box or case for that system (`BOX_SIZES` in `frontend/shelf.html`), so SNES boxes stand tall and PlayStation jewel cases are short and thin. Thin cases (DVD-style cases for PS2, GameCube, Wii, PS3 and PSP, plus DS, 3DS, PlayStation and Switch) are drawn larger than life, in proportion, until the spine is wide enough to read the game's name (`READABLE_SPINE_PX`), up to 1.5 times their real size.
- **Shelves** (remembered in this browser) chooses what each shelf holds:
  - **Consoles**: one per system, in name order. A console's nameplate is a link that opens it in the Library. **Consoles by generation** puts them in generation order with a heading over each.
  - **Franchises**: one per series (the Timeline's series, from the part of the name before the colon), in name order, then **Other games** for everything that isn't in one.
  - **Generations**: one per console generation, then Arcade, Computers and Other.
  - **Manufacturers**: Nintendo, Sega, Sony, Atari, Computers, Other.

  A shelf that mixes systems keeps each box its own size. Generation and manufacturer shelves keep each system's games together; a franchise's shelf runs in the chosen sort order (**Sort: Year** puts a series in release order). Generations and manufacturers are the Library's (`frontend/common/systems.js`); series detection is `frontend/common/series.js`.
- **Spines** use the game's `boxside` image. Download spines with the **Spine** media type in the Scrape popup or Fill the gaps (ScreenScraper `box-2D-side`). Without one, the spine shows the left edge of the cover with the title down it.
- **Hover** (or keyboard focus) turns the box to face you: it widens to its Box 2D cover, the boxes beside it slide over to make room, and the game's name and year show underneath. Boxes without a cover enlarge the spine instead.
- **Click** (or tap, or Enter) pulls the box out: it slides up out of the shelf, leaving a gap, and swings towards you. Then the game's [details](library.md#game-details) open in a popup. **Put it back** (or Esc) slides it back into its gap. With reduced motion switched on, the card opens straight away.
- **Keyboard:** ← → along a shelf, ↑ ↓ between shelves, Enter opens.
- **⚙ Options › Bookcase** changes what the bookcase is made of: Mahogany, Oak, Walnut, Ebony, White, Neon arcade or Frosted glass (see-through panes over a blurred wash of the site theme's colours). It's separate from the site theme, and remembered in this browser.
- Shelves are in system-name order. Pick one system from the system menu (remembered in the browser), or show all.
- Search dims boxes that don't match and hides shelves with none. By default only games with a gamelist entry are shown.

- **⚙ Options** (remembered in the browser):
  - **Preload pictures:** fetches every shown game's cover (the hover picture) and details picture in the background, 4 at a time, with progress in the menu, so hovering and opening are instant.

Images are served as small WebP thumbnails, made on first use and kept in `THUMB_DIR` (`/data/thumbs` in docker-compose.yml, so they survive rebuilds). Their addresses carry the source file's change time, so browsers keep them for a year and still pick up new art straight away.

## Timeline

**🕰️ Timeline** in the header (or `/timeline`) puts every game on one timeline by release year, as covers with a coloured edge for the system family (Nintendo, Sega, Sony, computers, Atari).

- **Layout:** each year's covers stack up from the axis and spill into more piles to the right, so the page stays one screen tall and scrolls sideways (the mouse wheel scrolls it too). Years without games are thin gaps. **Decades** switches to smaller covers grouped by decade; the **'90 '00 …** buttons jump along. Games without a release year sit in an **Unknown** column at the end.
- **Filters:** tick console generations (**Era**), systems and series; everything else fades (or disappears, with **Hide others**). Search works the same way. Filters are kept in the address, so a view can be bookmarked (`/timeline?gens=5&series=star wars&systems=n64`).
- **Series** come from the part of the name before the colon, so house-style names group themselves: `Star Wars: Rogue Squadron` is in *Star Wars*. Sequel numbers come off (`Castlevania II: …` is *Castlevania*), and names without a colon join a series they start with (`Pokémon Snap` is in *Pokémon*). A series needs two games; the twelve biggest are shown, **All series** lists the rest.
- **Series line:** a picked series is joined by a line in release order, each cover numbered, and the timeline scrolls to its first game. Several series get a line each, in different colours.
- **Hover** shows the name, year and system; **click** opens the game's [details](library.md#game-details) in a popup.
- By default only games with a gamelist entry are shown.

## Playing in the browser

**▶ Play** on a game's page (and on its Bookcase card) opens the game in the browser, using [EmulatorJS](https://emulatorjs.org).

- **Which games:** NES, SNES, N64, Game Boy / Color / Advance, DS, Virtual Boy, Master System, Mega Drive, Game Gear, 32X, SG-1000, PlayStation, Atari 2600 / 5200 / 7800, Lynx, Jaguar, ColecoVision, PC Engine, Neo Geo Pocket, WonderSwan, C64, Saturn and arcade sets. A disc's `.cue` is sent with its track files. Sega CD, 3DO, PC Engine CD, Famicom Disk System and Neo Geo play once their BIOS file is in the BIOS folder (`RetroGames/BIOS`, mounted at `/bios`); PlayStation uses its BIOS if one is there. Multi-disc playlists (`.m3u`) and `.7z`/`.rar` archives aren't offered.
- **Saves:** choose whose save to use (**Play as**). That person's battery save, `saves/<person>/<system>/<rom>.srm` (`.sav` on the DS), is loaded when the game starts and written back within 20 seconds of the game saving. It's the same file the Pi uses, so don't play the same game in both places at once. The first time a play session changes a save, the old file is copied to `save-backups/browser-play/<date>/`.
- **Save states:** the emulator's save state and load state buttons keep one state per game and person on the server, in `savestates/<person>/<system>/Browser/` (the one before it is kept as `.bak`). They're the browser emulator's own; the Pi can't load them.
- **Touch controls from RetroArch overlays:** on the play page, **Touch controls** (before Start) swaps EmulatorJS's own touch pad for a layout made for RetroArch: Game Boy Advance (also the Game Boy's), Super Nintendo, and two for the DS (controls below the screens, or between them, for which the core is asked to leave a gap of the right height), which were made by hand; and NES, Master System and Game Gear, Mega Drive (six buttons), PlayStation and Nintendo 64 (thumbstick first, with the C buttons), written in the same style by `tools/make_overlays.py`. On a touch screen a system's own layout is chosen by itself; the choice is remembered per system in the browser. They behave as in RetroArch: the portrait or landscape overlay to suit the screen, sliding from one button to the next, the buttons that switch to a thumbstick or to a left- or right-handed arrangement, and fast forward, save state (the server-kept one, with a person chosen), EmulatorJS's menu and exit. Touches elsewhere go to the game, so a DS's touch screen still works. The layouts are the `.cfg` files in `frontend/overlays/` with their images in `frontend/overlays/images/`, read as they are by `frontend/play-overlay.js`; to add one, put its `.cfg` and images there and list it in `layouts.json` (`systems` names the EmulatorJS systems it's the usual one for).
- **Full screen:** on a phone the game takes the whole screen when you press Start, and the bar is put away; the round **☰** in the corner brings it back. On a computer, **⛶ Full screen** in the bar does the same. (An iPhone's browser can't go truly full screen, so there it only puts the bar away.) The **Back** link, the layouts' exit button and, on a controller, **Select and Start held together for a second** all leave the game for where it was started from: the Console page or the Library.
- **Sending a moment to the Pi:** with a person chosen, **Send to the Pi…** in the bar writes the emulator's state where RetroArch on the Pi looks for that person's save state for the game: as the auto save state (what the Pi starts from, if it's set to load those) or as slot 1 to 5. A state already there is copied to the save backups folder first. RetroArch only loads it on the same core the browser used, which the message says if the Pi's other states for the game came from a different one. The browser's cores: FCEUmm (NES), Snes9x, Gambatte (Game Boy), mGBA (Game Boy Advance), melonDS (DS), Mupen64Plus-Next, PCSX ReARMed, Genesis Plus GX (Mega Drive, Game Gear) and SMS Plus (Master System); starting from a Pi save state uses the core that made it instead.
- **Save states from the Pi:** a game with RetroArch save states (the Pi's, or any RetroArch's) lists them under **Or carry on from a save state made on the Pi**, newest first with their screenshots. Pick one and press **Start**: the game starts on the emulator core that made the state, the state is loaded, and the line at the top says whether it took. A state only loads on the same core, at the same version or a newer one, so it's checked once the game is running; one that doesn't take leaves the game at its start. Tested with real states: Nestopia (NES), Snes9x (SNES), Genesis Plus GX (Master System, Mega Drive, Game Gear), mGBA (Game Boy, Game Boy Color and Game Boy Advance; a state from a newer mGBA than the browser's needs EmulatorJS's nightly build: set **Where EmulatorJS is fetched from** in Settings to `https://cdn.emulatorjs.org/nightly/data/`. Each address keeps its own copy of the emulator, so switching back is clean), Mupen64Plus (N64), DeSmuME (DS) and PCSX ReARMed (PlayStation). States from cores the browser doesn't have (Beetle PSX, Stella, PPSSPP, Dolphin and others) are counted but can't be used. A save state also brings back the in-game save as it was then, and with a person chosen that is written back like any other save (the old file is backed up first). While a game is running, **Load a Pi save state…** in the bar jumps to any of them that the running core made (the others say which core they need, and are picked before Start). The Pi's save states are only read (`backend/pi_states.py` unpacks RetroArch's compression and container).
- **The emulator** is fetched from EmulatorJS's server the first time each part of it is needed and kept in `RetroGames/retromanager/emulatorjs/`, so a system that has been played once plays again without the internet. **Settings › Playing in the browser** sets where it's fetched from.
