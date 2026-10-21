#!/bin/bash
# Keeps the CPU from sleeping: a do-nothing loop on the first N cores. Run by
# Quiet Mode (Code/scripts/quiet.sh) as unit nebulae-spin with
# CPUSchedulingPolicy=idle, and by noise_test.sh under chrt --idle, so all
# real work goes first. Each wake-up from sleep (WFI) was a current pulse
# heard in the audio as a tone.
#   spin.sh [yield|work|shell] [cores]   default: yield on every core
# yield/work: spin.c (see there), built into /tmp (RAM, so the root file
# system stays read-only) when missing or older than spin.c; shell: a shell
# loop (also the fallback if gcc fails).
KIND=${1:-yield}
CORES=${2:-$(nproc)}
[ "$CORES" -gt "$(nproc)" ] && CORES=$(nproc)
SRC=$(dirname "$0")/spin.c
BIN=/tmp/nebulae_spin
if [ "$KIND" != shell ] && ! { [ -x $BIN ] && [ $BIN -nt "$SRC" ]; }; then
    gcc -O2 -o $BIN "$SRC" || KIND=shell
fi
# Stopped (systemctl stop, noise_test.sh stop): the loops go too.
trap 'kill $(jobs -p) 2>/dev/null; exit 0' TERM INT
for c in $(seq 0 $(( CORES - 1 ))); do
    if [ "$KIND" = shell ]; then
        taskset -c "$c" sh -c 'while :; do :; done' &
    else
        taskset -c "$c" $BIN "$KIND" &
    fi
done
wait
