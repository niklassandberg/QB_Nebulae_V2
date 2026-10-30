#!/bin/sh
# cpustat.sh
# Measures CPU use per program over a time window and writes a report with
# min / max / mean / p95 for: python (nebulae.py, incl. nebio and Csound which
# run inside it), sclang, scsynth, pd, csound (standalone), jackd and the
# whole Pi. Python processes are also split per thread.
#
# Only uses sh, awk and /proc, so the same script runs on the original
# firmware for comparison (copy it to /tmp there).
#
#   sh cpustat.sh [-d seconds] [-i interval] [-l label] [-o outdir]
#   sh cpustat.sh -d 300 -l "SC bank, nebio"
#
# Writes <outdir>/cpustat_<date>.txt (report) and .csv (one row per interval).
# CPU values are "% of one core" like top (100 % = one core, the Pi 4 has 4);
# "Pi %" is the same divided by the number of cores.

DUR=300
INT=1
LABEL=""
OUT=/tmp
while getopts d:i:l:o:h opt
do
    case $opt in
        d) DUR=$OPTARG ;;
        i) INT=$OPTARG ;;
        l) LABEL=$OPTARG ;;
        o) OUT=$OPTARG ;;
        *) sed -n '2,17p' "$0"; exit 1 ;;
    esac
done

HZ=$(getconf CLK_TCK)
NCPU=$(getconf _NPROCESSORS_ONLN)
PAGE=$(getconf PAGESIZE)
STAMP=$(date +%Y%m%d_%H%M%S)
RAW=/tmp/cpustat_raw_$$.txt
REPORT=$OUT/cpustat_$STAMP.txt
CSV=$OUT/cpustat_$STAMP.csv
: > "$RAW" || exit 1

