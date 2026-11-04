#!/bin/sh
# Builds Code/nebio/build/libnebio.so; a stamp skips cmake when nothing changed.
# Needs: pacman -S cmake gcc libgpiod liblo
#   build_nebio.sh         build unless up to date
#   build_nebio.sh check   only test: exit 0 if up to date, 1 if a build is needed

SRC=/home/alarm/QB_Nebulae_V2/Code/nebio
BUILD=$SRC/build
LIB=$BUILD/libnebio.so
STAMP=$BUILD/.src_stamp

stamp() {
    cat "$SRC/CMakeLists.txt" "$SRC"/include/* "$SRC"/src/* | md5sum
    pkg-config --modversion libgpiod liblo 2>/dev/null
}

if [ -f "$LIB" ] && [ -f "$STAMP" ] && [ "$(stamp)" = "$(cat "$STAMP")" ]
then
    echo "nebio up to date"
    exit 0
fi
[ "$1" = "check" ] && exit 1

rm -f "$STAMP"
cmake -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release && cmake --build "$BUILD" -- -j3 || exit 1
stamp > "$STAMP"
