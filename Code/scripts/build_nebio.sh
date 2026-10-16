#!/bin/sh
# Builds the nebio C++ library (Code/nebio -> Code/nebio/build/libnebio.so).
# Incremental: only rebuilds what changed, so it is cheap to run at every boot.
# Needs: pacman -S cmake gcc libgpiod liblo
# -j3 leaves one core free (thermal headroom on the RPi4).

SRC=/home/alarm/QB_Nebulae_V2/Code/nebio
BUILD=$SRC/build

cmake -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release && cmake --build "$BUILD" -- -j3