# One sample: time, /proc/stat cpu line, temperature, one P line per process of
# interest (pid group ticks rss), one H line per python thread, N lines with
# the python command lines.
sample() {
    echo "T $(date +%s.%N)"
    head -n 1 /proc/stat
    echo "C $(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)"
    PROCS=$(awk '
    {
        s = $0
        l = index(s, "(")
        for (r = length(s); r > 0; r--) if (substr(s, r, 1) == ")") break
        comm = substr(s, l + 1, r - l - 1)
        split(substr(s, r + 2), f, " ")   # f[k] = stat field k+2
        g = ""
        if (comm ~ /^python/) g = "python"
        else if (comm == "sclang") g = "sclang"
        else if (comm == "scsynth" || comm == "supernova") g = "scsynth"
        else if (comm == "pd" || comm == "pd-watchdog") g = "pd"
        else if (comm ~ /^csound/) g = "csound"
        else if (comm == "jackd" || comm == "jackdbus") g = "jackd"
        if (g != "") print "P", $1, g, f[12] + f[13], f[22]
    }' /proc/[0-9]*/stat 2>/dev/null)
    echo "$PROCS"
    for p in $(echo "$PROCS" | awk '$3 == "python" { print $2 }')
    do
        echo "N $p $(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)"
        awk -v pid=$p '
        {
            s = $0
            l = index(s, "(")
            for (r = length(s); r > 0; r--) if (substr(s, r, 1) == ")") break
            comm = substr(s, l + 1, r - l - 1)
            gsub(/ /, "_", comm)
            split(substr(s, r + 2), f, " ")
            print "H", pid, $1, f[12] + f[13], comm
        }' /proc/$p/task/[0-9]*/stat 2>/dev/null
    done
}

# Header (written before measuring, so it shows what was running at the start)
{
    echo "==== cpustat $(date '+%Y-%m-%d %H:%M:%S')"
    [ -n "$LABEL" ] && echo "label:      $LABEL"
    echo "host:       $(uname -n) $(uname -r) $(uname -m), $NCPU cores"
    echo "cpu freq:   $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)" \
         "$(( $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null || echo 0) / 1000 )) MHz"
    echo "window:     $DUR s, sample every $INT s"
    NEB=/home/alarm/QB_Nebulae_V2/Code
    if [ -f $NEB/nebio/build/libnebio.so ]
    then
        echo "nebio:      yes ($(ls -l --time-style=+%Y-%m-%d_%H:%M $NEB/nebio/build/libnebio.so | awk '{print $6}'))"
    else
        echo "nebio:      no (original hardware handling)"
    fi
    echo "nebulae.py: md5 $(md5sum $NEB/nebulae/nebulae.py 2>/dev/null | cut -c1-12)"
    echo "running:"
    ps -eo pid,args | awk 'NR > 1 && /python|sclang|scsynth|supernova|[ \/]pd |pd-watchdog|csound|jackd/ \
        && !/awk|cpustat/ { printf "  %s\n", substr($0, 1, 150) }'
} > "$REPORT"

echo "measuring for $DUR s, report: $REPORT" >&2
START=$(date +%s)
cat /proc/interrupts > "$RAW.irq1"
sample >> "$RAW"
NEXTLOG=$((START + 60))
while [ $(( $(date +%s) - START )) -lt "$DUR" ]
do
    sleep "$INT"
    sample >> "$RAW"
    NOW=$(date +%s)
    if [ "$NOW" -ge "$NEXTLOG" ]
    then
        echo "  $((NOW - START)) / $DUR s" >&2
        NEXTLOG=$((NOW + 60))
    fi
done
cat /proc/interrupts > "$RAW.irq2"
IRQSECS=$(( $(date +%s) - START ))

awk -v HZ="$HZ" -v NCPU="$NCPU" -v PAGE="$PAGE" -v CSV="$CSV" '
function stats(arr, n,    i, j, v, sum, mn, mx, srt) {
    if (n == 0) { S_min = S_max = S_mean = S_p95 = 0; return }
    sum = 0; mn = arr[1]; mx = arr[1]
    for (i = 1; i <= n; i++) {
        v = arr[i]; sum += v
        if (v < mn) mn = v
        if (v > mx) mx = v
        srt[i] = v
    }
    for (i = 2; i <= n; i++) {   # insertion sort for the percentile
        v = srt[i]
        for (j = i - 1; j > 0 && srt[j] > v; j--) srt[j + 1] = srt[j]
        srt[j + 1] = v
    }
    i = int(0.95 * n + 0.999999); if (i < 1) i = 1
    S_min = mn; S_max = mx; S_mean = sum / n; S_p95 = srt[i]
}
function endSample(    pid, g, d, tid, total, idle, i) {
    if (ns > 0) {
        dt = t - tPrev
        if (dt <= 0) dt = 1
        n++
        dur += dt
        for (i = 1; i <= ng; i++) val[groups[i]] = 0
        for (pid in cur) {
            if ((pid in prev) && grp[pid] == pgrp[pid]) {
                d = cur[pid] - prev[pid]
                if (d < 0) d = 0
                val[grp[pid]] += d
                pidTicks[pid] += d
            }
        }
        for (pid in cur) if (rss[pid] * PAGE / 1048576 > 0) grpRss[grp[pid]] += rss[pid] * PAGE / 1048576
        for (i = 1; i <= ng; i++) {
            g = groups[i]
            series[g, n] = val[g] / HZ / dt * 100
            if (grpRss[g] > maxRss[g]) maxRss[g] = grpRss[g]
            grpRss[g] = 0
        }
        total = cpuTotal - pTotal; idle = cpuIdle - pIdle
        series["pi", n] = total > 0 ? (total - idle) / total * 100 : 0
        series["temp", n] = temp
        for (tid in tcur) if (tid in tprev) {
            d = tcur[tid] - tprev[tid]
            if (d < 0) d = 0
            tTicks[tid] += d
            if (d / HZ / dt * 100 > tMax[tid]) tMax[tid] = d / HZ / dt * 100
        }
        printf "%.1f,%.1f", dur, series["pi", n] > CSV
        for (i = 1; i <= ng; i++) printf ",%.1f", series[groups[i], n] > CSV
        printf ",%.1f\n", temp > CSV
    }
    delete prev; delete pgrp; delete tprev
    for (pid in cur) { prev[pid] = cur[pid]; pgrp[pid] = grp[pid] }
    for (tid in tcur) tprev[tid] = tcur[tid]
    delete cur; delete grp; delete rss; delete tcur
    tPrev = t; pTotal = cpuTotal; pIdle = cpuIdle
}
BEGIN {
    ng = split("python sclang scsynth pd csound jackd", groups, " ")
    printf "time_s,pi_total_pct" > CSV
    for (i = 1; i <= ng; i++) printf ",%s_pct_of_core", groups[i] > CSV
    printf ",temp_c\n" > CSV
}
$1 == "T" { if (started) { endSample(); ns++ } started = 1; t = $2; next }
$1 == "cpu" {
    cpuTotal = 0
    for (i = 2; i <= NF; i++) cpuTotal += $i
    cpuIdle = $5 + $6
    # user+nice, system, irq+softirq, idle+iowait for the breakdown
    if (ns == 0) { b0[1] = $2 + $3; b0[2] = $4; b0[3] = $7 + $8; b0[4] = $5 + $6; b0[0] = cpuTotal }
    b1[1] = $2 + $3; b1[2] = $4; b1[3] = $7 + $8; b1[4] = $5 + $6; b1[0] = cpuTotal
    next
}
$1 == "C" { temp = $2 / 1000; next }
$1 == "P" { cur[$2] = $4; grp[$2] = $3; rss[$2] = $5; seen[$3] = 1; pidGroup[$2] = $3; next }
$1 == "H" { tcur[$3] = $4; tpid[$3] = $2; tname[$3] = $5; next }
$1 == "N" { c = $0; sub(/^N [0-9]+ /, "", c); cmd[$2] = c; next }
END {
    if (started) { endSample(); ns++ }
    if (n == 0) { print "no complete interval measured"; exit }
    printf "\nmeasured:   %d intervals, %.0f s\n\n", n, dur
    printf "%-10s %8s %8s %8s %8s   %8s %9s\n", "program", "min %", "mean %", "p95 %", "max %", "mean Pi%", "max RSS"
    printf "%-10s %8s %8s %8s %8s   %8s %9s\n", "", "(of one core, like top)", "", "", "", "", ""
    for (i = 1; i <= ng; i++) {
        g = groups[i]
        if (!(g in seen)) { printf "%-10s %s\n", g, "not running"; continue }
        for (k = 1; k <= n; k++) a[k] = series[g, k]
        stats(a, n)
        printf "%-10s %8.1f %8.1f %8.1f %8.1f   %8.1f %7.1f MB\n", g, S_min, S_mean, S_p95, S_max, S_mean / NCPU, maxRss[g]
    }
    for (k = 1; k <= n; k++) a[k] = series["pi", k]
    stats(a, n)
    printf "%-10s %8.1f %8.1f %8.1f %8.1f   (whole Pi, all %d cores = 100 %%)\n", "total Pi", S_min, S_mean, S_p95, S_max, NCPU
    for (k = 1; k <= n; k++) a[k] = series["temp", k]
    stats(a, n)
    printf "%-10s %8.1f %8.1f %8.1f %8.1f   (deg C)\n", "temp", S_min, S_mean, S_p95, S_max

    tot = b1[0] - b0[0]
    if (tot > 0) {
        sumMean = 0
        for (pid in pidTicks) sumMean += pidTicks[pid]
        printf "\nwhole Pi split (%% of all %d cores): user %.1f, system %.1f, irq %.1f, idle %.1f\n",
            NCPU, (b1[1] - b0[1]) / tot * 100, (b1[2] - b0[2]) / tot * 100,
            (b1[3] - b0[3]) / tot * 100, (b1[4] - b0[4]) / tot * 100
        printf "The programs above use %.1f %% of the Pi. The rest is other processes and kernel/interrupt\n", sumMean / HZ / dur * 100 / NCPU
        printf "work; this kernel counts interrupts during idle as system time without any process.\n"
    }

    printf "\npython processes (mean %% of one core):\n"
    for (pid in pidTicks) if (pidGroup[pid] == "python")
        printf "  %6d %6.1f %%  %s\n", pid, pidTicks[pid] / HZ / dur * 100, substr(cmd[pid], 1, 100)

    printf "\npython threads, busiest first (mean / max %% of one core).\n"
    printf "nebio and Csound threads run inside nebulae.py; the first thread is the python main loop.\n"
    m = 0
    for (tid in tTicks) { m++; order[m] = tid }
    for (i = 2; i <= m; i++) {
        v = order[i]
        for (j = i - 1; j > 0 && tTicks[order[j]] < tTicks[v]; j--) order[j + 1] = order[j]
        order[j + 1] = v
    }
    for (i = 1; i <= m && i <= 12; i++) {
        tid = order[i]
        printf "  pid %6d tid %6d %-16s %6.1f %% / %6.1f %%%s\n", tpid[tid], tid, tname[tid],
            tTicks[tid] / HZ / dur * 100, tMax[tid], (tid == tpid[tid] ? "   (main thread)" : "")
    }
}' "$RAW" >> "$REPORT"

# Interrupts per second over the whole window, busiest first.
# (SPI = ADC reads, i2c = LED driver, DMA = audio, IPI = cores signalling each other)
{
    printf "\ninterrupts per second (all cores), busiest first:\n"
    awk -v NCPU="$NCPU" -v SECS="$IRQSECS" '
    FNR == 1 { next }
    {
        s = 0
        for (i = 2; i <= NCPU + 1; i++) s += $i
        desc = ""
        for (i = NCPU + 2; i <= NF; i++) desc = desc " " $i
        if (NR == FNR) { a[$1] = s; next }
        if (SECS > 0 && (s - a[$1]) / SECS >= 10) printf "  %8.0f /s  %-6s%s\n", (s - a[$1]) / SECS, $1, desc
    }' "$RAW.irq1" "$RAW.irq2" | sort -rn
} >> "$REPORT"

rm -f "$RAW" "$RAW.irq1" "$RAW.irq2"
cat "$REPORT"
echo "csv: $CSV" >&2
