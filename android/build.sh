#!/usr/bin/env bash
# Builds the Android app (RetroManager.apk) with the Android SDK's own tools:
# no Gradle and no libraries, just the SDK (build-tools and a platform) and a JDK.
#   ./build.sh            builds android/build/RetroManager.apk
#   ./build.sh install    ...and installs it on the phone plugged in (adb)
# The SDK is looked for in ANDROID_HOME, then ~/Android/Sdk.
set -euo pipefail
cd "$(dirname "$0")"

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}"
TOOLS="$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)"
PLATFORM="$(ls -d "$SDK"/platforms/android-* | sort -V | tail -1)/android.jar"
# Each build's number is the minutes since 2026 began, so a later build is a
# newer version: the app compares it with the one RetroManager has (below)
VERSION_CODE=$(( ($(date +%s) - 1767225600) / 60 ))
VERSION_NAME="1.$VERSION_CODE"
# The key it's signed with. An update only installs over the app if it's signed
# with the same key, so whoever builds the app for others keeps theirs safe and
# to themselves: neither it nor its password is in the repository. signing.env
# (beside this script) names it:
#     KEYSTORE=release.keystore
#     KEY_ALIAS=retromanager
#     KEYSTORE_PASS=...
# (and, if wanted, APK_COPIES=<a folder to keep a copy of every build in>)
# Without that file a key is made here the first time (debug.keystore, with a
# password anyone can read below): fine for a phone of your own.
KEY=debug.keystore
KEY_ALIAS=retromanager
KEY_PASS=android
if [ -f signing.env ]; then
    while IFS='=' read -r name value; do
        case "$name" in
            KEYSTORE) KEY="$value" ;;
            KEY_ALIAS) KEY_ALIAS="$value" ;;
            KEYSTORE_PASS) KEY_PASS="$value" ;;
            APK_COPIES) APK_COPIES="${APK_COPIES:-$value}" ;;
        esac
    done < signing.env
    [ -f "$KEY" ] || { echo "signing.env names $KEY, which isn't here" >&2; exit 1; }
fi

rm -rf build
mkdir -p build/res/mipmap-xxxhdpi build/classes build/gen
cp -r res/. build/res/
cp ../frontend/icons/icon-192.png build/res/mipmap-xxxhdpi/ic_launcher.png

"$TOOLS/aapt2" compile --dir build/res -o build/res.zip
"$TOOLS/aapt2" link -o build/unsigned.apk -I "$PLATFORM" --manifest AndroidManifest.xml --java build/gen \
    --min-sdk-version 26 --target-sdk-version 34 --version-code "$VERSION_CODE" --version-name "$VERSION_NAME" build/res.zip

javac -source 17 -target 17 -Xlint:-options -classpath "$PLATFORM" -d build/classes $(find src build/gen -name '*.java')
"$TOOLS/d8" --release --lib "$PLATFORM" --min-api 26 --output build $(find build/classes -name '*.class')
(cd build && zip -q -j unsigned.apk classes.dex)

"$TOOLS/zipalign" -f 4 build/unsigned.apk build/aligned.apk
[ -f "$KEY" ] || keytool -genkeypair -keystore "$KEY" -storepass "$KEY_PASS" -keypass "$KEY_PASS" -alias "$KEY_ALIAS" \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=RetroManager" >/dev/null 2>&1
# (the password goes by the environment, not the command line, where other programs could read it)
RM_KEY_PASS="$KEY_PASS" "$TOOLS/apksigner" sign --ks "$KEY" --ks-key-alias "$KEY_ALIAS" --ks-pass env:RM_KEY_PASS --key-pass env:RM_KEY_PASS \
    --out build/RetroManager.apk build/aligned.apk
echo "Built $(pwd)/build/RetroManager.apk"
# RetroManager serves the newest build itself, for the app to offer as an update
# (frontend/app/ isn't in the repository: it goes into the image when that's built)
mkdir -p ../frontend/app
cp build/RetroManager.apk ../frontend/app/RetroManager.apk
echo "{\"code\": $VERSION_CODE, \"name\": \"$VERSION_NAME\"}" > ../frontend/app/version.json

# ...and a copy of every build is kept, named by its version, if there's a place
# for them: APK_COPIES, in signing.env or the environment (nothing happens if
# that folder's drive isn't there)
COPIES="${APK_COPIES:-}"
if [ -n "$COPIES" ] && mkdir -p "$COPIES" 2>/dev/null; then
    cp build/RetroManager.apk "$COPIES/RetroManager-$VERSION_NAME.apk" && cp build/RetroManager.apk "$COPIES/RetroManager.apk" \
        && echo "Copied to $COPIES/RetroManager-$VERSION_NAME.apk" || echo "Couldn't copy the build to $COPIES" >&2
elif [ -n "$COPIES" ]; then
    echo "Not copied: $COPIES isn't there" >&2
fi

if [ "${1:-}" = install ]; then
    "$SDK/platform-tools/adb" install -r build/RetroManager.apk
fi
