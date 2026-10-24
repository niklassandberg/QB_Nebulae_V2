#!/bin/bash
# Quiet mode levels. Chosen on the scripts page of the instr selector
# (Code/nebscripts/3_quiet.ui: speed encoder picks the level, ui.py runs
# "quiet.sh set N"). For feedback patching everything that is not needed to
# play is switched off: whatever puts noise on the power is heard by the
# cheap ADC/DAC on i2s.
#   quiet.sh set 0|1|2|3   0 = off
#   quiet.sh apply         at boot (startup.sh): the saved level
#   quiet.sh status        exit 0 = a level is on, 1 = off; prints the level
# The level is saved in $FLAG (its content; an old empty file = level 1)
# and survives a reboot.
#
# Every level (1-3):
#  - USB off (usb_power.sh): only switched on while the stick is in use
#    (instrument/audio load, freeze write), then off again
#  - the Pi's own LEDs off (green blinks with every SD card access)
#  - LED PWM channels staggered in time (nebio, via ui.py)
#  - scheduled jobs (systemd timers), network time sync (timesyncd, writes
#    its clock file) and wpa_supplicant (netctl-auto) stopped
#  - system log (journald) kept in RAM instead of the SD card
#  - Wi-Fi off (can still be switched on after this with 1_wifi.sh, levels
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
FLAG=$CODE/config/quiet_mode
WIFI=$CODE/nebscripts/1_wifi.sh
USB=$CODE/scripts/usb_power.sh
SERVICES="systemd-timesyncd.service netctl-auto@wlan0.service"
# Scheduled jobs: keyring sync goes online weekly, shadow runs at midnight,
# tmpfiles-clean at a random time.
TIMERS="archlinux-keyring-wkd-sync.timer shadow.timer systemd-tmpfiles-clean.timer"
WIFI_MODULES="brcmfmac"
LAN=end0
SPIN=nebulae-spin

level() {  # saved level, 0 = off
    [ -f $FLAG ] || { echo 0; return; }
    l=$(tr -dc 0-9 < $FLAG)
    echo "${l:-1}"  # empty file (before levels) = level 1
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

save_level() {
    if [ "$1" = 0 ]; then rm -f $FLAG; else echo "$1" > $FLAG; fi
}

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
    # At boot in the background: systemd is still busy with its own start
    # then and took 1.4 s to answer systemd-run, and nothing waits for these.
    if [ -n "$BOOT" ]; then
        ( spin on; journalctl --relinquish-var ) &
    else
        spin on
        journalctl --relinquish-var
    fi
    # --runtime: blocked until the next reboot, so a late start at boot
    # cannot bring them back. In the background: mask reloads systemd
    # (1.4 s) and stopping netctl-auto takes ~1.4 s; nothing waits for them.
    # At boot (BOOT=1) it waits until Nebulae has loaded its first instrument:
    # the systemd reload of the mask made update.sh's USB stick mount wait for
    # it (0.04 -> 0.74 s).
    if [ "$(systemctl is-enabled systemd-timesyncd.service 2>/dev/null)" != masked-runtime ]; then
        ( if [ -n "$BOOT" ]; then
              for i in $(seq 60); do
                  [ -e /run/nebulae-ui-ready ] && break  # written by nebulae.py loadUI()
                  sleep 0.5
              done
          fi
          systemctl mask --runtime $SERVICES $TIMERS; systemctl stop $SERVICES $TIMERS ) &
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

set_level() {
    new=$1
    old=$(level)
    echo "quiet $old -> $new"
    save save_level $new
    if [ "$new" = 0 ]; then
        [ "$old" = 0 ] && return
        network 2
        common_off
        return
    fi
    common_on
    [ "$old" = 0 ] && { bash $USB off; bash $WIFI off; }
    if [ "$new" = 1 ]; then network 1; else network 2; fi
}

case "$1" in
    status) l=$(level); echo $l; if [ "$l" != 0 ]; then exit 0; else exit 1; fi ;;
    set)
        case "$2" in 0|1|2|3) set_level $2 ;; *) echo "level 0-3"; exit 2 ;; esac ;;
    # Boot: Wi-Fi is off already, and USB is switched off by the file loader
    # after Nebulae's first load from the stick.
    apply)
        l=$(level)
        [ "$l" = 0 ] && exit 0
        BOOT=1 common_on
        [ "$l" = 1 ] && network 1 ;;
    *) echo "usage: $0 set 0|1|2|3 | apply | status"; exit 2 ;;
esac
exit 0
