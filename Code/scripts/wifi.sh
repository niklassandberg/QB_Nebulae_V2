#!/bin/bash
# Switches Wi-Fi on or off; only switching, no settings. Nebulae saves the
# setting (configsettings.py) and runs "wifi.sh on|off" when it is changed on
# the configsettings page (1_wifi.ui), and once at its start for the saved setting
# (Wi-Fi is off until then: startup.sh blocks the radio).
#   wifi.sh on|off
#   wifi.sh driver   load the Wi-Fi driver (after Quiet level 1 removed it)
# "On" is nebwifi.service (start_wifi.sh): the home network if wlan0-wifi is
# on the USB stick, else the Nebulae access point + NebFile.

# Quiet level 1 (Code/scripts/quiet.sh) removes the Wi-Fi driver; load it again and wait
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

# Also at Nebulae's start when it is off: startup.sh's early "rfkill block
# wifi" comes before the Wi-Fi driver has loaded (~8 s), which then starts
# with the radio unblocked.
wifi_off() {
    echo "wifi off"
    systemctl stop NebFile.service
    # Kills what start_wifi.sh left running (create_ap, its delayed starts).
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
