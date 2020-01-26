#!/bin/bash
( sleep 10; systemctl start systemd-resolved; sh /home/alarm/QB_Nebulae_V2/Code/scripts/create_ap.sh --no-virt -n wlan0 Nebulae eurorack >/home/alarm/wifi.log 2>&1 ) & 
( sleep 10; systemctl start NebFile ) &

