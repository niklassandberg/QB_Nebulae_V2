#!/bin/bash
# Quiet mode levels: switches the system. For feedback patching everything
# that is not needed to play is switched off: whatever puts noise on the
# power is heard by the cheap ADC/DAC on i2s.
# Only switching, no settings: Nebulae saves the level (configsettings.py)
# and runs "quiet.sh change OLD NEW" when it is chosen on the scripts page
# (3_quiet.ui), and "quiet.sh change 0 N" once at its start for the saved
# level (Quiet mode is off until then). Wi-Fi off is done by Nebulae too.
#   quiet.sh change OLD NEW   from level OLD to NEW (0-3, 0 = off)
#
# Every level (1-3):
#  - USB off (usb_power.sh): only switched on while the stick is in use
#    (instrument/audio load, freeze write), then off again
#  - the Pi's own LEDs off (green blinks with every SD card access)
#  - LED PWM channels staggered in time (nebio, via ui.py)
#  - scheduled jobs (systemd timers), network time sync (timesyncd, writes
#    its clock file) and wpa_supplicant (netctl-auto) stopped
#  - system log (journald) kept in RAM instead of the SD card
#  - Wi-Fi off (by Nebulae; can be switched on again after this, levels
#    2 and 3 only)
#  - Nebulae's status lines (every 10 s) not logged (controlhandler.py)
#  - spin: the CPU never sleeps. Every scan woke it from sleep (WFI), a
#    current pulse heard as a tone (noise_test.sh "wake"); a do-nothing shell
#    loop (Code/scripts/spin.sh shell) on all 4 cores at the lowest priority
#    (SCHED_IDLE, all real work goes first) keeps the current even. Measured
#    (noise_measure.py, 400 Hz scan tone): none -98.5, yield or nohlt -103.5,
#    shell -107.2 dBFS; fewer than 4 cores was clearly worse by ear. Own unit
#    nebulae-spin, so it survives a Nebulae restart. Costs ~1-2 W and heat
#    (51 C tested, no throttling).
#    Pi 3 without heatsink: 82-83 C with the loops, spin.sh pauses them
#    above 80 C (its firmware throttles at 85 C). The glitches seen there
#    with spin came from Csound being too slow (the unoptimised Arch
#    package), not from the loops; see Resources/engines/csound.
# Level 1: also Ethernet (LAN) down (the gigabit PHY stops sending, no ssh!)
#          and the Wi-Fi/Bluetooth chip driver removed (chip without firmware)
# Level 2: LAN on, Wi-Fi chip driver loaded (radio off until Wi-Fi is on)
# Level 1 and 2: the file (next) and freeze LEDs only fully on or off: their
#          PWM is heard in the audio (ui.py reads the level). Level 3: both
#          with PWM.

CODE=/home/alarm/QB_Nebulae_V2/Code
WIFI=$CODE/scripts/wifi.sh
USB=$CODE/scripts/usb_power.sh
SERVICES="systemd-timesyncd.service netctl-auto@wlan0.service"
# Scheduled jobs: keyring sync goes online weekly, shadow runs at midnight,
# tmpfiles-clean at a random time.
TIMERS="archlinux-keyring-wkd-sync.timer shadow.timer systemd-tmpfiles-clean.timer"
WIFI_MODULES="brcmfmac"
LAN=end0
SPIN=nebulae-spin

spin() {  # on | off
    if [ "$1" = on ]; then
        systemctl is-active --quiet $SPIN && return
        systemd-run --unit=$SPIN --collect --quiet -p CPUSchedulingPolicy=idle \
            /bin/bash $CODE/scripts/spin.sh shell
    else
        systemctl stop $SPIN 2>/dev/null
    fi
}

# The Pi's green/red LEDs: led0/led1 on kernel 5.15, ACT/PWR on newer kernels.
ACT_LED=/sys/class/leds/ACT; [ -e $ACT_LED ] || ACT_LED=/sys/class/leds/led0
PWR_LED=/sys/class/leds/PWR; [ -e $PWR_LED ] || PWR_LED=/sys/class/leds/led1

leds() {  # off | on
    if [ "$1" = off ]; then
        for l in $ACT_LED $PWR_LED; do
            echo none > $l/trigger
            echo 0 > $l/brightness
        done
    else
        echo mmc0 > $ACT_LED/trigger
        echo default-on > $PWR_LED/trigger
    fi
}

# Everything every level has. Only what is not done yet: from one level to
# another nothing is restarted.
common_on() {
    leds off
    spin on
    journalctl --relinquish-var
    # --runtime: blocked until the next reboot, so a late start cannot bring
    # them back. In the background: mask reloads systemd (1.4 s) and stopping
    # netctl-auto takes ~1.4 s; nothing waits for them.
    if [ "$(systemctl is-enabled systemd-timesyncd.service 2>/dev/null)" != masked-runtime ]; then
        ( systemctl mask --runtime $SERVICES $TIMERS; systemctl stop $SERVICES $TIMERS ) &
    fi
}

common_off() {
    leds on
    spin off
    bash $USB on
    systemctl unmask --runtime $SERVICES $TIMERS
    systemctl start $TIMERS
    journalctl --flush
    # Right after the unmask netctl-auto can fail once ("Could not create
    # the configuration file"); a few seconds later it starts fine.
    for s in $SERVICES; do
        ( for i in 1 2 3 4 5; do systemctl start $s && break; sleep 2; done ) &
    done
}

# Level 1 only: LAN down and the Wi-Fi chip without driver; levels 2/3: both
# back (radio still blocked until Wi-Fi is switched on).
network() {  # 1 | 2
    if [ "$1" = 1 ]; then
        ip link set $LAN down
        # The driver goes when nothing uses wlan0 any more (after the stop).
        ( sleep 3; systemctl is-active --quiet nebwifi.service || modprobe -r $WIFI_MODULES ) &
    else
        ip link set $LAN up
        bash $WIFI driver
    fi
}

change() {  # old new
    old=$1; new=$2
    echo "quiet $old -> $new"
    if [ "$new" = 0 ]; then
        [ "$old" = 0 ] && return
        network 2
        common_off
        return
    fi
    common_on
    [ "$old" = 0 ] && bash $USB off  # Wi-Fi: switched off by Nebulae
    if [ "$new" = 1 ]; then network 1; else network 2; fi
}

case "$1" in
    change)
        case "$2$3" in [0-3][0-3]) change $2 $3 ;; *) echo "levels 0-3"; exit 2 ;; esac ;;
    *) echo "usage: $0 change OLD NEW"; exit 2 ;;
esac
exit 0
