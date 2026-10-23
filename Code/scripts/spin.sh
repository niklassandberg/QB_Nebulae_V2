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
# Heat guard: the loops pause (SIGSTOP) at SPIN_HOT and go on at SPIN_COOL
# (millidegrees). A Pi 3 without heatsink reached 83 C with them on all cores;
# at 85 C its firmware lowers the clock and the audio breaks up. A Pi 4 stays
# around 51 C, there the guard never acts.
KIND=${1:-yield}
HOT=${SPIN_HOT:-80000}
COOL=${SPIN_COOL:-75000}
TEMP=/sys/class/thermal/thermal_zone0/temp
CORES=${2:-$(nproc)}
[ "$CORES" -gt "$(nproc)" ] && CORES=$(nproc)
SRC=$(dirname "$0")/spin.c
BIN=/tmp/nebulae_spin
if [ "$KIND" != shell ] && ! { [ -x $BIN ] && [ $BIN -nt "$SRC" ]; }; then
    gcc -O2 -o $BIN "$SRC" || KIND=shell
fi
PIDS=""
# Stopped (systemctl stop, noise_test.sh stop): the loops go too (a paused
# loop only sees the TERM once it is continued).
trap 'kill -CONT $PIDS 2>/dev/null; kill $(jobs -p) 2>/dev/null; exit 0' TERM INT
for c in $(seq 0 $(( CORES - 1 ))); do
    if [ "$KIND" = shell ]; then
        taskset -c "$c" sh -c 'while :; do :; done' &
    else
        taskset -c "$c" $BIN "$KIND" &
    fi
    PIDS="$PIDS $!"
done
paused=0
while :; do
    t=$(cat $TEMP 2>/dev/null || echo 0)
    if [ $paused = 0 ] && [ "$t" -ge $HOT ]; then
        kill -STOP $PIDS 2>/dev/null; paused=1
        logger -t nebulae-spin "paused at $((t / 1000)) C"
    elif [ $paused = 1 ] && [ "$t" -le $COOL ]; then
        kill -CONT $PIDS 2>/dev/null; paused=0
        logger -t nebulae-spin "running again at $((t / 1000)) C"
    fi
    sleep 1 & wait $!  # the trap runs at once, not after the sleep
done
