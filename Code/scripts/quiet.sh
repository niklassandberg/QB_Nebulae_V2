#!/bin/bash
# The quiet settings: only switching, no settings. Nebulae saves them
# (configsettings.py) and runs this when one is changed on the configsettings
# page, and once at its start for the saved ones (all off until then).
# Whatever puts noise on the power is heard by the cheap ADC/DAC on i2s.
#   quiet.sh spin off|yield|shell   "Power regulator" (2_power_regulator.ui):
#       the CPU never sleeps. Every scan woke it from sleep (WFI), a current
#       pulse heard as a tone; a do-nothing loop on all cores at the lowest
#       priority (SCHED_IDLE) keeps the current even. Measured (400 Hz scan
#       tone): none -98.5, yield or nohlt -103.5, shell -107.2 dBFS. yield
#       touches no memory: on a Pi 3 the shell loop slowed Csound (shared
#       cache/bus) to dropouts while recording. The 4th choice, nohlt, is the
#       kernel option (configsettings.py writes /boot/cmdline.txt, restart):
#       with it no spin runs. Pi 3 without heatsink: 83 C, no slowdown.
#   quiet.sh services on|off        "Services no sounds" (4_services_quiet.ui):
#       the Pi's LEDs off (green blinks with every SD card access), USB off
#       while the stick is not in use (usb_power.sh), the system log in RAM,
#       network time sync, netctl-auto and the scheduled jobs stopped.
# "No PWM" (3_no_pwm.ui) is in the LEDs themselves (nebio, ui.py).

CODE=/home/alarm/QB_Nebulae_V2/Code
USB=$CODE/scripts/usb_power.sh
SERVICES="systemd-timesyncd.service netctl-auto@wlan0.service"
# Scheduled jobs: keyring sync goes online weekly, shadow runs at midnight,
# tmpfiles-clean at a random time.
TIMERS="archlinux-keyring-wkd-sync.timer shadow.timer systemd-tmpfiles-clean.timer"
SPIN=nebulae-spin

spin() {  # off | yield | shell
    systemctl stop $SPIN 2>/dev/null
    [ "$1" = off ] && return
    # Started with "nohlt": the kernel itself keeps the cores awake.
    if grep -qw nohlt /proc/cmdline; then
        echo "nohlt: the kernel keeps the cores awake, no spin"; return
    fi
    # Own unit, so it survives a Nebulae restart.
    systemd-run --unit=$SPIN --collect --quiet -p CPUSchedulingPolicy=idle \
        /bin/bash $CODE/scripts/spin.sh $1
}

# The Pi's green/red LEDs: led0/led1 on kernel 5.15, ACT/PWR on newer kernels.
ACT_LED=/sys/class/leds/ACT; [ -e $ACT_LED ] || ACT_LED=/sys/class/leds/led0
PWR_LED=/sys/class/leds/PWR; [ -e $PWR_LED ] || PWR_LED=/sys/class/leds/led1

services() {  # on | off
    if [ "$1" = on ]; then
        for l in $ACT_LED $PWR_LED; do
            echo none > $l/trigger
            echo 0 > $l/brightness
        done
        bash $USB off
        journalctl --relinquish-var
        # --runtime: until the next reboot. In the background: mask reloads
        # systemd (1.4 s), stopping netctl-auto takes ~1.4 s.
        if [ "$(systemctl is-enabled systemd-timesyncd.service 2>/dev/null)" != masked-runtime ]; then
            ( systemctl mask --runtime $SERVICES $TIMERS; systemctl stop $SERVICES $TIMERS ) &
        fi
    else
        echo mmc0 > $ACT_LED/trigger
        echo default-on > $PWR_LED/trigger
        bash $USB on
        systemctl unmask --runtime $SERVICES $TIMERS
        systemctl start $TIMERS
        journalctl --flush
        # Right after the unmask netctl-auto can fail once; a few seconds later it starts.
        for s in $SERVICES; do
            ( for i in 1 2 3 4 5; do systemctl start $s && break; sleep 2; done ) &
        done
    fi
}

case "$1 $2" in
    "spin off"|"spin yield"|"spin shell") spin $2 ;;
    "services on"|"services off") services $2 ;;
    *) echo "usage: $0 spin off|yield|shell | services on|off"; exit 2 ;;
esac
exit 0
