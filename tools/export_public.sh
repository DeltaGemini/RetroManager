#!/usr/bin/env bash
# Makes the copy of RetroManager that's given to others, in another folder that
# is its own git repository (the public one): everything that's in git here and
# nothing that isn't, so what's kept out of git on purpose (this installation's
# settings, its logos and background, its keys) stays behind. The Android app
# as last built (frontend/app/, signed with its maker's key) goes too, for the
# image to serve to phones and the release to attach.
#
#     tools/export_public.sh /path/to/public/checkout
#
# It only changes that folder's files: look at `git status` and `git diff`
# there, then commit, tag (v1.2.3) and push it yourself. A tag starts the
# release (.github/workflows/release.yml).
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${1:?Where is the public checkout? tools/export_public.sh <folder>}"
[ -d "$DEST/.git" ] || { echo "$DEST isn't a git repository" >&2; exit 1; }
[ "$(cd "$DEST" && pwd -P)" != "$(pwd -P)" ] || { echo "That's this folder" >&2; exit 1; }
if [ -n "$(git status --porcelain)" ]; then
    echo "There are changes here that aren't committed: only what's committed goes." >&2
fi

# Out with what was there (but for its .git), in with what's committed here
find "$DEST" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
git archive HEAD | tar -x -C "$DEST"

# The app, if it's been built
if [ -f frontend/app/RetroManager.apk ] && [ -f frontend/app/version.json ]; then
    mkdir -p "$DEST/frontend/app"
    cp frontend/app/RetroManager.apk frontend/app/version.json "$DEST/frontend/app/"
    git -C "$DEST" add -f frontend/app/RetroManager.apk frontend/app/version.json
    echo "With the app: $(cat frontend/app/version.json)"
else
    echo "Without the app: it hasn't been built here (android/build.sh)"
fi
git -C "$DEST" add -A
echo "Exported $(git rev-parse --short HEAD) to $DEST:"
git -C "$DEST" status --short | awk '{print $1}' | sort | uniq -c
