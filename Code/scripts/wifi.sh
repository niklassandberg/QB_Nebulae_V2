#!/bin/bash
#   wifi.sh on|off
#   wifi.sh driver   load the Wi-Fi driver
# On: the home network if wlan0-wifi is on the stick, else the access point.

# The radio stays blocked until start_wifi.sh unblocks it.
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

# Also at start: the driver loads after startup.sh's rfkill block.
wifi_off() {
    echo "wifi off"
    systemctl stop NebFile.service
    systemctl stop nebwifi.service
    netctl stop-all
    rfkill block wifi
}

case "$1" in
    on) wifi_on ;;
    off) wifi_off ;;
    driver) driver ;;
    *) echo "usage: $0 on|off|driver"; exit 2 ;;
esac
