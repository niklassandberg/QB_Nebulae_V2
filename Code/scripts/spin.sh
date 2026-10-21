#!/bin/bash
# Keeps the CPU from sleeping: a do-nothing loop on every core. Run by
# Quiet Mode (Code/nebscripts/3_quiet.sh) as unit nebulae-spin with
# CPUSchedulingPolicy=idle, so all real work goes first. Each wake-up from
# sleep (WFI) was a current pulse heard in the audio as a tone.
for c in $(seq 0 $(( $(nproc) - 1 ))); do
    taskset -c "$c" sh -c 'while :; do :; done' &
done
wait
