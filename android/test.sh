#!/bin/bash
# The app's tests that run without Android: its plain decisions (src/.../Decide.java),
# checked by tests/DecideTest.java. Needs only a JDK. build.sh runs them first.
set -euo pipefail
cd "$(dirname "$0")"
out=build/test
rm -rf "$out" && mkdir -p "$out"
javac -d "$out" src/com/retromanager/phone/Decide.java tests/DecideTest.java
java -cp "$out" com.retromanager.phone.DecideTest
