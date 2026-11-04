#!/bin/bash
# Needs root.
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"

#disable network by default.
rfkill block wifi

#sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw

echo "enable i2c"
modprobe i2c-dev
echo "starting bootup LEDs"
python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py booting &

bash /home/alarm/QB_Nebulae_V2/Code/scripts/eeprom_update.sh

# Before any Python script that reads buttons or knobs.
echo "building nebio (only if changed)"
if ! sh /home/alarm/QB_Nebulae_V2/Code/scripts/build_nebio.sh check
then
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/build_nebio.sh
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
fi

echo "optimizing system."
sh /home/alarm/QB_Nebulae_V2/Code/scripts/sys_opt_lite.sh

echo "checking for firmware update"
sh /home/alarm/QB_Nebulae_V2/Code/scripts/update.sh

#echo "checking for reversion file"
#if [ -f /mnt/memory/revert_to_factory_firmware ]
#then
#    sh /home/alarm/revertfactoryfw.sh
#fi
# config.txt for the next boot, only when changed (/boot is FAT). /boot is
# automounted ~1.5 s later: never write into the empty mount point.
(
    for i in $(seq 200); do mountpoint -q /boot && [ -f /boot/cmdline.txt ] && break; sleep 0.1; done
    if [ -f /boot/cmdline.txt ] && [ -f /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt ] && ! cmp -s /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt /boot/config.txt
    then
        echo "updating /boot/config.txt for next boot up."
        bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt > /boot/config.txt"
    fi
) &


# Codec inputs, after the card and alsa-restore are there.
(
    for i in $(seq 100); do [ -e /proc/asound/sndrpiproto ] && break; sleep 0.1; done
    for i in $(seq 50); do systemctl is-active --quiet alsa-restore.service && break; sleep 0.1; done
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/enable_inputs.sh
) &

# jackd early for the boot instrument (jack line in bootinstr.txt), unless
# one runs already (nebulae.service restarted).
JACK_EARLY=$(sed -n 's/^jack,\([0-9]*-[0-9]*-[0-9]*\)$/\1/p' /home/alarm/QB_Nebulae_V2/Code/config/bootinstr.txt 2>/dev/null)
if [ -n "$JACK_EARLY" ] && ! pgrep -x jackd > /dev/null
then
    (
        for i in $(seq 100); do [ -e /proc/asound/sndrpiproto ] && break; sleep 0.1; done
        echo "starting jack@$JACK_EARLY early (boot instrument)"
        systemctl start "jack@$JACK_EARLY.service"
    ) &
fi

if ! cmp -s /home/alarm/QB_Nebulae_V2/Code/localfiles/environment /etc/environment
then
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw
    bash -c "cat /home/alarm/QB_Nebulae_V2/Code/localfiles/environment > /etc/environment"
    sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro
fi
export HOME=/root
set -a; . /etc/environment; set +a

# Hardware test firmware (create_fw_update.sh --hwtest). exit 0: no restart.
if [ -f /home/alarm/QB_Nebulae_V2/Code/hwtest_mode ]
then
    echo "hardware test mode"
    HWLOG=/tmp/hwtest_log.txt
    if mount /dev/sda1 /mnt/memory
    then
        HWLOG=/mnt/memory/hwtest_log.txt
    fi
    # update.sh may just have installed libgpiod/liblo.
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

# Pitch encoder held at boot (GPIO22 = 0): calibration. Read here, as
# starting Python only for it takes ~1.2 s.
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
