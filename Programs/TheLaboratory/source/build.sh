#!/bin/sh
# Builds thelaboratory on the Pi (needs cmake, g++, jack2 and liblo) and puts
# the binary next to its .prog (Programs/TheLaboratory/), ready for the USB stick:
#   sh Programs/TheLaboratory/source/build.sh
# Copy thelaboratory and thelaboratory.prog to the root of the USB stick
# (or Programs/deploy_prog.sh TheLaboratory).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=$(cd "$HERE/.." && pwd)
BUILD=/tmp/thelaboratory-build
cmake -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j3
install -m 755 "$BUILD/thelaboratory" "$BIN/thelaboratory"
echo "built $BIN/thelaboratory"
