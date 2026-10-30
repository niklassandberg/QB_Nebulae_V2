#!/bin/bash
# Noise test: everything off except the audio chip (i2s, WM8731) and the LAN
# (to run this over ssh), to hear how much noise is left from the sound chip
# itself. Run as root over ssh:
#   sudo bash noise_test.sh start [silence|thru|poll|leds|cpu|jitter|lock|wake|gpio|spi] [spin|spin=yield|work|shell[:cores]]
#       (stop a running test first)
#       silence (default): the DAC plays digital zero, so only the chip's own
#                          noise (and what reaches it from the board) is heard
#       thru: input -> output with nothing in between (ADC -> DAC), for
#             feedback at the input
#     Steps, each with everything of the one before, to find what in a
#     running Nebulae makes the noise:
#       poll: + nebio reads knobs/CV (SPI, 400/s) and buttons/encoders (GPIO,
#             1200/s), a Python loop takes the values ~400/s (noise_test_load.py)
#       leds: + every LED at half brightness (PWM), the reset LED too
#       cpu:  + Csound with a DSP load like the granular looper's, output
#             multiplied by 0 (Csound plays the silence instead of aplay)
#     Against the tones of "poll" (compare with poll, same parts running):
#       jitter: poll, but every scan interval varies randomly by up to
#               +-JITTER (the mean rate stays): the tone should become noise
#       lock:   poll, but the scans are triggered by the audio chip's clock
#               (one per 64 samples = 750/s, knobs/buttons 375/s, in audio
#               time: no drift; 64 is the smallest block the chip takes)
#     How the scans' pulse gets into the audio (compare with poll):
#       wake: no nebio, no GPIO, no SPI: a program only wakes 1200/s and
#             sleeps again. Tones here: the CPU waking up (supply current)
#       gpio: nebio scans 1200/s (encoders) and buttons/shift register 400/s,
#             ADC (SPI) only 1/s; no Python loop. Tones: GPIO toggling
#       spi:  ADC (SPI) 400/s, encoder scans down to 400/s, buttons 1/s; no
#             Python loop. Compare with gpio: SPI to the ADC chips
#     Result (2026-10-21): "wake" alone gives a high tone: the CPU waking from
#     sleep is a current pulse that is heard. Against that, any step with
#     "spin" after it (e.g. start wake spin): the CPU never sleeps, a
#     do-nothing loop on every core at the lowest priority (SCHED_IDLE).
#     spin = shell loop on every core; spin=KIND[:CORES] with KIND yield
#     (least current, lowest hiss), work (even work, closer to real work's
#     current) or shell, on the first CORES cores, e.g. start cpu spin=work:2
#   sudo bash noise_test.sh stop      everything back, Nebulae starts again
#   sudo bash noise_test.sh status
#
# Off while the test runs: Nebulae (Python loop, Csound, nebio's knob/button
# polling at 400/1200 Hz, LED updates), SuperCollider/jack/pd, all LEDs
# (static off: PCA9685 full bit, reset LED pin held high), the Pi's own LEDs,
# USB (controller unbound), Wi-Fi/BT chip (driver removed), time sync,
# wpa_supplicant, scheduled jobs, journal writes to the SD card.

CODE=/home/alarm/QB_Nebulae_V2/Code
STATE=/tmp/noise_test_active
USB_DEV=0000:01:00.0
USB_DRV=/sys/bus/pci/drivers/xhci_hcd
# The Pi's green/red LEDs: led0/led1 on kernel 5.15, ACT/PWR on newer kernels.
ACT_LED=/sys/class/leds/ACT; [ -e $ACT_LED ] || ACT_LED=/sys/class/leds/led0
PWR_LED=/sys/class/leds/PWR; [ -e $PWR_LED ] || PWR_LED=/sys/class/leds/led1
SERVICES="systemd-timesyncd.service netctl-auto@wlan0.service"
TIMERS="archlinux-keyring-wkd-sync.timer shadow.timer systemd-tmpfiles-clean.timer"
FMT="-D hw:0,0 -f S16_LE -r 48000 -c 2 -t raw"  # as Csound: 16-bit, 48 kHz
LOAD=$CODE/scripts/noise_test_load.py
CSD=/tmp/noise_test_load.csd
CPU_VOICES=8  # Csound load: voices of vco2 + moogladder (tuned to ~ the granular looper)
JITTER=0.3    # step "jitter": scan intervals vary by up to +-30 %

