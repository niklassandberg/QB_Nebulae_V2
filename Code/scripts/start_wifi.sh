#!/bin/bash

mount /dev/sda1 /mnt/memory
if [ -f /mnt/memory/wlan0-wifi ]
then
  cp /mnt/memory/wlan0-wifi /etc/netctl
  netctl start wlan0-wifi
else
  ( sleep 10; systemctl start systemd-resolved; sh /home/alarm/QB_Nebulae_V2/Code/scripts/create_ap.sh --no-virt -n wlan0 Nebulae eurorack >/home/alarm/wifi.log 2>&1 ) & 
fi

umount /dev/sda1
( sleep 10; systemctl start NebFile ) &
