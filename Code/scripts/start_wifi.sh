#!/bin/bash
# Needs root.
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"

#enable network so wpa_suppliant gets active (buzz sound).
rfkill unblock wifi

# USB put back as it was.
bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh status; USB_WAS_ON=$?
bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh on
mount /dev/sda1 /mnt/memory
rm /home/alarm/wifi.log
if [ -f /mnt/memory/wlan0-wifi ]
then
  echo starting wlan0-wifi> /home/alarm/wifi.log
  ( umask 077; bash /home/alarm/QB_Nebulae_V2/Code/scripts/wifi_profile.sh clean /mnt/memory/wlan0-wifi > /etc/netctl/wlan0-wifi )
  ( sleep 10; systemctl start systemd-resolved; netctl start wlan0-wifi; iwconfig >> /home/alarm/wifi.log 2>&1 ) & 
else
  echo starting access point > /home/alarm/wifi.log
  ( sleep 10; systemctl start systemd-resolved; netctl stop-all; pkill -f "wpa_supplicant.*wlan0"; pkill -f "wpa_cli.*wlan0"; sleep 2; sh /home/alarm/QB_Nebulae_V2/Code/scripts/create_ap.sh --no-virt -c 6 -n wlan0 Nebulae eurorack >> /home/alarm/wifi.log 2>&1 ) &
fi

umount /dev/sda1
[ $USB_WAS_ON = 0 ] || bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh off
( sleep 10; systemctl start NebFile ) &
