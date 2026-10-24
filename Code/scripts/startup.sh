#!/bin/bash
# Needs root. The services start it as root; started by hand it runs
# itself again with sudo (sudo as root only adds lines to the journal).
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"

#disable network by default so wpa_suppliant does not make any sounds.
rfkill block wifi

#sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw

echo "enable i2c"
modprobe i2c-dev
echo "starting bootup LEDs"
python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py booting &

# After a bootloader (EEPROM) update (update_bootloader on the stick, see
# update.sh): remove its files from /boot again. Otherwise nothing, a few ms.
bash /home/alarm/QB_Nebulae_V2/Code/scripts/eeprom_update.sh

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
# (Code/nebscripts/1_wifi.sh).
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
# nebulae.service starts before /boot is mounted (an automount on the aarch64
# image, mounted when udev has seen the partition, ~1.5 s later). config.txt
# is for the next boot, so this runs in the background: wait for /boot, at most
# 20 s, and never write into the empty /boot directory of the root file system.
(
    for i in $(seq 200); do mountpoint -q /boot && [ -f /boot/cmdline.txt ] && break; sleep 0.1; done
    if [ -f /boot/cmdline.txt ] && [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt ] && ! cmp -s /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt /boot/config.txt
    then
        echo "updating /boot/config.txt for next boot up."
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt > /boot/config.txt"
    fi
) &
#sh /home/alarm/QB_Nebulae_V2/Code/scripts/handleuserfiles.sh


# Configure Audio Codec
# nebulae.service starts before the sound card is there (~5.5-7 s after kernel
# start), and then alsa-restore sets the mixer state saved at shutdown. So in
# the background: wait for the card, then for alsa-restore (at most 15 s in
# all), so these settings come last. Audio is opened later (~8.5 s).
(
    for i in $(seq 100); do [ -e /proc/asound/sndrpiproto ] && break; sleep 0.1; done
    for i in $(seq 50); do systemctl is-active --quiet alsa-restore.service && break; sleep 0.1; done
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/enable_inputs.sh
) &

if ! cmp -s /home/alarm/QB_Nebulae_V2/Code/localfiles/environment /etc/environment
then
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
    bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/environment > /etc/environment"
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
fi
# What "sudo python3 nebulae.py" gave it before: HOME and /etc/environment
# (LD_LIBRARY_PATH, SC_JACK_DEFAULT_*), now for everything started from here.
export HOME=/root
set -a; . /etc/environment; set +a

# Hardware test firmware (create_fw_update.sh --hwtest): run the nebio
# hardware test instead of nebulae. The log goes to the USB stick
# (hwtest_log.txt), or /tmp when no stick is in. Ends with exit 0 so
# nebulae.service (Restart=on-failure) does not restart startup.sh.
if [ -f /home/alarm/QB_Nebulae_V2/Code/hwtest_mode ]
then
    echo "hardware test mode"
    HWLOG=/tmp/hwtest_log.txt
    if mount /dev/sda1 /mnt/memory
    then
        HWLOG=/mnt/memory/hwtest_log.txt
    fi
    # Build again: update.sh may just have installed libgpiod/liblo from the stick.
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/build_nebio.sh > /tmp/nebio_build.log 2>&1
    BUILD=$?
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
    pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py
    if [ $BUILD -ne 0 ]
    then
        echo "hardware test: nebio build failed"
        bash -c "{ echo '==== nebio build FAILED' \$(date); pkg-config --modversion libgpiod liblo; cat /tmp/nebio_build.log; } >> $HWLOG 2>&1"
        python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py error &
    else
        python3 /home/alarm/QB_Nebulae_V2/Code/nebio/tools/hwtest.py --headless --log $HWLOG
    fi
    sync
    exit 0
fi

#sudo systemctl start sclang.service

# Calibration starts when the pitch encoder is held at boot. Its pin (GPIO22,
# pull-up, 0 = held) is read here directly (a few ms) instead of starting
# Python and nebio only to read it (~1.2 s). Anything but a clear 1 (held,
# or no gpioget v2) runs check_calibration.py as before.
if [ "$(gpioget -c gpiochip0 --bias=pull-up --numeric 22 2>/dev/null)" != 1 ]
then
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
    python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/check_calibration.py
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
fi

pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py

echo "Running Nebulae"

#dont do this, you cannot run sudo systemctl stop nebulae.service then.
#just run: journalctl -u nebulae.service -f for full history, add -n 100 for instance to see last 100 lines
#sudo python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/nebulae.py &> /tmp/nebulae_stdout.log

python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/nebulae.py
