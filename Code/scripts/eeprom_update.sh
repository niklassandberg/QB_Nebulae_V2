#!/bin/bash
# Pi 4 bootloader update from Code/localfiles/eeprom, 64-bit image only (the
# 32-bit image has no USB with this bootloader).
#   eeprom_update.sh flash   copy the kit to /boot and reboot; the firmware flashes
#   eeprom_update.sh         after a flash: clean /boot and log

# Needs root.
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"
KIT=/home/alarm/QB_Nebulae_V2/Code/localfiles/eeprom
MARK=/home/alarm/.eeprom_update   # kit timestamp while a flash is pending
TS=/proc/device-tree/chosen/bootloader/build-timestamp
MOUNTFS=/home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh
LOG=/mnt/memory/neb_log.txt       # on the stick (flash only)

say() {
    echo "$1"
    [ "$MODE" = flash ] && echo "$(date +"%a %D - %T") - $1" >> $LOG
}
day() { date -u -d @"$1" +%F; }

MODE=$1
current=$([ -r $TS ] && echo $((16#$(od -An -tx1 $TS | tr -d ' \n'))))
kit=$(awk '/^ts:/{print $2}' $KIT/pieeprom.sig 2>/dev/null)

if [ "$MODE" != flash ]; then
    [ -f $MARK ] || exit 0
    sh $MOUNTFS rw
    rm -f /boot/RECOVERY.000 /boot/recovery.bin /boot/pieeprom.upd /boot/pieeprom.sig
    if [ -n "$current" ] && [ "$current" -ge "$(cat $MARK)" ]; then
        echo "EEPROM bootloader updated ($(day $current))"
    else
        echo "EEPROM bootloader update FAILED (still $(day ${current:-0}))"
    fi
    rm -f $MARK
    sync
    sh $MOUNTFS ro
    exit 0
fi

if [ "$(uname -m)" != aarch64 ] || ! [ "$(uname -r | cut -d. -f1)" -ge 6 ] 2>/dev/null; then
    say "bootloader update: not on this image (needs the 64-bit image), nothing done"
    exit 0
fi
if [ -z "$current" ] || [ -z "$kit" ]; then
    say "bootloader update: no bootloader version or no kit, nothing done"
    exit 0
fi
if [ "$current" -ge "$kit" ]; then
    say "bootloader update: already $(day $current), nothing done"
    exit 0
fi
# The image must match its signature file, or recovery.bin would refuse it.
if [ "$(sha256sum $KIT/pieeprom.upd | cut -d' ' -f1)" != "$(head -1 $KIT/pieeprom.sig)" ]; then
    say "bootloader update: kit damaged (checksum), nothing done"
    exit 0
fi

say "bootloader update: $(day $current) -> $(day $kit), flashing at the next boot"
sync
pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py updating &
sh $MOUNTFS rw
cp $KIT/pieeprom.upd $KIT/pieeprom.sig $KIT/recovery.bin /boot/ || { sh $MOUNTFS ro; exit 0; }
echo "$kit" > $MARK
sync
umount /dev/sda1 2>/dev/null
reboot
sleep 30
