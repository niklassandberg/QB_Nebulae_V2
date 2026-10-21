#!/bin/bash
# Wi-Fi on/off, from the scripts page of the instr selector.
#   1_wifi.sh          toggle
#   1_wifi.sh on|off
#   1_wifi.sh status   exit 0 = on, 1 = off (slot LED bright/dim; nebulae-status)
# "On" is nebwifi.service (start_wifi.sh): the home network if wlan0-wifi is
# on the USB stick, else the Nebulae access point + NebFile.

is_on() { systemctl is-active --quiet nebwifi.service; }

# Quiet mode (3_quiet.sh) removes the Wi-Fi driver; load it again and wait
# for wlan0. The radio stays blocked until start_wifi.sh unblocks it.
driver() {
    [ -e /sys/class/net/wlan0 ] && return
    modprobe brcmfmac
    for i in $(seq 1 25); do [ -e /sys/class/net/wlan0 ] && break; sleep 0.2; done
    rfkill block wifi
}

wifi_on() {
    echo "wifi on"
    driver
    systemctl start nebwifi.service
}

wifi_off() {
    echo "wifi off"
    systemctl stop NebFile.service
    # Kills what start_wifi.sh left running (create_ap, its delayed starts).
    systemctl stop nebwifi.service
    netctl stop-all
    rfkill block wifi
}

case "$1" in
    status) if is_on; then exit 0; else exit 1; fi ;;  # is-active says 3 for off
    on) wifi_on ;;
    off) wifi_off ;;
    driver) driver ;;
    "") if is_on; then wifi_off; else wifi_on; fi ;;
    *) echo "usage: $0 [on|off|status]"; exit 2 ;;
esac
