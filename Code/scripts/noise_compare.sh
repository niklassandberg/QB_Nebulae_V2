#!/bin/bash
# Noise, CPU and heat of a playing Nebulae, for comparing firmwares (Qu-Bit's
# original against ours, with and without noise reduction). Only measures:
# it switches nothing that a firmware may not have (no spin, nohlt, nebio),
# so the same script runs on the original image (bash + coreutils only, no
# Python on the Pi). The analysis runs afterwards on the PC:
# noise_compare_analyze.py (same spectrum code as noise_measure.py).
#
# Set up the same on every firmware: granular looper (a_granularlooper),
# source on live input, buffer empty, nothing recording, blend_alt at 0, so
# the output is digital silence and the input can't reach the output; a cable
# from output to input. Csound holds the sound card, so it records its own
# input through a tap (one fout line in the instrument, into RAM).
#
#   sudo bash noise_compare.sh tap on     tap into /home/alarm/instr/
#       a_granularlooper.instr, the stick's USB storage driver unbound (the
#       original copies the stick's instruments over everything at every
#       start; without a stick it keeps them), Nebulae restarted
#   sudo bash noise_compare.sh measure LABEL [NOISE_S] [CPU_S]
#       NOISE_S (default 60) seconds of the tap, then CPU_S (default 600)
#       seconds of CPU, temperature and clock, once a second (bash builtins
#       only, so the sampler itself hardly wakes the CPU). Result:
#       /dev/shm/noise_compare_LABEL.tar
#   sudo bash noise_compare.sh tap off    original instrument and stick back,
#       Nebulae restarted
#   sudo bash noise_compare.sh load LABEL [PHASE_S]   robustness under load:
#       Nebulae plays as in real use (CV moving the knobs), four phases of
#       PHASE_S (default 60) seconds: normal, cpu (a busy loop per core at
#       normal priority: "another program"), sd (4 MB written + fsync to the
#       SD card over and over), recover. Per phase: Csound's buffer
#       underrun/overrun messages (journal), 30 s of the tap from the middle
#       (with source on file and the cable, a dropout is a sudden gap in the
#       sound: the analysis finds it), CPU, temperature, clock. Two variants:
#       source on file (samples play, cable output->input; blend_alt 0: no
#       feedback) and source on live input (pull the cable: it would record
#       its own output; then only the messages count).
# LABEL e.g. original, ours_off, ours_nohlt. Let Nebulae play a few minutes
# before measuring (heat): the script waits until it has played 3 minutes.
# Copy the tar to the PC, then:
#   python3 noise_compare_analyze.py noise_compare_*.tar
set -u
CODE=/home/alarm/QB_Nebulae_V2/Code
# The granular looper Nebulae loads: the original's "factory" bank is the
# firmware's own Code/instr (its "user" bank and our "instr" bank are the
# stick's copy in /home/alarm/instr).
case "$(sed -n 's/^bank,//p' $CODE/config/bootinstr.txt 2>/dev/null)" in
    factory) INSTR=$CODE/instr/a_granularlooper.instr ;;
    *) INSTR=/home/alarm/instr/a_granularlooper.instr ;;
esac
BACKUP=/home/alarm/.noise_compare_instr_backup
BACKUP_PATH=$BACKUP.path   # which file the backup belongs to
TAP=/dev/shm/noise_tap.raw
TAP_AFTER="ainl, ainr inch 1, 2"
TAP_LINE="fout \"$TAP\", 0, ainl, ainr"
WORK=/dev/shm/noise_compare
USB_STATE=/home/alarm/.noise_compare_usb   # the unbound USB storage interfaces
HZ=$(getconf CLK_TCK)

[ "$(id -u)" = 0 ] || { echo "run as root: sudo bash $0 $*"; exit 1; }

nebulae_pid() { pgrep -f "nebulae/nebulae.py" | head -1; }

# The original image keeps / read-only between its own writes: open it for
# ours and close it again if it was closed.
WAS_RO=
rw() { [ "$(findmnt -no OPTIONS / | cut -d, -f1)" = ro ] && WAS_RO=1 && mount -o remount,rw /; }
ro_again() { [ -n "$WAS_RO" ] && mount -o remount,ro /; WAS_RO=; }

