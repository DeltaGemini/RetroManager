# Changelog

Each version's big changes, then the bugs found and fixed since the version before. A release's page on GitHub shows its section of this file (`.github/workflows/release.yml`), so a version is tagged only once its section is here.

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
