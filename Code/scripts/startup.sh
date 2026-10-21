#!/bin/bash

#disable network by default so wpa_suppliant does not make any sounds.
sudo rfkill block wifi

#sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw

echo "enable i2c"
sudo modprobe i2c-dev
echo "starting bootup LEDs"
python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py booting &

# nebio (C++ hardware/OSC library) must exist before any Python script that
# reads buttons or knobs (check_wifi.py, check_calibration.py, nebulae.py).
echo "building nebio (only if changed)"
if ! sh /home/alarm/QB_Nebulae_V2/Code/scripts/build_nebio.sh check
then
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/build_nebio.sh
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
fi

echo "optimizing system."
sh /home/alarm/QB_Nebulae_V2/Code/scripts/sys_opt_lite.sh
# Wi-Fi is not started at boot any more (was check_wifi.py: hold the speed
# click). It is switched on/off on the scripts page of the instr selector
# (Code/nebscripts/1_wifi.sh); neb_globals.wifi_always_on is read by nebulae.py.
# Quiet mode (scripts page, 3_quiet.ui -> scripts/quiet.sh) is a saved setting: applied here
# (its slow part runs in the background). USB stays on for the firmware
# update check below; the file loader switches it off after its first load.
bash /home/alarm/QB_Nebulae_V2/Code/scripts/quiet.sh apply

echo "checking for firmware update"
sh /home/alarm/QB_Nebulae_V2/Code/scripts/update.sh

#echo "checking for reversion file"
#if [ -f /mnt/memory/revert_to_factory_firmware ]
#then
#    sh /home/alarm/revertfactoryfw.sh
#fi
# Update Local Files - Config.txt (nebulae.service handled in update.)
# Only write when changed: /boot is FAT, and a write left it marked dirty
# ("Volume was not properly unmounted") when the power is cut.
if [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt ] && ! cmp -s /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt /boot/config.txt
then
    echo "updating /boot/config.txt for next boot up."
    sudo bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt > /boot/config.txt"
fi
#sh /home/alarm/QB_Nebulae_V2/Code/scripts/handleuserfiles.sh


# Configure Audio Codec
sh /home/alarm/QB_Nebulae_V2/Code/scripts/enable_inputs.sh

if ! cmp -s /home/alarm/QB_Nebulae_V2/Code/localfiles/environment /etc/environment
then
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
    sudo bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/environment > /etc/environment"
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
fi

# Hardware test firmware (create_fw_update.sh --hwtest): run the nebio
# hardware test instead of nebulae. The log goes to the USB stick
# (hwtest_log.txt), or /tmp when no stick is in. Ends with exit 0 so
# nebulae.service (Restart=on-failure) does not restart startup.sh.
if [ -f /home/alarm/QB_Nebulae_V2/Code/hwtest_mode ]
then
    echo "hardware test mode"
    HWLOG=/tmp/hwtest_log.txt
    if sudo mount /dev/sda1 /mnt/memory
    then
        HWLOG=/mnt/memory/hwtest_log.txt
    fi
    # Build again: update.sh may just have installed libgpiod/liblo from the stick.
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/build_nebio.sh > /tmp/nebio_build.log 2>&1
    BUILD=$?
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
    sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
    if [ $BUILD -ne 0 ]
    then
        echo "hardware test: nebio build failed"
        sudo bash -c "{ echo '==== nebio build FAILED' \$(date); pkg-config --modversion libgpiod liblo; cat /tmp/nebio_build.log; } >> $HWLOG 2>&1"
        python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py error &
    else
        sudo python3 /home/alarm/QB_Nebulae_V2/Code/nebio/tools/hwtest.py --headless --log $HWLOG
    fi
    sync
    exit 0
fi

#sudo systemctl start sclang.service

sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
sudo python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/check_calibration.py
sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro

sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py

echo "Running Nebulae"

#dont do this, you cannot run sudo systemctl stop nebulae.service then.
#just run: journalctl -u nebulae.service -f for full history, add -n 100 for instance to see last 100 lines
#sudo python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/nebulae.py &> /tmp/nebulae_stdout.log

sudo python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/nebulae.py
