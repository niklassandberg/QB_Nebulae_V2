#!/bin/sh
# Builds the nebio C++ library (Code/nebio -> Code/nebio/build/libnebio.so).
# Incremental: only rebuilds what changed, so it is cheap to run at every boot.
# Needs: pacman -S cmake gcc libgpiod liblo
# -j3 leaves one core free (thermal headroom on the RPi4).
#
# A stamp (md5 of the sources + libgpiod/liblo versions) is kept next to the
# library. When it matches, cmake is skipped entirely (saves ~2 s at boot).
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
