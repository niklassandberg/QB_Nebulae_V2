#!/bin/bash
# Raspberry Pi 4 bootloader (EEPROM) update, only when asked for: a file
# called "update_bootloader" on the USB stick (update.sh removes it and runs
# "eeprom_update.sh flash"). The kit in Code/localfiles/eeprom (pieeprom.upd
# + .sig, recovery.bin) is the bootloader 2026-09-23 with the Nebulae config
# (~0.9 s faster to the kernel than older ones).
#
#   eeprom_update.sh flash   (update.sh, stick mounted) 64-bit image and an
#                            older bootloader: copies the kit to /boot and
#                            reboots; the Pi's firmware flashes it (a few
#                            seconds, green LED blinks; do not switch the
#                            power off then) and starts normally.
#   eeprom_update.sh         (startup.sh, every boot) after a flash: removes
#                            the files from /boot and logs the result.
#                            Otherwise nothing (no /boot access: it is an
#                            automount, the first access waits ~1.5 s at boot).
#
# Only on the 64-bit image (aarch64, kernel 6 or newer): the old 32-bit image
# (kernel 5.15) has no USB with this bootloader (no vl805.bin). To go back to
# the 32-bit image on a Pi with this bootloader, first flash an older
# bootloader (Raspberry Pi Imager: Misc utility images > Bootloader, or an
# older release from github.com/raspberrypi/rpi-eeprom).
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
    # After a flash: clean /boot and log.
    sh $MOUNTFS rw
    sudo rm -f /boot/RECOVERY.000 /boot/recovery.bin /boot/pieeprom.upd /boot/pieeprom.sig
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
sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py updating &
sh $MOUNTFS rw
sudo cp $KIT/pieeprom.upd $KIT/pieeprom.sig $KIT/recovery.bin /boot/ || { sh $MOUNTFS ro; exit 0; }
echo "$kit" > $MARK
sync
sudo umount /dev/sda1 2>/dev/null
sudo reboot
sleep 30
