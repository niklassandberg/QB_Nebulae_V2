#!/bin/bash
# Switches the quiet settings (saved by configsettings.py). Power noise is
# heard through the codec.
#   quiet.sh spin off|yield|shell   the CPU never sleeps: each wake-up was a
#                                   tone. yield, as shell slows Csound on a Pi 3.
#   quiet.sh services on|off        Pi LEDs, USB, log in RAM, time sync,
#                                   netctl-auto and timers off

CODE=/home/alarm/QB_Nebulae_V2/Code
USB=$CODE/scripts/usb_power.sh
SERVICES="systemd-timesyncd.service netctl-auto@wlan0.service"
TIMERS="archlinux-keyring-wkd-sync.timer shadow.timer systemd-tmpfiles-clean.timer"
SPIN=nebulae-spin

spin() {  # off | yield | shell
    systemctl stop $SPIN 2>/dev/null
    [ "$1" = off ] && return
    if grep -qw nohlt /proc/cmdline; then
        echo "nohlt: the kernel keeps the cores awake, no spin"; return
    fi
    # Own unit: survives a Nebulae restart.
    systemd-run --unit=$SPIN --collect --quiet -p CPUSchedulingPolicy=idle \
        /bin/bash $CODE/scripts/spin.sh $1
}

# led0/led1 on kernel 5.15, ACT/PWR on newer kernels.
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
        # In the background: each takes ~1.4 s.
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
        # netctl-auto can fail once right after the unmask.
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
