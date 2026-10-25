#!/bin/bash
# Needs root. The services start it as root; started by hand it runs
# itself again with sudo (sudo as root only adds lines to the journal).
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"
mount /dev/sda1 /mnt/memory
# Bootloader (EEPROM) update, only when a file "update_bootloader" is on the
# stick: removed first (once only), then eeprom_update.sh flashes and reboots,
# or logs to neb_log.txt why not (already up to date, 32-bit image).
if [ -f /mnt/memory/update_bootloader ]
then
    rm -f /mnt/memory/update_bootloader
    sync
    bash /home/alarm/QB_Nebulae_V2/Code/scripts/eeprom_update.sh flash
fi
# Nothing to install (no update zip, no packages on the stick or left in
# Code/packages): done without remounting / read-write and back (~0.3 s at boot).
if [ ! -f /mnt/memory/neb_update.zip ] && [ ! -d /home/alarm/QB_Nebulae_V2/Code/packages ] \
    && ! ls /mnt/memory/*.tar.xz /mnt/memory/*.tar.zst >/dev/null 2>&1
then
    echo "No Update Detected"
    umount /dev/sda1
    echo "Advancing to the rest of the startup script."
    exit 0
fi
sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
if [ -f /mnt/memory/neb_update.zip ]
then
    pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
    python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py updating &
    echo "neb_update.zip detected."
    # The engines report of an earlier update or build is stale now; this
    # update writes a new one only when a recipe has no package.
    rm -f /mnt/memory/neb_engines_report.txt /mnt/memory/neb_engines_build.log.gz
    echo "Commencing Firmware Update Procedure"
    echo "Creating Backup Directories"
    mkdir -p /home/alarm/backup/new
    mkdir -p /home/alarm/backup/old
    echo "Making sure New Backup Directory is Empty"
    rm -rf /home/alarm/backup/new/*
    echo "Copying neb_update.zip to Backup Directory"
    cp -R /mnt/memory/neb_update.zip /home/alarm/backup/new
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
    echo "$now - Firmware updated to: $VERSION" >> /mnt/memory/neb_log.txt
    rm -rf /mnt/memory/neb_update.zip
    # The new firmware has no nebio build yet, and check_calibration.py reads
    # the knobs through nebio, so build it first (file system is still rw).
    echo "building nebio for the new firmware"
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/build_nebio.sh
    # Audio engines: the firmware's Code/engines/ and the stick's engines/
    # are merged into /home/alarm/engines/ (kept across updates, so what was
    # built here stays), other versions installed. Nothing is built: what has
    # no package is reported on the stick (build it: engines_build.sh).
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
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/jack.service ]
    then
        echo "updating /etc/systemd/system/jack.service for next boot up."
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/jack.service > /etc/systemd/system/jack.service"
        systemctl --system daemon-reload
        systemctl disable jack.service
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

    # Only packages built for this Pi's architecture: Code/packages holds old
    # armv7h packages (and Python 2 wheels), which the aarch64 image must skip.
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

    reboot
else
    # Arch packages on the stick (.tar.xz, or .tar.zst which newer packages use),
    # e.g. libgpiod and liblo for nebio.
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
