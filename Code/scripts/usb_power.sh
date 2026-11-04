#!/bin/bash
# USB on/off for quiet mode: the controller unbound, no 8 kHz microframes.
#   usb_power.sh on       bind the controller if needed, wait for the stick
#   usb_power.sh off      unbind, if nothing is mounted
#   usb_power.sh status   exit 0 = on

DEV=0000:01:00.0
DRV=/sys/bus/pci/drivers/xhci_hcd

case "$1" in
    on)
        if [ ! -e $DRV/$DEV ]; then
            echo $DEV > $DRV/bind
            # A stick shows up within ~1 s; sda1 1 s later.
            for i in $(seq 1 10); do
                ls -d /sys/bus/usb/drivers/usb-storage/*:* >/dev/null 2>&1 && break
                sleep 0.2
            done
            if ls -d /sys/bus/usb/drivers/usb-storage/*:* >/dev/null 2>&1; then
                for i in $(seq 1 30); do [ -b /dev/sda1 ] && break; sleep 0.2; done
            fi
        fi
        ;;
    off)
        grep -q " /mnt/memory " /proc/mounts && exit 0
        [ -e $DRV/$DEV ] && echo $DEV > $DRV/unbind
        ;;
    status)
        [ -e $DRV/$DEV ] && exit 0 || exit 1
        ;;
esac
exit 0
