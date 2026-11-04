#!/bin/sh
# Builds proxy on the Pi (needs cmake, g++, jack2 and liblo) and puts the
# binary next to its .prog (Programs/Proxy/), ready for the USB stick:
#   sh Programs/Proxy/source/build.sh
# Copy proxy and proxy.prog to the root of the USB stick.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=$(cd "$HERE/.." && pwd)
BUILD=/tmp/proxy-build
cmake -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j3
install -m 755 "$BUILD/proxy" "$BIN/proxy"
echo "built $BIN/proxy"