# Csound as Nebulae runs it (alsa, hw:0,0, -B512, ksmps 64), with CPU_VOICES
# voices of DSP whose sum is multiplied by 0. Output only: the input stays
# free for noise_measure.py (cable from output to input).
write_csd() {
    cat > $CSD <<EOF
<CsoundSynthesizer>
<CsOptions>
-+rtaudio=alsa -odac:hw:0,0 -B512 --realtime -d -m0
</CsOptions>
<CsInstruments>
sr = 48000
ksmps = 64
nchnls = 2
0dbfs = 1
gaload init 0
instr 1
  a1 vco2 0.1, 80 + p4 * 7
  a2 moogladder a1, 1500 + p4 * 20, 0.4
  gaload = gaload + a2
endin
instr 2
  outs gaload * 0, gaload * 0
  gaload = 0
endin
instr 3
  icnt = 0
  loop:
  schedule 1 + (icnt + 1) / 1000, 0, -1, icnt  ; own number: held notes of one number replace each other
  loop_lt icnt, 1, $CPU_VOICES, loop
endin
</CsInstruments>
<CsScore>
i 2 0 36000
i 3 0 0
</CsScore>
</CsoundSynthesizer>
EOF
}

# All 16 PCA9685 outputs static high (ALL_LED_ON_H full bit) = LEDs off.
leds_static_off() {
    python3 - <<'EOF'
import fcntl, os
fd = os.open("/dev/i2c-1", os.O_RDWR)
fcntl.ioctl(fd, 0x0703, 0x40)  # I2C_SLAVE, PCA9685
for reg, val in ((0xFA, 0), (0xFB, 0x10), (0xFC, 0), (0xFD, 0)):
    os.write(fd, bytes([reg, val]))
os.close(fd)
EOF
}

