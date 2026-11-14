#!/bin/bash
# Needs root.
#   update.sh                  at boot (startup.sh): the update on the USB stick
#   update.sh <neb_update.zip> that file, e.g. copied over the network
#                              (deploy_fw_net.sh); no stick needed
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"
ZIP="${1:-/mnt/memory/neb_update.zip}"
mount /dev/sda1 /mnt/memory 2>/dev/null
# "update_bootloader" on the stick: flash the EEPROM once.
if [ -f /mnt/memory/update_bootloader ]
then
    rm -f /mnt/memory/update_bootloader
    sync
    bash /home/alarm/QB_Nebulae_V2/Code/scripts/eeprom_update.sh flash
fi
# Nothing to install: no remount (~0.3 s at boot).
if [ ! -f "$ZIP" ] && [ ! -d /home/alarm/QB_Nebulae_V2/Code/packages ] \
    && ! ls /mnt/memory/*.tar.xz /mnt/memory/*.tar.zst >/dev/null 2>&1
then
    echo "No Update Detected"
    umount /dev/sda1
    echo "Advancing to the rest of the startup script."
    exit 0
fi
sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
if [ -f "$ZIP" ]
then
    pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
    python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py updating &
    echo "neb_update.zip detected."
    rm -f /mnt/memory/neb_engines_report.txt /mnt/memory/neb_engines_build.log.gz
    echo "Commencing Firmware Update Procedure"
    echo "Creating Backup Directories"
    mkdir -p /home/alarm/backup/new
    mkdir -p /home/alarm/backup/old
    echo "Making sure New Backup Directory is Empty"
    rm -rf /home/alarm/backup/new/*
    echo "Copying neb_update.zip to Backup Directory"
    cp "$ZIP" /home/alarm/backup/new/neb_update.zip
    echo "Extracting Contents of neb_update.zip"
    tar -xvf /home/alarm/backup/new/neb_update.zip -C /home/alarm/backup/new/
    if [ -d /home/alarm/backup/new/QB_Nebulae_V2/Code/nebulae/ ]; then
        # TODO: This can be built upon to check for a list of directories, etc.
        target="/home/alarm/backup/new/QB_Nebulae_V2/Code/nebulae/"
        if find "$target" -mindepth 1 -print -quit | grep -q .; then
            echo "Verified Primary Code Dir has Content."
            echo "Erasing Previous backup with current firmware."
            rm -rf /home/alarm/backup/old/*
            echo "Moving current firmware to backup directory."
            mv /home/alarm/QB_Nebulae_V2/ /home/alarm/backup/old/
            echo "Moving new code into place."
            mv /home/alarm/backup/new/QB_Nebulae_V2/ /home/alarm/
            echo "Changing owner of entire directory from root to alarm"
            chown -R alarm:alarm QB_Nebulae_V2/
        else
            echo "There are no contents within QB_Nebulae_V2/Code/nebulae/"
            echo "The update was improperly prepared."
            echo "Keeping Current Firmware In Place."
        fi
    fi
    # Again, it would REALLY be nice to verify this works before deleting stuff.
    echo "Removing neb_update.zip from USB device. It is safely on the Nebulae."
    source /home/alarm/QB_Nebulae_V2/Code/config.txt
    now=$(date +"%a %D - %T")
    mountpoint -q /mnt/memory && echo "$now - Firmware updated to: $VERSION" >> /mnt/memory/neb_log.txt
    rm -f "$ZIP"
    # check_calibration.py reads the knobs through nebio.
    echo "building nebio for the new firmware"
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/build_nebio.sh
    bash /home/alarm/QB_Nebulae_V2/Code/scripts/engines_check.sh
    python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/check_calibration.py force
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/nebulae.service ]
    then
        echo "updating /etc/systemd/system/nebulae.service for next boot up."
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/nebulae.service > /etc/systemd/system/nebulae.service"
        systemctl --system daemon-reload 
    fi
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/sclang.service ]
    then
        echo "updating /etc/systemd/system/sclang.service for next boot up."
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/sclang.service > /etc/systemd/system/sclang.service"
        systemctl --system daemon-reload
        systemctl enable sclang.service
    fi
    # Started by nebulae.py, never at boot.
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/jack@.service ]
    then
        echo "updating /etc/systemd/system/jack@.service for next boot up."
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/jack@.service > /etc/systemd/system/jack@.service"
        if [ -f /etc/systemd/system/jack.service ]
        then
            systemctl disable jack.service
            rm -f /etc/systemd/system/jack.service
        fi
        systemctl --system daemon-reload
    fi
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/nebwifi.service ]
    then
        echo "updating /etc/systemd/system/nebwifi.service for next boot up."
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/nebwifi.service > /etc/systemd/system/nebwifi.service"
        systemctl --system daemon-reload
    fi
    
    systemctl --system daemon-reload

    reboot
elif [ -d /home/alarm/QB_Nebulae_V2/Code/packages ]
then
    echo "detected firmware pacakges to install" 
    pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
    python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py updating &

    echo "install web services"
    cp /home/alarm/QB_Nebulae_V2/Code/web/NebFile/NebFile.service /etc/systemd/system
    systemctl --system daemon-reload 

    cd /home/alarm/QB_Nebulae_V2/Code/packages

    # Code/packages also holds old armv7h packages.
    ARCH=$(pacman-conf Architecture | head -1)
    PKGS=$(ls *-$ARCH.pkg.tar.* *-any.pkg.tar.* 2>/dev/null)
    if [ -n "$PKGS" ]
    then
        pacman --noconfirm -U $PKGS
        echo "installed packages"
    fi

    if [ "$ARCH" = "armv7h" ]
    then
        echo "install pip3 packages"
        cd python
        echo "installed pip packages"
        pip3 install *
    fi
    cd /home/alarm

    rm -rf /home/alarm/QB_Nebulae_V2/Code/packages

    # In this stage: the first one runs the old firmware's update.sh.
    bash /home/alarm/QB_Nebulae_V2/Code/scripts/kernel_modules.sh

    #TODO: in wrong elif. Should test -d /home/alarm/QB_Nebulae_V2/Code/localfiles
    echo "Supercollider config"
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/jackdrc ]
    then
        echo "updating /etc/jackdrc"
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/jackdrc > /etc/jackdrc"
    fi
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/startup.scd ]
    then
        echo "updating startup.scd"
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/startup.scd > /root/.config/SuperCollider/startup.scd"
    fi

    DIR1="/home/alarm/QB_Nebulae_V2/SuperColliderExtensions"
    DIR2="/usr/share/SuperCollider/Extensions"

    if [ -d "$DIR1" ]; then
        echo "Updating SuperCollider Extensions"
        mkdir -p "$DIR2"
        # Remove and replace
        for item in "$DIR1"/*; do
            rm -rf "$DIR2/$(basename "$item")"
        done
        mv "$DIR1"/* "$DIR2"/
        rm -rf "$DIR1"
    fi

    #mkdir dir if they dont exist
    mkdir -p /home/alarm/sc
    mkdir -p /home/alarm/prog
    # No instrument in any bank: a copy of the granular looper.
    if ! ls /home/alarm/instr/*.instr /home/alarm/sc/*.scd /home/alarm/pd/*.pd /home/alarm/prog/*.prog >/dev/null 2>&1
    then
        mkdir -p /home/alarm/instr
        cp /home/alarm/QB_Nebulae_V2/Code/instr/a_granularlooper.instr /home/alarm/instr/
    fi

    reboot
else
    # Arch packages on the stick, e.g. libgpiod and liblo for nebio.
    FC=`ls /mnt/memory/*.tar.xz /mnt/memory/*.tar.zst 2>/dev/null | wc -l`
    if [ $FC -gt 0 ] 
    then 
        echo "Packages detected"
	pacman --noconfirm -U `ls /mnt/memory/*.tar.xz /mnt/memory/*.tar.zst 2>/dev/null`
        rm -f /mnt/memory/*.tar.xz /mnt/memory/*.tar.zst
    else  
      echo "No Update Detected"
    fi
fi
umount /dev/sda1
sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
echo "Advancing to the rest of the startup script."
