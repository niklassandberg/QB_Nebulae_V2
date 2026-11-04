#!/bin/sh
# Builds miRings on the Pi (needs cmake, g++, jack2 and liblo) and puts the
# binary next to its .prog (Programs/miRings/), ready for the USB stick:
#   sh Programs/miRings/source/build.sh
# Copy miRings and miRings.prog to the root of the USB stick.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=$(cd "$HERE/.." && pwd)
BUILD=/tmp/miRings-build
cmake -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j3
install -m 755 "$BUILD/miRings" "$BIN/miRings"
echo "built $BIN/miRings"
