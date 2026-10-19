# Changelog

Each version's big changes, then the bugs found and fixed since the version before. A release's page on GitHub shows its section of this file (`.github/workflows/release.yml`), so a version is tagged only once its section is here.

## Unreleased

(Renamed to the version, with its date, when it's released.)

### Big changes

1. **Only the systems on your phone**: in the phone app, the Console settings can hide the systems that have no games on this phone.

### Bugs fixed

- The Starship Panels themes: the header's elbow was empty on a phone (the theme hides the logo, and narrow screens hide the name). RetroManager's name is its title now, in tall capitals, always in the phone app and wherever a page has room beside its links.

## 2.5.1 (18 October 2026)

With the phone app 1.418213 (as in 2.5.0).

### Big changes

1. **Up-to-date foundations**: Flask 3.1, Werkzeug 3.1, lxml 6.1, Requests 2.34, Pillow 12.3 and Gunicorn 26 (the versions before were from early 2024; Werkzeug, Requests and Gunicorn have had security fixes since, Gunicorn's against request smuggling), and the pages compiled with Node 24 (Node 20 is no longer kept up). Flask-CORS is gone: nothing has used it since other sites were shut out in 2.4.0.
2. **The pages tested as the image builds them**: GitHub runs the browser tests a second time on the compiled pages, so one that only breaks once compiled is caught on every push, not at a release. The play, setup and sign-in pages' code is in files of its own now (`play.js`, `setup.js`, `login.js`), checked with the rest of the pages' plain JavaScript, and the sign-in page has a browser test.

### Bugs fixed

- The sign-in page: choosing an admin (to give the PIN) left everyone else's tile showing beside the PIN box; they're hidden, as they were meant to be.
- Fill the gaps: the row marked for the keys could slip to the next one down when a game's sources answered and a row above it went (one with nothing new to offer); the mark stays on its row.
- Fill the gaps: a number key pressed while a game was still being looked up was lost, or picked another tile (✨ Generate in place of the first source's picture); it's now held and picked when the sources answer, and a picture being made keeps its number, so the ones after it don't move.
- Tests on GitHub: the Fill the gaps keys test could fail on a slow machine, pressing a number before the sources had answered.
- Tests on GitHub: a Console test could fail on the compiled pages, reading the page's address just before it changed after going back to the first screen.

## 2.5.0 (18 October 2026)

With the phone app 1.418213.

### Big changes

1. **Achievements after a replace or a patch**: Replace with an updated ROM and Apply a patch say whether RetroAchievements still recognises the game (still, no longer, or now: a known hack's file), and the game's Achievements section goes by it.
2. **Adding a game fills it as Fill the gaps does**: from the game picked, then every other source in Fill the gaps' order for what that hasn't (a confident match only), another source's copy of a picture tried when one won't download, and the matches remembered for Fill the gaps. (Before, it had a shorter chain of its own: IGDB by checksum, then GameTDB, LaunchBox, TheGamesDB and SteamGridDB for pictures only.)
3. **TheGamesDB and SteamGridDB, failing, are left out for 15 minutes** in Fill the gaps and the Background scrape too (their allowances are small), unless you search them again yourself.
4. **Pages load lighter**: each page's code is one file (the library's was 31), the browser keeps the pages' files until they change rather than fetching them every time, and they're sent compressed. The library page's first load fetches 13 files and about 200 KB instead of over 40 and about 800 KB; after that, none.
5. **The Scrape popup is retired**: Fill the gaps is the one way to scrape, from a game's page as from Tools. (Its **Search one source by hand** link, and Scrape while a game's details were being edited, opened the old popup, which filled the edit form to check before saving; Fill the gaps applies what you choose, and lets you search any one source again under **Matched on**.) The server routes only it used are gone too: ScreenScraper's and IGDB's search, game-info and download-media, and `/api/sources/<source>/search` and `game-info` (see [API.md](https://github.com/DeltaGemini/RetroManager/blob/v2.5.0/docs/api.md) for what's there).
6. **More of the phone app's decisions tested** (`android/test.sh`, 47 checks from 24): what RetroArch's history says (a game started from a zip, a folder named in another case, a core used for another system), whether a game started from the app began, and which way a controller's stick points. Inside, the app is in smaller parts; it works as before.

### Bugs fixed

- Every Fill the gaps look-up cleared the Stats, Bookcase and Media viewer caches, so they were worked out again after any scraping; a look-up changes nothing, and now leaves them.
- Opening a game on the Timeline blanked the page: the Timeline didn't load the panel's ROM file section (since 2.3.0).
- A refused patch (for another ROM, damaged, or changing nothing), or a ROM Replace refused, stayed among the Add games page's uploads; the uploaded file now goes once it's been tried.
- A patch that changes nothing (an IPS patch writing bytes the ROM already has) made a duplicate game; it's now refused, saying so.
- The Console stayed on a game after **Apply a patch** made a new one from it; it now moves on to the new game, added to the list.
- Tests on GitHub: the phone app's tests didn't run (`android/test.sh` wasn't marked executable).

## 2.4.0 (17 October 2026)

With the phone app 1.417436.

### Big changes

1. **Keys in Fill the gaps' Choose step**: ↑↓ a row, 1–9 a candidate in it (they're numbered), ←→ another game, A apply.
2. **Made 3D boxes and spines are known as made**: the Media viewer counts them and **Make again n made** shows a fresh one beside each in Fill the gaps, to apply or not. Made and pasted pictures not applied are listed in Storage and cleared nightly.
3. **Background scrape, checked before anything changes**: it now runs Fill the gaps' look-up (every source in your order, remembered matches) over the systems chosen, on the server, and applies nothing. What it finds waits by system under **Found, to check**; **Review** opens Fill the gaps with those games looked up already, to check and apply. (The old ScreenScraper-only run, which applied matches it thought sure, is gone.)
4. **Tests for the phone app's decisions** (`android/test.sh`, run before each build and on GitHub), and lint for the Python (ruff).
5. **One uploader** for Add games and Replace with an updated ROM.
6. **The Tools menu in groups** (Fill and media, Library care, Playing, Setup), two columns on a computer and one that scrolls on a phone, so it no longer runs off the screen.
7. **Check this phone** lists the cores marked as not starting a game and the last games started from the app, with the path RetroArch was given beside the one its history has, and **Try every core again** clears the marks (app 1.417409).
8. **ROM patches** (a game's ROM file section, **Apply a patch…**): an IPS, UPS or BPS patch applied to the ROM, as a new game beside it or in its place; UPS and BPS patches checked against the ROM they're for and the result, an SNES copier header handled.
9. **Where you stopped**, in the browser: leaving a game keeps a save state of where you were (apart from your own), and Start offers to carry on from it, chosen already.
10. **Playing and Backlog on the Console**: the row of lists (now **Your lists**) has your Playing and Backlog games as tiles of their own, beside Favourites and the collections.

### Bugs fixed

- Security: any website could call RetroManager from your browser (CORS was open to every site), so with login off a page you visited could change your library or its settings; other sites are now refused, and a change a browser says came from another site's page is refused.
- Security: a media or page address could reach a folder beside RetroManager's own whose name began the same way (`/media2` beside `/media`).
- Security: a picture's address could make the server download from the home network (a router's page); only public internet addresses are fetched now, redirects included.
- Tapping a game's picture in the phone app opened it at full size, larger than the screen: it now opens over the page, fitted to the screen, and a tap or Back closes it (everywhere, not only on the phone).
- Made 3D boxes: a Game Boy Advance (or other) cover wider than tall laid its box down like an SNES box, at odd angles; only SNES and N64 boxes lie down now, and the boxes are drawn with flatter perspective.
- Phone app: every game of a system could show "Needs an emulator" though RetroArch had the core (GBA, with mGBA playing Game Boy games): a game started from the app that didn't show in RetroArch's history in time marked its core as not installed for that system, and after a few, all of them. A core RetroArch's history shows playing anything is now never passed over (app 1.417220).

## 2.3.0 (17 October 2026)

### Big changes

1. **Fill the gaps** (Tools, or a system's **Bulk** menu): one system's games (or games picked in the Media viewer, from any systems) and what each is missing; for the ones picked, every source's version of each picture and detail side by side, the first in your order picked already. Matches are remembered, so a game isn't looked up again. **Only what's missing** or **Everything ticked**, as a choice and as a switch while choosing.
2. **Manuals and videos** can be filled too (from ScreenScraper), opened with ⤢ to read or play beside the one the game has.
3. **Made here**: a Mix from the Mix generator, and a **3D box** or **spine** made from the game's cover (a keep case's rim, a jewel case's frame or a clamshell's edge; a made spine in the cover's colour, or black like the system's case with its band, with the game's logo along it). Made and picked for a game missing one that no source has.
4. **From the web**: each picture row opens a Google Images search for the game and that kind of picture; paste the picture (or its address), drop it in or choose a file.
5. **Scrape on a game's page** goes straight to choosing in Fill the gaps; the **Media viewer** opens Fill the gaps with the games it has picked, and each number in its "What each system is missing" table fills those games.
6. **Bulk scrape is retired** (Fill the gaps does the same and more); **Library scrape is now Background scrape**, the unattended one.
7. **A ROM's version** is noted with the game's other details, and changed in Edit like them (for ROM hacks and indie games); kept by RetroManager, not in gamelist.xml, which EmulationStation rewrites.
8. **Replace with an updated ROM** (a game's ROM file section): the new file takes the old one's name, so saves, save states and pictures still go with it; the old one is kept in Tools › Storage, and the versions it replaced are listed.
9. **Phone app 1.417153**: a ROM replaced in RetroManager is fetched again when next played, even if it's the same size; with **Keep games up to date** (📱 This phone, on to begin with), so are games put on the phone another way.
10. **Clearer Edit and Delete** buttons on a game's page: a drawn pencil with its name, and a drawn bin.

### Bugs fixed

- Playing in the browser loaded the browser's stored copy of a replaced ROM instead of the new one (EmulatorJS only checked the file's size).
- The phone app didn't fetch an updated ROM that was the same size as the old one, and never updated a game it hadn't fetched itself.
- EmulatorJS's ☰ menu button seemed to do nothing on a computer: a click could close the menu bar the mouse had just opened, and the bar hid itself after 3 seconds at the other end of the screen. It now opens the bar until pressed again.
- On computers without a touch screen, the play page had no menu button at all.
- Fill the gaps: the wrong-game **Search** button gave no sign it was searching.
- Fill the gaps: Previous, Next or another game in the list left the page scrolled down instead of at the top of that game.
- Fill the gaps: "Missing" counted kinds that weren't ticked; a game with a picture showed only the kinds it lacked, which looked like the other ticked kinds had been ignored.
- Fill the gaps: opened from a system's page before the systems had loaded, it showed the first system rather than that one.
- Fill the gaps: "Matched before" didn't update after applying until the tool was reopened.
- Fill the gaps: the larger picture view (⤢) could show the wrong game's picture.
- Fill the gaps: text rows were cramped (line spacing).
- Made 3D boxes: a PS1 cover, a little wider than tall, laid its jewel case down like an SNES box.

## 2.2.0 (16 October 2026)

### Big changes

1. **Media viewer**: one kind of media (box, Mix, logo, screenshot, manual, video...) for every game of every system, with a size slider, what each system is missing, and Generate Mix. Pick games and scrape them again, reviewing each game's picture beside ScreenScraper's with the match to change. (Replaces Missing media.)
2. **Duplicates**: games in the library more than once, by name and by identical files, in one list.
3. **Storage**: everything set aside (replaced pictures, duplicates, save backups, gamelist backups...) and the caches, with their sizes; compare an item with what's in the library now, put a gamelist copy back, delete for good. (Takes in Gamelist backups.)
4. **Saves tool**: thin each person's save states of a game to the newest few, and number them again.
5. **Reloading a page** comes back to the system and game that were open.
6. **Themes**: Starship Panels, Starship Panels · Blue and Starship Bridge · 1960s (fonts: Antonio and Michroma, SIL OFL).
7. **System pictures** in the theme menu: the Switch theme's, or tiles with system logos drawn in the theme's colours (fetched with `tools/fetch_system_logos.py`).
8. **Languages**: English and Cockney; more can be added as packs.
9. **Phone app**: updates fetch and install inside the app; a home-screen widget and the app icon's shortcuts for the last five games played, with intents (PLAY_RECENT, PLAY) for routines and automation apps.
10. **Phone app**: choosing whose unsorted saves are asks first, and taking over others' saves can be undone; the server's save date shows in the save question.

### Bugs fixed

- ScreenScraper pictures didn't download (and previews didn't load) when the account's password had #, & or + in it.
- "Dragon Warrior I & II" was taken to be the same title as "Dragon Warrior III".
- The Media viewer took around 14 seconds to open on a NAS (every picture file was checked first).
- The Media viewer cleared the picked games without asking when the kind of picture changed.
- Phone app: choosing whose unsorted saves are could take over every save on the phone without warning.
- Phone app: the widget's and app icon's games didn't change to the new person's when someone else signed in.
- Phone app: the widget's pictures were different heights, and the app icon's shortcuts left out the newest game.
- Starship Panels: the header's corner was drawn the wrong way round, and the Michroma font made the header overflow.

## 2.1.0 (15 October 2026)

### Big changes

1. **Console tiles** can be as wide as their picture (Console settings › Game tiles are).
2. **Documentation**: a short README, with the rest in pages under `docs/`, including how the server, browser, phone app and RetroArch fit together.

### Bugs fixed

- Console: Back from a game opened on the first screen (Continue playing, Recently added, Installed games) went to its system instead of back there.
- Collections: a game taken out of one stayed in its Console list until the page was reloaded; the checkboxes on a game's page could send their changes out of order.
- A game's title was squeezed beside its logo on a narrow screen.

## 2.0.1 (15 October 2026)

### Big changes

1. **Screenshots of made-up games**: the README's screenshots show a demo library of invented games, with names, descriptions and pictures drawn by `tools/make_demo_library.py`, so they show no one else's games. `tools/take_screenshots.py` takes them again.

### Bugs fixed

- None in this version.

## 2.0.0 (15 October 2026)

### Big changes

1. **The Android app**: plays the library in RetroArch, with save and save-state sync, offline use and a controller.
2. **Console page**: the collection as a games console's home screen.
3. **Playing in the browser**, with your saves.
4. **Profiles and login**, with a save set per person.
5. **First-run setup page**, and a library folder that needs no settings.
6. **Saves** kept in folders of their own, or beside the games.
7. **More scraping sources**: TheGamesDB, SteamGridDB, LaunchBox and GameTDB.
8. **RetroManager's own** system tiles, logo and icon.
9. **Licence and credits** (CREDITS.md).
10. **Releases** publish a Docker image (PCs and 64-bit Raspberry Pis) and the Android app.

### Bugs fixed

- The first release with a version number: there's no earlier version to compare with.
