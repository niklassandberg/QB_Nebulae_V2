#!/bin/bash
# Needs root. The services start it as root; started by hand it runs
# itself again with sudo (sudo as root only adds lines to the journal).
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"

case "${1}" in
    rw)
        mount -o remount,rw /
        echo "Filesystem mounted in READ-WRITE mode"
        ;;
    ro)
        mount -o remount,ro /
        echo "Filesystem mounted in READ-ONLY mode"
        ;;
    *)
        if [ -n "$(mount | grep mmcblk0p2 | grep -o 'rw')" ]
        then
            echo "Filesystem is mounted in READ-WRITE mode"
        else
            echo "Filesystem is mounted in READ-ONLY mode"
        fi
        echo "Usage ${0} [rw|ro]"
        ;;
    esac
exit 0
