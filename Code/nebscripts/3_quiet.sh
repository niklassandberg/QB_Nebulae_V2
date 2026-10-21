#!/bin/bash
# Quiet mode on/off, from the scripts page of the instr selector.
# For feedback patching everything that is not needed to play is switched
# off: whatever puts noise on the power is heard by the cheap ADC/DAC on i2s.
#   3_quiet.sh          toggle
#   3_quiet.sh on|off
#   3_quiet.sh apply    at boot (startup.sh): on if the setting is saved
#   3_quiet.sh status   exit 0 = on, 1 = off (slot LED bright/dim; nebulae-status)
#
# On:
#  - Ethernet (LAN) down: the gigabit PHY stops sending (no ssh!)
#  - USB off (usb_power.sh): only switched on while the stick is in use
#    (instrument/audio load, freeze write), then off again
#  - the Pi's own LEDs off (green blinks with every SD card access)
#  - file (next) LED only fully on or off: its PWM is heard in the audio;
#    the other LEDs keep PWM, but each channel starts its pulse at its own
#    point of the period, so they do not all switch at once (nebio, via ui.py)
#  - Wi-Fi/Bluetooth chip driver removed (chip without firmware, not just
#    radio-blocked); scheduled jobs (systemd timers) stopped
#  - system log (journald) kept in RAM instead of the SD card
#  - network time sync (timesyncd, writes its clock file) stopped
#  - wpa_supplicant (netctl-auto, runs even with the radio off) stopped
#  - Wi-Fi off (can still be switched on after this with 1_wifi.sh)
#  - Nebulae's status lines (every 10 s) not logged (controlhandler.py)
#  - spin: the CPU never sleeps. Every scan woke it from sleep (WFI), a
#    current pulse heard as a tone (noise_test.sh "wake"); a do-nothing loop
#    on every core at the lowest priority (SCHED_IDLE, all real work goes
#    first) keeps the current even. Own unit nebulae-spin, so it survives a
#    Nebulae restart. Costs ~1-2 W and heat (51 C tested, no throttling).
# Off: all back as normal. The choice is saved and survives a reboot.

CODE=/home/alarm/QB_Nebulae_V2/Code
FLAG=$CODE/config/quiet_mode
WIFI=$CODE/nebscripts/1_wifi.sh
USB=$CODE/scripts/usb_power.sh
SERVICES="systemd-timesyncd.service netctl-auto@wlan0.service"
# Scheduled jobs: keyring sync goes online weekly, shadow runs at midnight,
# tmpfiles-clean at a random time.
TIMERS="archlinux-keyring-wkd-sync.timer shadow.timer systemd-tmpfiles-clean.timer"
# Wi-Fi/Bluetooth chip driver: removed, so the chip is not just radio-blocked
# but without firmware. 1_wifi.sh loads it again when Wi-Fi is switched on.
WIFI_MODULES="brcmfmac"
LAN=end0
SPIN=nebulae-spin

spin() {  # on | off
    if [ "$1" = on ]; then
        systemctl is-active --quiet $SPIN && return
        systemd-run --unit=$SPIN --collect --quiet -p CPUSchedulingPolicy=idle \
            /bin/bash $CODE/scripts/spin.sh
    else
        systemctl stop $SPIN 2>/dev/null
    fi
}

# The root file system may be read-only; only remount if it is (Nebulae
# itself may be running with it read-write).
save() {
    if [ ! -w $CODE/config ]; then
        mount -o remount,rw / && "$@"; mount -o remount,ro /
    else
        "$@"
    fi
}

leds() {  # off | on
    if [ "$1" = off ]; then
        for l in led0 led1; do
            echo none > /sys/class/leds/$l/trigger
            echo 0 > /sys/class/leds/$l/brightness
        done
    else
        echo mmc0 > /sys/class/leds/led0/trigger
        echo default-on > /sys/class/leds/led1/trigger
    fi
}

quiet_on() {
    echo "quiet on"
    ip link set $LAN down
    leds off
    spin on
    journalctl --relinquish-var
    # --runtime: blocked until the next reboot, so a late start at boot
    # cannot bring them back. In the background: mask reloads systemd
    # (1.4 s) and stopping netctl-auto takes ~1.4 s; nothing waits for them.
    # The Wi-Fi driver goes last, when nothing uses wlan0 any more.
    ( systemctl mask --runtime $SERVICES $TIMERS; systemctl stop $SERVICES $TIMERS
      systemctl is-active --quiet nebwifi.service || modprobe -r $WIFI_MODULES ) &
}

quiet_off() {
    echo "quiet off"
    ip link set $LAN up
    leds on
    spin off
    bash $USB on
    bash $WIFI driver   # Wi-Fi driver back, radio still blocked
    systemctl unmask --runtime $SERVICES $TIMERS
    systemctl start $TIMERS
    journalctl --flush
    # Right after the unmask netctl-auto can fail once ("Could not create
    # the configuration file"); a few seconds later it starts fine.
    for s in $SERVICES; do
        ( for i in 1 2 3 4 5; do systemctl start $s && break; sleep 2; done ) &
    done
}

case "$1" in
    status) if [ -f $FLAG ]; then exit 0; else exit 1; fi ;;
    on) save touch $FLAG; quiet_on; bash $USB off; bash $WIFI off ;;
    off) save rm -f $FLAG; quiet_off ;;
    # Boot: Wi-Fi is off already, and USB is switched off by the file loader
    # after Nebulae's first load from the stick.
    apply) [ -f $FLAG ] && quiet_on ;;
    "") if [ -f $FLAG ]; then bash "$0" off; else bash "$0" on; fi ;;
    *) echo "usage: $0 [on|off|apply|status]"; exit 2 ;;
esac
exit 0