start() {
    [ -f $STATE ] && { echo "noise test already running (stop first)"; exit 1; }
    mode=${1:-silence}
    case "$mode" in
        silence|thru|poll|leds|cpu|jitter|lock|wake|gpio|spi) ;;
        *) echo "unknown mode $mode (silence|thru|poll|leds|cpu|jitter|lock|wake|gpio|spi)"; exit 2 ;;
    esac
    echo "$mode" > $STATE
    echo "stopping Nebulae and audio engines"
    systemctl stop nebulae.service sclang.service jack.service 2>/dev/null
    pkill -x scsynth; pkill -x jackd; pkill -x pd
    # Wait until the audio chip is free: right after "stop" Nebulae may just
    # have opened it, and Csound then ended at once ("cpu", seen 1 of 2).
    for i in $(seq 1 25); do
        grep -q closed /proc/asound/card0/pcm0p/sub0/status 2>/dev/null && break
        sleep 0.2
    done
    echo "LEDs off (static)"
    leds_static_off || echo "  could not reach the LED chip"
    # leds/cpu: nebio drives the reset LED pin itself (it would be busy).
    if [ "$mode" != leds ] && [ "$mode" != cpu ] && command -v gpioset >/dev/null; then
        gpioset -z -c gpiochip0 12=1 2>/dev/null || echo "  reset LED pin not held (gpioset failed)"
    fi
    for l in $ACT_LED $PWR_LED; do
        echo none > $l/trigger; echo 0 > $l/brightness
    done
    echo "USB off, Wi-Fi/BT off"
    [ -e $USB_DRV/$USB_DEV ] && { umount /mnt/memory 2>/dev/null; echo $USB_DEV > $USB_DRV/unbind; }
    bash $CODE/scripts/wifi.sh off >/dev/null 2>&1
    echo "services, timers, journal"
    systemctl stop $SERVICES $TIMERS 2>/dev/null
    modprobe -r brcmfmac 2>/dev/null
    journalctl --relinquish-var
    case "$mode" in
        silence|thru) ;;
        poll) echo "nebio input polling + Python loop"
              python3 $LOAD > /dev/null 2>&1 & ;;
        leds) echo "nebio input polling + Python loop + LEDs at half brightness"
              python3 $LOAD --leds > /dev/null 2>&1 & ;;
        cpu)  echo "nebio input polling + Python loop + LEDs + Csound DSP load"
              python3 $LOAD --leds > /dev/null 2>&1 & ;;
        jitter) echo "nebio input polling + Python loop, scan timing jittered +-$JITTER"
              python3 $LOAD --jitter $JITTER > /dev/null 2>&1 & ;;
        wake) echo "only a CPU wake-up 1200/s, nothing else"
              python3 $LOAD --wake > /dev/null 2>&1 & ;;
        gpio) echo "nebio GPIO scans 1200/s, buttons 400/s, ADC 1/s"
              python3 $LOAD --rates 1200,400,1 --nosnap > /dev/null 2>&1 & ;;
        spi)  echo "nebio ADC (SPI) 400/s, encoder scans 400/s, buttons 1/s"
              python3 $LOAD --rates 400,1,400 --nosnap > /dev/null 2>&1 & ;;
        lock) echo "nebio input polling + Python loop, scans locked to the audio clock (750/s)"
              python3 $LOAD --lock > /dev/null 2>&1 & ;;  # plays the silence itself (ALSA)
    esac
    echo "audio: $mode"
    if [ "$mode" = lock ]; then
        :  # noise_test_load.py --lock plays through ALSA itself
    elif [ "$mode" = thru ]; then
        ( arecord -q $FMT | aplay -q $FMT ) > /dev/null 2>&1 &
    elif [ "$mode" = cpu ]; then
        write_csd
        for try in 1 2 3; do  # ended at once now and then: start it again
            csound $CSD > /tmp/noise_test_csound.log 2>&1 &
            sleep 2
            pgrep -x csound > /dev/null && break
            echo "  Csound ended at once, starting it again"
        done
    else
        aplay -q $FMT /dev/zero > /dev/null 2>&1 &
    fi
    case "$2" in
        spin|spin=*)
        # The CPU never sleeps: a do-nothing loop per core at the lowest
        # priority (SCHED_IDLE, any real work goes first). Waking from sleep
        # (WFI) is a current pulse that is heard ("wake" gives a tone).
        # spin = shell loop on every core (as the first tests);
        # spin=KIND[:CORES], KIND yield|work|shell (Code/scripts/spin.sh).
        spec=${2#spin}; spec=${spec#=}
        kind=${spec%%:*}; kind=${kind:-shell}
        cores=$(nproc); [ "$spec" != "${spec#*:}" ] && cores=${spec#*:}
        echo "spin: $kind loop on $cores of $(nproc) cores, idle priority"
        echo "$mode spin=$kind:$cores" > $STATE
        # Output to /dev/null: it must not hold the ssh session's terminal.
        chrt --idle 0 bash $CODE/scripts/spin.sh $kind $cores noise_test > /dev/null 2>&1 < /dev/null &
        ;;
    esac
    sleep 2
    if pgrep -x aplay > /dev/null || pgrep -x csound > /dev/null || { [ "$mode" = lock ] && pgrep -f "noise_test_load.py --lock" > /dev/null; }; then
        echo "running. Stop with: sudo bash $0 stop"
    else
        echo "audio did not start: is the audio device free? (cpu: see /tmp/noise_test_csound.log)"
    fi
}

stop() {
    [ -f $STATE ] || echo "(no noise test was running, restoring anyway)"
    # gpioset rewrites its command line ("12 1"), so match the name: a
    # -f "...12=1" never matched, and the pin stayed held after stop, so
    # nebio could not drive the reset LED (seen 2026-10-22).
    pkill -x aplay; pkill -x arecord; pkill -x csound; pkill -x gpioset
    pkill -f noise_test_load.py; pkill -f "scripts/spin.sh .* noise_test"  # its loops go with it
    sleep 0.5  # releases nebio's GPIO lines before Nebulae starts
    echo "Pi LEDs, USB, Wi-Fi driver back"
    echo mmc0 > $ACT_LED/trigger
    echo default-on > $PWR_LED/trigger
    [ -e $USB_DRV/$USB_DEV ] || echo $USB_DEV > $USB_DRV/bind
    bash $CODE/scripts/wifi.sh driver
    journalctl --flush
    # Started again as before the test; Nebulae then applies its saved Quiet
    # mode itself (level 1: LAN goes down!). Units Quiet mode masked do not
    # start (no harm).
    echo "services and timers back"
    systemctl start $TIMERS 2>/dev/null
    for s in $SERVICES; do
        ( for i in 1 2 3 4 5; do systemctl start $s 2>/dev/null && break; sleep 2; done ) &
    done
    systemctl start sclang.service
    echo "starting Nebulae (applies its config settings)"
    systemctl start nebulae.service
    rm -f $STATE
    echo "done"
}

status() {
    if [ -f $STATE ]; then echo "noise test running: $(cat $STATE)"; else echo "no noise test running"; fi
    echo "nebulae=$(systemctl is-active nebulae) aplay=$(pgrep -cx aplay) csound=$(pgrep -cx csound) load=$(pgrep -cf noise_test_load.py) usb=$([ -e $USB_DRV/$USB_DEV ] && echo on || echo off) wlan0=$([ -e /sys/class/net/wlan0 ] && echo yes || echo no) lan=$(cat /sys/class/net/end0/operstate) spin=$(( $(pgrep -cx nebulae_spin) + $(pgrep -cf "^sh -c while :; do :; done") )) cpu_temp=$(( $(cat /sys/class/thermal/thermal_zone0/temp) / 1000 ))C"
}

[ "$(id -u)" = 0 ] || { echo "run as root: sudo bash $0 $*"; exit 1; }
case "$1" in
    start) start "$2" "$3" ;;
    stop) stop ;;
    status) status ;;
    # Records the input (cable from output to input) and shows the tones:
    # noise_test.sh measure [seconds] [label]
    measure) shift; python3 $CODE/scripts/noise_measure.py "${1:-10}" "${2:-$(cat $STATE 2>/dev/null || echo nebulae)} ${*:3}" ;;
    *) echo "usage: sudo bash $0 start [silence|thru|poll|leds|cpu|jitter|lock|wake|gpio|spi] [spin|spin=yield|work|shell[:cores]] | stop | status | measure [secs] [label]"; exit 2 ;;
esac
