#!/bin/bash

# Exporting LIB path for nebulae
echo export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Everything that needs root in one sudo call: each sudo costs ~30 ms at boot
# (this script took 0.74 s with one sudo per line). "service ntp stop" is gone:
# there is no service command (nor ntp) on the Arch images.
sudo sh -c '
# Probing i2c dev to enable i2c
modprobe i2c-dev

## Stop the console-kit-daemon and polkitd services. Warning: this can cause
## unpredictable behaviour when running a desktop environment on the RPi
killall -q console-kit-daemon polkitd

## Disable Overcommit protection to allow subprocess forking when < half RAM is available.
## This may cause hardfaults if more memory than is available is actually committed.
echo 1 > /proc/sys/vm/overcommit_memory

## Remount /dev/shm to prevent memory allocation errors. 512M: on the 64-bit
## image JACK alone takes 107 MB there, and a crashed jackd leaves its copy
## behind (128M then made the next jackd die with SIGBUS).
mount -o remount,size=512M /dev/shm

## Set the CPU scaling governor to performance
for cpu in 0 1 2 3; do
    echo -n performance > /sys/devices/system/cpu/cpu$cpu/cpufreq/scaling_governor
done
'

## Stop the triggerhappy service
##sudo service triggerhappy stop

## Stop the dbus service. Warning: this can cause unpredictable behaviour when running a desktop environment on the RPi
##sudo service dbus stop

## Only needed when Jack2 is compiled with D-Bus support (Jack2 in the AutoStatic RPi audio repo is compiled without D-Bus support)
#export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket

## Kill the usespace gnome virtual filesystem daemon. Warning: this can cause unpredictable behaviour when running a desktop environment on the RPi
killall -q gvfsd

## Kill the userspace D-Bus daemon. Warning: this can cause unpredictable behaviour when running a desktop environment on the RPi
##killall dbus-daemon

## Kill the userspace dbus-launch daemon. Warning: this can cause unpredictable behaviour when running a desktop environment on the RPi
##killall dbus-launch

#disable hdmi
##/opt/vc/bin/tvservice -o
#enable tvservice with:
#/opt/vc/bin/tvservice -p

## Uncomment if you'd like to disable the network adapter completely
#echo -n “1-1.1:1.0” | sudo tee /sys/bus/usb/drivers/smsc95xx/unbind
## In case the above line doesn't work try the following
#echo -n “1-1.1” | sudo tee /sys/bus/usb/drivers/usb/unbind

## And finally start JACK
#jackd -P70 -p16 -t2000 -d alsa -dhw:UA25 -p 128 -n 3 -r 44100 -s &

exit
