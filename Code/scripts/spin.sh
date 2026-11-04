#!/bin/bash
# Keeps the CPU from sleeping: a do-nothing loop per core, run at idle
# priority. Each wake-up was heard as a tone.
#   spin.sh [yield|work|shell] [cores]   default: yield on every core
# spin.c is built into /tmp; shell is the fallback.
KIND=${1:-yield}
CORES=${2:-$(nproc)}
[ "$CORES" -gt "$(nproc)" ] && CORES=$(nproc)
SRC=$(dirname "$0")/spin.c
BIN=/tmp/nebulae_spin
if [ "$KIND" != shell ] && ! { [ -x $BIN ] && [ $BIN -nt "$SRC" ]; }; then
    gcc -O2 -o $BIN "$SRC" || KIND=shell
fi
trap 'kill $(jobs -p) 2>/dev/null; exit 0' TERM INT
for c in $(seq 0 $(( CORES - 1 ))); do
    if [ "$KIND" = shell ]; then
        taskset -c "$c" sh -c 'while :; do :; done' &
    else
        taskset -c "$c" $BIN "$KIND" &
    fi
done
wait
