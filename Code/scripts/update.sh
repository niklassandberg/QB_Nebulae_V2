#!/bin/bash
sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
sudo mount /dev/sda1 /mnt/memory
if [ -f /mnt/memory/neb_update.zip ]
then
    sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
    python2 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py updating &
    echo "neb_update.zip detected."
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
    sudo python2 /home/alarm/QB_Nebulae_V2/Code/nebulae/check_calibration.py force
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/nebulae.service ]
    then
        echo "updating /etc/systemd/system/nebulae.service for next boot up."
        sudo bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/nebulae.service > /etc/systemd/system/nebulae.service"
        sudo systemctl --system daemon-reload 
    fi
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/sclang.service ]
    then
        echo "updating /etc/systemd/system/sclang.service for next boot up."
        sudo bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/sclang.service > /etc/systemd/system/nsclang.service"
        sudo systemctl --system daemon-reload 
    fi

    sudo reboot
elif [ -d /home/alarm/QB_Nebulae_V2/Code/packages ]
then
    echo "detected firmware pacakges to install" 
    sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
    python2 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py updating &

    echo "install web services"
    sudo cp /home/alarm/QB_Nebulae_V2/Code/web/NebFile/NebFile.service /etc/systemd/system
    sudo systemctl --system daemon-reload 

    cd /home/alarm/QB_Nebulae_V2/Code/packages

    sudo pacman --noconfirm -U *.tar.xz
    echo "installed packages"

    echo "install pip2"
    cd python
    sudo python2 pip-20.0.2-py2.py3-none-any.whl/pip install --no-index pip-20.0.2-py2.py3-none-any.whl 

    echo "installed pip packages"
    sudo pip2 install *
    cd /home/alarm

    rm -rf /home/alarm/QB_Nebulae_V2/Code/packages

    echo "Supercollider config"
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/jackdrc ]
    then
        echo "updating /etc/jackdrc"
        sudo bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/jackdrc > /etc/jackdrc"
    fi
    if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/startup.scd ]
    then
        echo "updating startup.scd"
        sudo bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/startup.scd > /root/.config/SuperCollider/startup.scd"
    fi

    DIR1="/home/alarm/QB_Nebulae_V2/SuperColliderExtensions"
    DIR2="/usr/share/SuperCollider/Extensions"

    if [ -d "$DIR1" ]; then
        echo "Updating SuperCollider Extensions"

        mkdir -p "$DIR2"

        # Create directory structure
        find "$DIR1" -type d -mindepth 1 | while read -r d; do
            mkdir -p "$DIR2/${d#$DIR1/}"
        done

        # Move files
        find "$DIR1" -type f | while read -r f; do
            mv "$f" "$DIR2/${f#$DIR1/}"
        done

        # Remove empty directories
        find "$DIR1" -type d -empty -delete
    fi

    #mkdir dir if they dont exist
    mkdir -p /home/alarm/sc

    sudo reboot
else
    FC=`ls -l /mnt/memory/*.tar.xz | wc -l` 
    if [ $FC -gt 0 ] 
    then 
        echo "Packages detected"
	sudo pacman --noconfirm -U /mnt/memory/*.tar.xz
        rm /mnt/memory/*.tar.xz
    else  
      echo "No Update Detected"
    fi
fi
sudo umount /dev/sda1
sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
echo "Advancing to the rest of the startup script."
