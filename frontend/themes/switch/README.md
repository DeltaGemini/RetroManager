# Switch theme assets

The background, logo, font and star icons used by RetroManager's "Switch" and
"Switch Light" site themes (see `frontend/common/theme.js` and the Switch
section of `frontend/common/header.css`).

They come from a customised copy of **Switch Master**, an EmulationStation
theme by Lilbud, based on the Switch Theme for LaunchBox by Grila. The theme
the system pictures were taken from is Lilbud's
<https://github.com/lilbud/es-theme-switch-light> (so the owner says, October
2026). That repository has no LICENSE file (GitHub reports no licence), but the
header of its `theme.xml` states it: "license: creative commons CC-BY-NC-SA",
author Lilbud, "based on: Switch Theme for Launchbox by Grila" (read 12 October
2026). No version of the licence is named. Its README says all the icons and
the background images were made by Lilbud. The theme is
licensed **CC BY-NC-SA**: credit the author, non-commercial use only, and share
changes under the same licence. The system pictures in `frontend/imgs/` are
from the same theme. `Oxygen-Regular.ttf` is the Oxygen font (SIL Open Font
License). `background.jpg` and `logo.png` ("Master RetroPie") are from the
copy of that EmulationStation theme this installation used (so its owner says,
October 2026): they were in the customised copy, not in Lilbud's release. The
background is a NASA picture of a nebula, darkened (which one, and so its exact
credit line, isn't recorded). NASA's own pictures aren't under copyright and
may be passed on with a credit and no suggestion that NASA endorses anything;
one made with a partner (ESA/Hubble's are CC BY 4.0) asks for that partner's
credit too. The logo is the owner's own work, lettered in the same Sega logo
font as the header's logo below, and has the same difficulty: the lettering is
Sega's.
`retromanager-logo.svg` (and its `.png` copy) is the header's logo: "RetroManager"
in the same lettering, as outlines taken from `SEGA.TTF` ("SEGA LOGO FONT",
which carries a Sega copyright notice).

The three logos (`logo.png`, `retromanager-logo.svg`, `retromanager-logo.png`)
and `background.jpg` (the nebula photograph: its source couldn't be found, so it
can't be credited) are **not in the repository** (they're listed in `.gitignore`): they stay on the
machine that has them, where the Switch colour themes go on using them, and a
copy of RetroManager without them shows its own logo and a drawn night sky instead
(`frontend/open/retromanager-logo.svg` and `background.svg`, the latter drawn by
`tools/make_background.py`). The system pictures in `frontend/imgs/`
are an optional extra with their own notice (`frontend/imgs/README.md`), and
RetroManager shows its drawn tiles (`frontend/tiles/`) unless they're chosen.
Everything here that is passed on is listed in `CREDITS.md`.
