#!/bin/bash
# Noise test: everything off except the codec and the LAN. Root, over ssh:
#   noise_test.sh start [STEP] [spin|spin=yield|work|shell[:cores]]
#     silence (default)  the DAC plays digital zero
#     thru               ADC -> DAC
#     poll               + nebio scans, a Python loop (noise_test_load.py)
#     leds               + every LED at half brightness
#     cpu                + Csound with the granular looper's DSP load, muted
#     jitter, lock       poll with random / audio-clocked scans
#     wake, gpio, spi    only CPU wake-ups / GPIO / SPI at the scan rates
#   noise_test.sh stop      everything back, Nebulae starts again
#   noise_test.sh status
#   noise_test.sh measure [seconds] [label]

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

# Csound as Nebulae runs it, CPU_VOICES voices muted; the input stays free.
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
    systemctl stop nebulae.service sclang.service 'jack@*.service' 2>/dev/null
    pkill -x scsynth; pkill -x jackd; pkill -x pd
    # Right after "stop" Nebulae may still hold the card.
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
    modprobe -r brcmfmac_cyw brcmfmac 2>/dev/null || modprobe -r brcmfmac 2>/dev/null
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
    # gpioset rewrites its command line: match the name.
    pkill -x aplay; pkill -x arecord; pkill -x csound; pkill -x gpioset
    pkill -f noise_test_load.py; pkill -f "scripts/spin.sh .* noise_test"  # its loops go with it
    sleep 0.5  # releases nebio's GPIO lines before Nebulae starts
    echo "Pi LEDs, USB, Wi-Fi driver back"
    echo mmc0 > $ACT_LED/trigger
    echo default-on > $PWR_LED/trigger
    [ -e $USB_DRV/$USB_DEV ] || echo $USB_DEV > $USB_DRV/bind
    bash $CODE/scripts/wifi.sh driver
    journalctl --flush
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
    measure) shift; python3 $CODE/scripts/noise_measure.py "${1:-10}" "${2:-$(cat $STATE 2>/dev/null || echo nebulae)} ${*:3}" ;;
    *) echo "usage: sudo bash $0 start [silence|thru|poll|leds|cpu|jitter|lock|wake|gpio|spi] [spin|spin=yield|work|shell[:cores]] | stop | status | measure [secs] [label]"; exit 2 ;;
esac
