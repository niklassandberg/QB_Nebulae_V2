#!/bin/sh
# Builds audrey on the Pi (needs cmake, g++, jack2 and liblo) and puts the
# binary next to its .prog (Programs/audrey/), ready for the USB stick:
#   sh Programs/audrey/source/build.sh
# Copy audrey and audrey.prog to the root of the USB stick.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=$(cd "$HERE/.." && pwd)
BUILD=/tmp/audrey-build
cmake -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j3
install -m 755 "$BUILD/audrey" "$BIN/audrey"
echo "built $BIN/audrey"
