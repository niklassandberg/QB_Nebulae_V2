#!/bin/bash
# /home/alarm/checkfirmware.sh - run by nebulae.service at boot (not part of
# the firmware update, so a broken update cannot remove it).
#
# Same checks as the original image's script: every file in
# /home/alarm/mandatory_files.txt must exist (non-empty) in the firmware, and a
# file "revert_to_factory_firmware" on the USB stick asks for a revert.
# Then it runs startup.sh.
#
# Revert on the aarch64 image: the original script unpacked
# /home/alarm/neb_factory_fw.zip (2020 firmware, Python 2), which cannot run
# here. This one goes back to the previous firmware that update.sh keeps in
# /home/alarm/backup/old/QB_Nebulae_V2.
primarypath=/home/alarm/QB_Nebulae_V2/Code
filelist=/home/alarm/mandatory_files.txt
previous=/home/alarm/backup/old/QB_Nebulae_V2

foundc=0
nfoundc=0
while read -r file_a; do
    [ -z "$file_a" ] && continue
    if [[ -s "$primarypath/${file_a}" ]]; then
        foundc=$((foundc + 1))
    else
        nfoundc=$((nfoundc + 1))
        echo "missing: $file_a"
    fi
done < $filelist

# nebulae.service starts before the USB stick is there (/boot is an automount,
# setup_system.sh): the stick comes ~3.3 s after kernel start. Wait for it,
# but not past 4.5 s (no stick in).
while [ ! -b /dev/sda1 ] && [ "$(cut -d' ' -f1 /proc/uptime | tr -d .)" -lt 450 ]; do
    sleep 0.05
done
mount /dev/sda1 /mnt/memory 2>/dev/null
logfile="/mnt/memory/neb_log.txt"
if [ ! -f $logfile ]; then
    logfile="/tmp/checkfirmware_log.txt"
fi
echo "Number of files in [$filelist] found = [${foundc}]" >> $logfile
echo "Number of files in [$filelist] NOT found = [${nfoundc}]" >> $logfile

revertfirmware=0
if [ "$nfoundc" -eq "0" ]; then
    echo "No Missing Files." >> $logfile
    if [ -f /mnt/memory/revert_to_factory_firmware ]; then
        revertfirmware=1
        echo "Found Firmware Reversion Request. Deleting Request File" >> $logfile
        rm /mnt/memory/revert_to_factory_firmware
    fi
else
    revertfirmware=1
fi

if [ "$revertfirmware" -eq "1" ] && [ -f "$previous/Code/scripts/startup.sh" ]; then
    mount -o remount,rw /
    echo "Reverting to the previous firmware ($previous)." >> $logfile
    rm -rf /home/alarm/QB_Nebulae_V2.broken
    mv /home/alarm/QB_Nebulae_V2 /home/alarm/QB_Nebulae_V2.broken 2>/dev/null
    cp -a "$previous" /home/alarm/QB_Nebulae_V2
    sync
elif [ "$revertfirmware" -eq "1" ]; then
    echo "Revert requested, but there is no previous firmware in $previous." >> $logfile
fi

# No global sync here (the revert above has its own): umount writes the stick's
# log out, and a sync of every file system cost ~0.3 s during boot.
umount /dev/sda1 2>/dev/null
exec bash $primarypath/scripts/startup.sh
