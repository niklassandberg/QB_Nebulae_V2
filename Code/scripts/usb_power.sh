#!/bin/bash
# USB on/off for quiet mode (Code/scripts/quiet.sh). Off = the USB
# controller (VL805 on PCIe) is unbound from its driver: no bus traffic, no
# 8 kHz microframes. Everything that uses the stick calls "on" before it
# mounts and, in quiet mode, "off" after it unmounts (the caller knows the
# mode: configSettings.servicesQuiet in Nebulae; NebFile and start_wifi.sh put
# back what they found), so in quiet mode USB is only on while the stick is in
# use.
#   usb_power.sh on       bind the controller if needed, wait for the stick
#   usb_power.sh off      unbind, if nothing is mounted
#   usb_power.sh status   exit 0 = on

DEV=0000:01:00.0
DRV=/sys/bus/pci/drivers/xhci_hcd

case "$1" in
    on)
        if [ ! -e $DRV/$DEV ]; then
            echo $DEV > $DRV/bind
            # A stick shows up as usb-storage within ~1 s; with none, stop
            # waiting after 2 s. usb-storage then waits 1 s before sda1.
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
