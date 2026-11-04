#!/bin/sh
# Builds audrey on the Pi (needs cmake, g++, jack2 and liblo) and puts the
# binary in Code/bin/, where the firmware ships it:
#   sh Code/programs/audrey/build.sh
# The binary is committed like the kernel modules: the Nebulae does not
# build it at boot.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HERE/../../bin"
BIN=$(cd "$HERE/../../bin" && pwd)
BUILD=/tmp/audrey-build
cmake -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j3
install -m 755 "$BUILD/audrey" "$BIN/audrey"
echo "built $BIN/audrey"
