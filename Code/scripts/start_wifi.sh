#!/bin/bash
# Needs root. The services start it as root; started by hand it runs
# itself again with sudo (sudo as root only adds lines to the journal).
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"

#enable network so wpa_suppliant gets active (buzz sound).
rfkill unblock wifi

# usb_power.sh: quiet mode keeps USB off except while the stick is in use.
# Put back as it was: off again only if it was off.
bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh status; USB_WAS_ON=$?
bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh on
mount /dev/sda1 /mnt/memory
rm /home/alarm/wifi.log
if [ -f /mnt/memory/wlan0-wifi ]
then
  echo starting wlan0-wifi> /home/alarm/wifi.log
  # Cleaned on the way: any quotes people write -> plain '...' for netctl.
  ( umask 077; bash /home/alarm/QB_Nebulae_V2/Code/scripts/wifi_profile.sh clean /mnt/memory/wlan0-wifi > /etc/netctl/wlan0-wifi )
  ( sleep 10; systemctl start systemd-resolved; netctl start wlan0-wifi; iwconfig >> /home/alarm/wifi.log 2>&1 ) & 
else
  echo starting access point > /home/alarm/wifi.log
  ( sleep 10; systemctl start systemd-resolved; netctl stop-all; pkill -f "wpa_supplicant.*wlan0"; pkill -f "wpa_cli.*wlan0"; sleep 2; sh /home/alarm/QB_Nebulae_V2/Code/scripts/create_ap.sh --no-virt -c 6 -n wlan0 Nebulae eurorack >> /home/alarm/wifi.log 2>&1 ) &
fi

umount /dev/sda1
[ $USB_WAS_ON = 0 ] || bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh off
( sleep 10; systemctl start NebFile ) &
