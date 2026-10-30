#!/usr/bin/env python3
# ledwalk.py
# Lights every LED on its own, one after another, so dead LEDs or swapped
# colours can be seen by eye. Button LEDs first, then each RGB LED red, green,
# blue, and at the end everything white. Each step is printed with a timestamp.
#
#   sudo systemctl stop nebulae
#   sudo python3 Code/nebio/tools/ledwalk.py [--step 3.0]

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "nebulae")))

import nebio  # noqa: E402

COLORS = [("red", (4095, 0, 0)), ("green", (0, 4095, 0)), ("blue", (0, 0, 4095))]


def all_off(led):
    for name in nebio.BUTTON_LEDS:
        led.set_button_led(name, 0.0)
    for name in nebio.RGB_LEDS:
        led.set_rgb(name, 0, 0, 0, 0.0)


def show(led, text, seconds, setup):
    all_off(led)
    setup()
    led.update()
    print("%s  %s" % (time.strftime("%H:%M:%S"), text), flush=True)
    time.sleep(seconds)


def main():
    parser = argparse.ArgumentParser(description="Light every LED one at a time.")
    parser.add_argument("--step", type=float, default=3.0, help="seconds per LED (default 3)")
    args = parser.parse_args()

    led = nebio.LedDriver()
    try:
        show(led, "all off", 2.0, lambda: None)
        for name in ("record", "next", "source", "freeze", "reset"):
            show(led, "button LED %s" % name, args.step,
                 lambda n=name: led.set_button_led(n, 1.0))
        for name in ("pitch_pos", "pitch_neg", "speed_pos", "speed_neg"):
            for cname, (r, g, b) in COLORS:
                show(led, "%s %s" % (name, cname), args.step,
                     lambda n=name, r=r, g=g, b=b: led.set_rgb(n, r, g, b, 1.0))

        def everything():
            for name in nebio.BUTTON_LEDS:
                led.set_button_led(name, 1.0)
            for name in nebio.RGB_LEDS:
                led.set_rgb(name, 4095, 4095, 4095, 1.0)
        show(led, "all LEDs on, white", 5.0, everything)
    finally:
        all_off(led)
        led.update()
        time.sleep(0.2)
        print("%s  done, all off" % time.strftime("%H:%M:%S"), flush=True)


if __name__ == "__main__":
    main()
