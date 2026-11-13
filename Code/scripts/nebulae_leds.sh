#!/bin/sh
# The LEDs after Nebulae: nebulae.service's ExecStopPost and fatal.py. The
# PCA9685 keeps its registers. Active low: full ON in ALL_LED_ON_H with full
# OFF cleared in ALL_LED_OFF_H is dark; a channel's full OFF bit wins and
# lights it.
# Dark, or red after a fatal stop (/run/nebulae-fatal, cleared at boot and by
# the next start).
i2cset -y 1 0x40 0xFB 0x10
i2cset -y 1 0x40 0xFD 0x00
[ -e /run/nebulae-fatal ] || exit 0
# LEDn_OFF_H = 0x09 + 4n of the red channels 8, 13, 4 and 7 (nebio leds.cpp)
for reg in 0x29 0x3D 0x19 0x25; do
    i2cset -y 1 0x40 $reg 0x10
done
