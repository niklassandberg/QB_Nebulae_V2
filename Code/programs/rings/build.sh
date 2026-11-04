#!/bin/sh
# Builds miRings on the Pi (needs cmake, g++, jack2 and liblo) and puts the
# binary in Code/bin/, where the firmware ships it:
#   sh Code/programs/rings/build.sh
# The binary is committed like the kernel modules: the Nebulae does not
# build it at boot.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=$(cd "$HERE/../../bin" 2>/dev/null && pwd || (mkdir -p "$HERE/../../bin" && cd "$HERE/../../bin" && pwd))
BUILD=/tmp/miRings-build
cmake -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j3
install -m 755 "$BUILD/miRings" "$BIN/miRings"
echo "built $BIN/miRings"
