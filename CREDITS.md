# Credits

RetroManager's own code, its drawn system tiles (`frontend/tiles/`), its logo and
the Switch colour themes' night sky (`frontend/open/`) and its icon (`frontend/icons/`) are under the MIT licence in
[LICENSE](LICENSE). What follows is other people's work that comes with it, or
that it fetches or talks to, and the terms each is under.

## Comes with RetroManager

| What | Where | From | Terms |
|---|---|---|---|
| Touch-control button pictures | `frontend/overlays/images/` | The "flat" gamepad overlays of [libretro/common-overlays](https://github.com/libretro/common-overlays) | CC BY 4.0 |
| Touch-control layouts | `frontend/overlays/rm_*.cfg` | RetroManager's own, in RetroArch's overlay format: `rm_gba`, `rm_snes`, `rm_nds` and `rm_nds_mid` were laid out by hand starting from the libretro layouts above, the others are written by `tools/make_overlays.py` | CC BY 4.0, as the layouts they started from |
| System pictures (optional) | `frontend/imgs/*.jpg`, `frontend/imgs/template.psd` | Modified from [Switch-Light](https://github.com/lilbud/es-theme-switch-light), an EmulationStation theme by Lilbud, based on the Switch Theme for LaunchBox by Grila. The template is RetroManager's author's own, after Lilbud's design | CC BY-NC-SA (credit, no commercial use, changes shared alike). See `frontend/imgs/README.md`; delete the pictures and RetroManager shows its own tiles |
| Star icons of the Switch colour themes | `frontend/themes/switch/star-*.svg` | The same theme | CC BY-NC-SA |
| Oxygen font | `frontend/themes/switch/Oxygen-Regular.ttf` | Vernon Adams | SIL Open Font License 1.1 (`frontend/themes/switch/OFL.txt`) |

The screenshots in `docs/screenshots/` show a demo library of made-up games,
drawn by `tools/make_demo_library.py`: no real game, box art or logo is in
them. Any real game that ever appears in a picture of RetroManager is there for
illustration only, belongs to its publisher, and is not part of RetroManager
or included with it.

The consoles' and publishers' names and logos, wherever they appear (in the
optional system pictures, and in pictures and names fetched for your games),
belong to their owners. RetroManager isn't connected with or endorsed by any of
them.

## Fetched when it's used, not included

| What | When | Terms |
|---|---|---|
| [EmulatorJS](https://emulatorjs.org) and the emulator cores it loads | The first time a game is played in the browser (kept in the data folder afterwards) | GPL 3.0; each core has its own licence |
| React, ReactDOM and Babel | By the pages, from unpkg and jsDelivr (Babel only when the pages aren't built) | MIT |
| The LaunchBox Games Database's list of games | If LaunchBox is turned on in Settings | Its data and pictures are the LaunchBox community's |

## Built on

Python with Flask, Flask-CORS and Werkzeug (BSD), lxml (BSD), Requests (Apache
2.0), Pillow (MIT-CMU) and Gunicorn (MIT). The Android app uses only Android's
own libraries.

## Services it can ask

ScreenScraper, IGDB, RetroAchievements, Steam, SteamGridDB, TheGamesDB,
libretro thumbnails, GameTDB, the LaunchBox Games Database and Hasheous: each
with your own account or key where it needs one, and under its own terms.
What they return (descriptions, pictures, videos, manuals) belongs to them or
to the games' publishers; RetroManager stores it in your own folders and
passes none of it on. No games, BIOS files or media are supplied.

## Related

The profile switcher described in [PROFILES.md](PROFILES.md) is
[retropie_profiles](https://github.com/DeltaGemini/retropie_profiles), MIT.