tap_on() {
    grep -qF "$TAP_LINE" "$INSTR" && { echo "tap already in"; return; }
    grep -qxF "$TAP_AFTER" "$INSTR" || { echo "\"$TAP_AFTER\" not in $INSTR"; exit 1; }
    rw
    cp -p "$INSTR" "$BACKUP"
    echo "$INSTR" > $BACKUP_PATH
    # the line after the input
    sed -i "/^$TAP_AFTER\$/a $TAP_LINE" "$INSTR"
    ro_again
    echo "tap in $INSTR"
    # Kept from an earlier tap on (then nothing is bound any more to list).
    [ -s $USB_STATE ] || for d in /sys/bus/usb/drivers/usb-storage/*:*; do
        [ -e "$d" ] || continue
        basename "$d" >> $USB_STATE
    done
    umount /mnt/memory 2>/dev/null
    while read -r i; do echo "$i" > /sys/bus/usb/drivers/usb-storage/unbind; done < $USB_STATE
    echo "tap in; USB storage unbound: $(tr '\n' ' ' < $USB_STATE)"
    systemctl restart nebulae.service
    echo "Nebulae restarted; waiting for the tap"
    for i in $(seq 1 120); do
        [ -s $TAP ] && { echo "tap is written"; return; }
        sleep 1
    done
    echo "no tap after 2 minutes: is the granular looper loaded? (journalctl -u nebulae)"
}

tap_off() {
    if [ -f "$BACKUP" ]; then
        rw
        cp -p "$BACKUP" "$(cat $BACKUP_PATH 2>/dev/null || echo $INSTR)" && rm -f "$BACKUP" $BACKUP_PATH
        ro_again
    fi
    if [ -f $USB_STATE ]; then
        while read -r i; do echo "$i" > /sys/bus/usb/drivers/usb-storage/bind 2>/dev/null; done < $USB_STATE
        rm -f $USB_STATE
    fi
    rm -f $TAP
    echo "original instrument and USB storage back; Nebulae restarted"
    systemctl restart nebulae.service
}

# Frees the tap's RAM: Csound writes on at its offset, what was before becomes
# a hole (no memory). /dev/shm can be small (128 MB on the original image;
# the tap grows 384 KB/s). Never inside a noise window.
trim() { : > $TAP; }

# Sleeps N seconds, trimming the tap every 30 s.
sleep_trim() {
    local left=$1
    while [ $left -gt 0 ]; do
        local s=$(( left < 30 ? left : 30 ))
        sleep $s; trim; left=$(( left - s ))
    done
}

# CPU ticks of a process (utime + stime), bash builtins only.
ticks() {
    local f
    read -r f < /proc/$1/stat 2>/dev/null || { echo 0; return; }
    f=${f##*) }              # after "(comm) "
    set -- $f
    echo $(( ${12} + ${13} ))   # fields 14 and 15 of the whole line
}

measure() {
    local label=$1 noise_s=${2:-60} cpu_s=${3:-600}
    local out=$WORK/$label
    [ -s $TAP ] || { echo "no tap ($TAP): tap on first"; exit 1; }
    local pid; pid=$(nebulae_pid)
    [ -n "$pid" ] || { echo "Nebulae is not running"; exit 1; }
    rm -rf "$out"; mkdir -p "$out"
    local played=$(( $(cut -d' ' -f22 /proc/$pid/stat) / HZ ))
    local up; read -r up _ < /proc/uptime; up=${up%.*}
    local age=$(( up - played ))
    if [ $age -lt 180 ]; then
        echo "Nebulae plays for ${age} s: waiting until 3 minutes"
        sleep_trim $(( 180 - age ))
    fi
    {
        echo "label=$label"
        echo "date=$(date -u '+%F %T') UTC"
        echo "model=$(tr -d '\0' < /proc/device-tree/model)"
        echo "kernel=$(uname -r) $(uname -m)"
        echo "cmdline=$(cat /proc/cmdline)"
        echo "firmware=$(grep -h VERSION /home/alarm/QB_Nebulae_V2/Code/config.txt 2>/dev/null | head -1)"
        echo "config=$(tr '\n' ' ' < /home/alarm/QB_Nebulae_V2/Code/config/configsettings.txt 2>/dev/null)"
        echo "governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
        echo "spin=$(pgrep -c nebulae_spin)"
        echo "cores=$(nproc)"
        echo "hz=$HZ"
        echo "nebulae_cmd=$(tr '\0' ' ' < /proc/$pid/cmdline)"
        echo "gain=$(amixer -D hw:0 sget Capture 2>/dev/null | sed -n 's/.*Left: Capture \([0-9]*\).*/\1/p')"
    } > $out/info.txt
    echo "noise: $noise_s s of the tap"
    local s0 s1
    trim; sleep 1
    s0=$(stat -c %s $TAP); sleep "$noise_s"; s1=$(stat -c %s $TAP)
    s0=$(( s0 - s0 % 8 )); s1=$(( s1 - s1 % 8 ))
    tail -c +$(( s0 + 1 )) $TAP | head -c $(( s1 - s0 )) > $out/noise.raw
    echo "noise_bytes=$(( s1 - s0 ))" >> $out/info.txt
    trim
    echo "CPU: $cpu_s s"
    # threads of Nebulae at the start (their CPU time over the run at the end)
    for t in /proc/$pid/task/*; do
        echo "$(basename $t) $(ticks $pid/task/$(basename $t)) $(cat $t/comm)"
    done > $out/threads_start.txt
    echo "t,sys_busy_pct,nebulae_pct_of_one_core,spin_pct_of_one_core,temp_c,freq_mhz" > $out/cpu.csv
    local line cpu a b c d e f g h total busy pt pn st sn t0 temp freq spins sp sp0
    read -r line < /proc/stat; set -- $line
    total=$(( $2 + $3 + $4 + $5 + $6 + $7 + $8 + $9 )); busy=$(( total - $5 - $6 ))
    pt=$(ticks $pid)
    sp0=0; for p in $(pgrep nebulae_spin); do sp0=$(( sp0 + $(ticks $p) )); done
    for t0 in $(seq 1 "$cpu_s"); do
        sleep 1
        read -r line < /proc/stat; set -- $line
        local tt=$(( $2 + $3 + $4 + $5 + $6 + $7 + $8 + $9 )) bb
        bb=$(( tt - $5 - $6 ))
        pn=$(ticks $pid)
        sp=0; for p in $(pgrep nebulae_spin); do sp=$(( sp + $(ticks $p) )); done
        read -r temp < /sys/class/thermal/thermal_zone0/temp
        read -r freq < /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null || freq=0
        # ticks per second: HZ per core; busy share of all cores in percent
        echo "$t0,$(( 100 * (bb - busy) / (tt - total) )),$(( 100 * (pn - pt) / HZ )),$(( 100 * (sp - sp0) / HZ )),$(( temp / 1000 )),$(( freq / 1000 ))" >> $out/cpu.csv
        total=$tt; busy=$bb; pt=$pn; sp0=$sp
        [ $(( t0 % 30 )) = 0 ] && trim
    done
    for t in /proc/$pid/task/*; do
        echo "$(basename $t) $(ticks $pid/task/$(basename $t)) $(cat $t/comm)"
    done > $out/threads_end.txt
    command -v vcgencmd >/dev/null && vcgencmd get_throttled >> $out/info.txt
    tar -cf /dev/shm/noise_compare_$label.tar -C $WORK $label
    echo "done: /dev/shm/noise_compare_$label.tar"
}

# One sample per second for N seconds: phase,t,system %, Nebulae % of one
# core, temperature, clock. Bash builtins only.
sample() {
    local n=$1 phase=$2 csv=$3 pid=$4
    local line total busy pt pn temp freq t tt bb
    read -r line < /proc/stat; set -- $line
    total=$(( $2 + $3 + $4 + $5 + $6 + $7 + $8 + $9 )); busy=$(( total - $5 - $6 ))
    pt=$(ticks $pid)
    for t in $(seq 1 "$n"); do
        sleep 1
        read -r line < /proc/stat; set -- $line
        tt=$(( $2 + $3 + $4 + $5 + $6 + $7 + $8 + $9 )); bb=$(( tt - $5 - $6 ))
        pn=$(ticks $pid)
        read -r temp < /sys/class/thermal/thermal_zone0/temp
        read -r freq < /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null || freq=0
        echo "$phase,$t,$(( 100 * (bb - busy) / (tt - total) )),$(( 100 * (pn - pt) / HZ )),$(( temp / 1000 )),$(( freq / 1000 ))" >> $csv
        total=$tt; busy=$bb; pt=$pn
    done
}

LOAD_PIDS=
SD_FILE=/home/alarm/.noise_compare_sdload
load_start() {
    case $1 in
        cpu) for i in $(seq 1 $(nproc)); do bash -c 'while :; do :; done' & LOAD_PIDS="$LOAD_PIDS $!"; done ;;
        sd)  rw
             bash -c "while :; do dd if=/dev/zero of=$SD_FILE bs=64k count=64 conv=fsync 2>/dev/null; done" &
             LOAD_PIDS="$LOAD_PIDS $!" ;;
    esac
}
load_stop() {
    [ -n "$LOAD_PIDS" ] && kill $LOAD_PIDS 2>/dev/null; wait $LOAD_PIDS 2>/dev/null
    LOAD_PIDS=
    rm -f $SD_FILE
    ro_again
}

measure_load() {
    local label=$1 phase_s=${2:-60}
    local out=$WORK/$label
    local pid; pid=$(nebulae_pid)
    [ -n "$pid" ] || { echo "Nebulae is not running"; exit 1; }
    rm -rf "$out"; mkdir -p "$out"
    trap 'load_stop' EXIT
    {
        echo "label=$label"
        echo "mode=load"
        echo "date=$(date -u '+%F %T') UTC"
        echo "model=$(tr -d '\0' < /proc/device-tree/model)"
        echo "kernel=$(uname -r) $(uname -m)"
        echo "cmdline=$(cat /proc/cmdline)"
        echo "firmware=$(grep -h VERSION /home/alarm/QB_Nebulae_V2/Code/config.txt 2>/dev/null | head -1)"
        echo "cores=$(nproc)"
        echo "hz=$HZ"
        echo "phase_s=$phase_s"
        echo "csound_rt=$(for t in /proc/$pid/task/*; do s=$(cut -d' ' -f41 $t/stat 2>/dev/null); [ "${s:-0}" != 0 ] && echo -n "$(cat $t/comm):policy$s "; done)"
        echo "rss_kb=$(sed -n 's/^VmRSS:[[:space:]]*\([0-9]*\).*/\1/p' /proc/$pid/status)"
    } > $out/info.txt
    echo "phase,t,sys_busy_pct,nebulae_pct_of_one_core,temp_c,freq_mhz" > $out/cpu.csv
    local phase t0 t1 s0 s1 half=$(( phase_s / 2 )) cap
    cap=$(( phase_s - 30 )); [ $cap -lt 0 ] && cap=0
    for phase in normal cpu sd recover; do
        trim
        load_start $phase
        t0=$(date '+%Y-%m-%d %H:%M:%S')
        # 30 s of the tap from the middle of the phase, in the background
        [ -s $TAP ] && (
            sleep $(( cap / 2 ))
            s0=$(stat -c %s $TAP); sleep 30; s1=$(stat -c %s $TAP)
            s0=$(( s0 - s0 % 8 )); s1=$(( s1 - s1 % 8 ))
            tail -c +$(( s0 + 1 )) $TAP 2>/dev/null | head -c $(( s1 - s0 )) > $out/phase_$phase.raw
        ) &
        local cap_pid=$!
        sample $phase_s $phase $out/cpu.csv $pid
        wait $cap_pid   # only the recording: the load loops run until load_stop
        load_stop
        t1=$(date '+%Y-%m-%d %H:%M:%S')
        echo "phase_$phase=$t0|$t1" >> $out/info.txt
        echo "$phase done"
    done
    trap - EXIT
    # Csound's dropout messages per phase (the journal, nebulae.service)
    sleep 5   # late lines
    for phase in normal cpu sd recover; do
        local span; span=$(sed -n "s/^phase_$phase=//p" $out/info.txt)
        echo "msgs_$phase=$(journalctl -u nebulae.service --since "${span%|*}" --until "${span#*|}" --no-pager -o cat 2>/dev/null | grep -ciE 'underrun|overrun|xrun|buffer.*(late|empty)')" >> $out/info.txt
    done
    journalctl -u nebulae.service --since "$(sed -n 's/^phase_normal=\(.*\)|.*/\1/p' $out/info.txt)" --no-pager -o short-iso 2>/dev/null \
        | grep -iE 'underrun|overrun|xrun' > $out/csound_msgs.txt
    tar -cf /dev/shm/noise_compare_$label.tar -C $WORK $label
    echo "done: /dev/shm/noise_compare_$label.tar"
}

case "${1:-}" in
    tap) case "${2:-}" in on) tap_on ;; off) tap_off ;; *) echo "tap on|off"; exit 2 ;; esac ;;
    load) [ -n "${2:-}" ] || { echo "load LABEL [PHASE_S]"; exit 2; }; measure_load "$2" "${3:-60}" ;;
    measure) [ -n "${2:-}" ] || { echo "measure LABEL [NOISE_S] [CPU_S]"; exit 2; }; measure "$2" "${3:-60}" "${4:-600}" ;;
    *) echo "usage: sudo bash $0 tap on|off | measure LABEL [NOISE_S] [CPU_S] | load LABEL [PHASE_S]"; exit 2 ;;
esac
