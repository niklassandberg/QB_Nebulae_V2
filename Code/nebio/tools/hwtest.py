#!/usr/bin/env python3
# hwtest.py
# Hardware test for nebio without nebulae running.
#
# Plays the audio files nebulae uses (/home/alarm/audio, .wav only since
# aplay cannot play .aif/.flac) in a loop on the I2S soundcard while all inputs are shown
# live: 16 analog values, shift register bits, gates, encoder clicks and
# encoders. Knobs and buttons drive the LEDs so everything can be checked by
# hand. Audio underruns, nebio scan rate, CPU load and temperature are shown at
# the bottom; if the audio breaks up while inputs are used, nebio disturbs it.
#
#   sudo systemctl stop nebulae
#   sudo python3 Code/nebio/tools/hwtest.py [--file x.wav] [--device plughw:sndrpiproto] [--no-audio]
#
# q quits (LEDs off, audio stopped).
#
# --headless runs without a screen and writes a log instead. startup.sh runs it
# that way instead of nebulae when Code/hwtest_mode exists (made by
# create_fw_update.sh --hwtest).

import argparse
import curses
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "Code", "nebulae"))

import nebio  # noqa: E402
import nebmixer  # noqa: E402

AUDIO_DIR = "/home/alarm/audio/"  # conductor.py
DEFAULT_DEVICE = "plughw:sndrpiproto"

# Channel names as used in controlhandler.py (pot channel / cv channel).
POT_NAMES = {0: "start", 1: "blend", 2: "density", 5: "window", 6: "size", 7: "overlap"}
CV_NAMES = {0: "start", 1: "speed", 2: "density", 3: "blend", 4: "pitch", 5: "window",
            6: "size", 7: "overlap"}

# Shift register bits (shiftregister.py) and the LED each one lights.
SR_BITS = [(0, "reset", "reset"), (3, "record", "record"), (4, "freeze", "freeze"),
           (5, "source", "source"), (6, "source gate", "source"), (7, "next", "next"),
           (1, "bit 1 (unused)", None), (2, "bit 2 (unused)", None)]
# GPIO inputs (controlhandler.py, ui.py) and the LED each one lights.
GPIO_INPUTS = [(4, "freeze gate", "freeze"), (25, "reset gate", "reset"),
               (23, "next gate", "next"), (24, "record gate", "record"),
               (22, "pitch click", None), (26, "speed click", None)]
ENCODERS = [("pitch", 17, 27), ("speed", 6, 13)]


def audio_files(directory):
    """The .wav files nebulae would load from its audio folder, in name order."""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return [os.path.join(directory, n) for n in sorted(names, key=str.lower)
            if n.lower().endswith(".wav") and not n.startswith(".")]


class Audio(object):
    """Plays the files one after another in a loop with aplay and counts
    underruns from its stderr."""

    def __init__(self, paths, device):
        self.paths = paths
        self.path = paths[0]
        self.device = device
        self.proc = None
        self.stop = False
        self.underruns = 0
        self.loops = 0
        self.status = "starting"
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True

    def start(self):
        self.thread.start()

    def run(self):
        index = 0
        while not self.stop:
            self.path = self.paths[index % len(self.paths)]
            index += 1
            try:
                self.proc = subprocess.Popen(["aplay", "-D", self.device, self.path],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                             universal_newlines=True)
            except OSError as e:
                self.status = "aplay failed: %s" % e
                return
            self.status = "playing"
            for line in self.proc.stderr:
                line = line.strip()
                if "underrun" in line:
                    self.underruns += 1
                elif line and not line.startswith("Playing"):
                    self.status = line[:70]
            rc = self.proc.wait()
            if self.stop:
                break
            if rc != 0:
                self.status = "aplay exit %d: %s" % (rc, self.status)
                time.sleep(1.0)
            else:
                self.loops += 1

    def close(self):
        self.stop = True
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()


class CpuMeter(object):
    """CPU use of this process (nebio threads included) and of the whole Pi."""

    def __init__(self):
        self.tick = float(os.sysconf("SC_CLK_TCK"))
        self.last = self.sample()
        self.proc_pct = 0.0
        self.sys_pct = 0.0

    @staticmethod
    def sample():
        with open("/proc/self/stat") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        proc = int(fields[11]) + int(fields[12])  # utime + stime
        with open("/proc/stat") as f:
            cpu = [int(x) for x in f.readline().split()[1:]]
        idle = cpu[3] + cpu[4]
        return time.time(), proc, sum(cpu), idle

    def update(self):
        now = self.sample()
        t0, p0, tot0, idle0 = self.last
        t1, p1, tot1, idle1 = now
        if t1 - t0 < 0.5:
            return
        self.proc_pct = 100.0 * (p1 - p0) / self.tick / (t1 - t0)
        if tot1 > tot0:
            self.sys_pct = 100.0 * (1.0 - float(idle1 - idle0) / (tot1 - tot0))
        self.last = now


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except (IOError, OSError):
        return None


def temperature():
    t = read_text("/sys/class/thermal/thermal_zone0/temp")
    return "%.1f C" % (int(t) / 1000.0) if t else "n/a"


def throttled():
    t = read_text("/sys/devices/platform/soc/soc:firmware/get_throttled")
    return t if t is not None else "n/a"


def bar(value, width=20):
    filled = int(round(max(0.0, min(1.0, value)) * width))
    return "#" * filled + "-" * (width - filled)


def put(scr, row, text, attr=0):
    """addstr that ignores lines outside a small terminal."""
    h, w = scr.getmaxyx()
    if row < h - 1:
        try:
            scr.addstr(row, 0, text[:w - 1], attr)
        except curses.error:
            pass


def run(scr, args):
    curses.curs_set(0)
    scr.nodelay(True)

    nebio.inputs()
    if nebio.lib().nebio_snapshot() < 0:
        raise RuntimeError("nebio inputs init failed: %s" % nebio.last_error())
    led = nebio.LedDriver()

    audio = None
    if not args.no_audio:
        nebmixer.init()
        nebmixer.enable()
        audio = Audio(args.files, args.device)
        audio.start()

    cpu = CpuMeter()
    enc_ids = [(name, nebio.encoder_id(a, b)) for name, a, b in ENCODERS]
    enc_pos = dict((name, 0) for name, _ in enc_ids)

    nebio.snapshot()
    sr_rest = nebio.sr_bits()
    gpio_rest = dict((pin, nebio.lib().nebio_gpio_level(pin)) for pin, _, _ in GPIO_INPUTS)

    try:
        while True:
            key = scr.getch()
            if key in (ord("q"), ord("Q")):
                break

            nebio.snapshot()
            cpu.update()
            sr = nebio.sr_bits()
            pots = [nebio.adc_code(nebio.ADC_POT, ch) for ch in range(8)]
            cvs = [nebio.adc_code(nebio.ADC_CV, ch) for ch in range(8)]
            for name, eid in enc_ids:
                if eid >= 0:
                    enc_pos[name] += nebio.encoder_steps(eid)

            lit = set()
            scr.erase()
            row = 0
            put(scr, row, "nebio hardware test   q = quit", curses.A_BOLD)
            row += 2
            put(scr, row, "ch  knob (spidev0.1)                     CV (spidev0.0)")
            row += 1
            for ch in range(8):
                p, c = pots[ch], cvs[ch]
                cv_volts = ((4095.0 - c) - 2047.0) / 2047.0  # control.py convertRawCV
                put(scr, row, "%d  %4d %s %-8s   %4d %+.3f %-8s" % (
                    ch, p, bar(p / 4095.0), POT_NAMES.get(ch, "(unused)"),
                    c, cv_volts, CV_NAMES.get(ch, "")))
                row += 1

            row += 1
            put(scr, row, "Shift register (raw 0x%02x, at start 0x%02x)" % (sr, sr_rest))
            row += 1
            for bit, name, led_name in SR_BITS:
                level = (sr >> bit) & 1
                changed = level != ((sr_rest >> bit) & 1)
                if changed and led_name:
                    lit.add(led_name)
                put(scr, row, "  bit %d %-15s %d %s" % (bit, name, level, "<<" if changed else ""))
                row += 1

            row += 1
            put(scr, row, "GPIO inputs")
            row += 1
            for pin, name, led_name in GPIO_INPUTS:
                level = nebio.lib().nebio_gpio_level(pin)
                changed = level != gpio_rest[pin]
                if changed and led_name:
                    lit.add(led_name)
                put(scr, row, "  GPIO %2d %-12s %d %s" % (pin, name, level, "<<" if changed else ""))
                row += 1

            row += 1
            put(scr, row, "Encoders   pitch %+5d   speed %+5d" % (enc_pos["pitch"], enc_pos["speed"]))
            row += 2

            # LEDs: knobs 0-2 colour pitch+, knobs 5-7 colour speed+,
            # encoders set the brightness of pitch-/speed-, buttons/gates light their LED.
            led.set_rgb("pitch_pos", pots[0], pots[1], pots[2], 1.0)
            led.set_rgb("speed_pos", pots[5], pots[6], pots[7], 1.0)
            led.set_rgb("pitch_neg", 4095, 4095, 4095, (enc_pos["pitch"] % 21) / 20.0)
            led.set_rgb("speed_neg", 4095, 4095, 4095, (enc_pos["speed"] % 21) / 20.0)
            for name in nebio.BUTTON_LEDS:
                led.set_button_led(name, 1.0 if name in lit else 0.0)
            led.update()

            if audio is not None:
                put(scr, row, "Audio  %s  (%s, %d file(s))" % (
                    audio.status, os.path.basename(audio.path), len(audio.paths)))
                row += 1
                put(scr, row, "       files played %d   underruns %d" % (audio.loops, audio.underruns),
                           curses.A_BOLD if audio.underruns else 0)
                row += 1
            put(scr, row, "nebio  %s" % nebio.stats())
            row += 1
            put(scr, row, "CPU    this process %.1f %% of one core, whole Pi %.1f %%" % (
                cpu.proc_pct, cpu.sys_pct))
            row += 1
            put(scr, row, "Temp   %s   throttled %s" % (temperature(), throttled()))
            scr.refresh()
            time.sleep(0.05)
    finally:
        if audio is not None:
            audio.close()
        for name in nebio.BUTTON_LEDS:
            led.set_button_led(name, 0.0)
        for name in nebio.RGB_LEDS:
            led.set_rgb(name, 0, 0, 0, 0.0)
        led.update()
        time.sleep(0.1)  # let the LED thread write the last values
        nebio.shutdown()


class Log(object):
    """Writes to stdout (journalctl) and to a file that is synced after every
    write, so the file on the USB stick is complete even after power off."""

    def __init__(self, path):
        self.start = time.time()
        self.f = None
        if path:
            try:
                self.f = open(path, "a")
            except (IOError, OSError) as e:
                print("hwtest: cannot open log %s: %s" % (path, e))

    def __call__(self, text):
        line = "%7.1f s  %s" % (time.time() - self.start, text)
        print(line)
        sys.stdout.flush()
        if self.f is not None:
            self.f.write(line + "\n")
            self.f.flush()
            os.fsync(self.f.fileno())


def headless(args):
    """The same test without a screen, for running at boot (startup.sh).
    LEDs follow knobs, encoders and buttons like in the screen version; the
    log records every button/gate/encoder change, how far each analog input
    has moved, and every 10 s the audio, nebio, CPU and temperature status.
    Runs until it is stopped (SIGTERM) or the Nebulae is switched off."""
    import signal

    def on_term(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, on_term)

    log = Log(args.log)
    log("==== nebio hardware test %s ====" % time.strftime("%Y-%m-%d %H:%M:%S"))
    nebio.inputs()
    if nebio.lib().nebio_snapshot() < 0:
        log("ERROR nebio inputs init failed: %s" % nebio.last_error())
        return 1
    led = nebio.LedDriver()
    log("nebio inputs and LEDs started")

    audio = None
    if args.no_audio:
        log("audio off (--no-audio)")
    elif not args.files:
        log("WARNING no .wav files in %s, testing without audio" % AUDIO_DIR)
    else:
        nebmixer.init()
        nebmixer.enable()
        audio = Audio(args.files, args.device)
        audio.start()
        log("audio: %d file(s) on %s" % (len(args.files), args.device))

    cpu = CpuMeter()
    enc_ids = [(name, nebio.encoder_id(a, b)) for name, a, b in ENCODERS]
    enc_pos = dict((name, 0) for name, _ in enc_ids)
    nebio.snapshot()
    sr_rest = nebio.sr_bits()
    gpio_rest = dict((pin, nebio.lib().nebio_gpio_level(pin)) for pin, _, _ in GPIO_INPUTS)
    prev_sr = sr_rest
    prev_gpio = dict(gpio_rest)
    lo = {}
    hi = {}
    reported_moved = set()
    log("at rest: shift register 0x%02x, GPIO %s" % (
        sr_rest, " ".join("%d=%d" % (p, l) for p, l in sorted(gpio_rest.items()))))
    log("now: turn every knob, patch every CV input, press every button, send gates, "
        "turn and click both encoders")

    next_status = time.time() + 10.0
    last_enc_log = dict(enc_pos)
    try:
        while True:
            nebio.snapshot()
            cpu.update()
            sr = nebio.sr_bits()
            codes = {}
            for dev, label in ((nebio.ADC_POT, "knob"), (nebio.ADC_CV, "CV")):
                for ch in range(8):
                    codes[(label, ch)] = nebio.adc_code(dev, ch)
            for key, c in codes.items():
                lo[key] = min(lo.get(key, c), c)
                hi[key] = max(hi.get(key, c), c)
                if key not in reported_moved and hi[key] - lo[key] > 400:
                    reported_moved.add(key)
                    names = POT_NAMES if key[0] == "knob" else CV_NAMES
                    log("moved: %s %d %s (range %d..%d)" % (
                        key[0], key[1], names.get(key[1], "(unused)"), lo[key], hi[key]))

            lit = set()
            for bit, name, led_name in SR_BITS:
                level = (sr >> bit) & 1
                if level != (prev_sr >> bit) & 1:
                    log("shift register bit %d %s -> %d" % (bit, name, level))
                if led_name and level != (sr_rest >> bit) & 1:
                    lit.add(led_name)
            prev_sr = sr
            for pin, name, led_name in GPIO_INPUTS:
                level = nebio.lib().nebio_gpio_level(pin)
                if level != prev_gpio[pin]:
                    log("GPIO %d %s -> %d" % (pin, name, level))
                    prev_gpio[pin] = level
                if led_name and level != gpio_rest[pin]:
                    lit.add(led_name)
            for name, eid in enc_ids:
                if eid >= 0:
                    enc_pos[name] += nebio.encoder_steps(eid)

            led.set_rgb("pitch_pos", codes[("knob", 0)], codes[("knob", 1)], codes[("knob", 2)], 1.0)
            led.set_rgb("speed_pos", codes[("knob", 5)], codes[("knob", 6)], codes[("knob", 7)], 1.0)
            led.set_rgb("pitch_neg", 4095, 4095, 4095, (enc_pos["pitch"] % 21) / 20.0)
            led.set_rgb("speed_neg", 4095, 4095, 4095, (enc_pos["speed"] % 21) / 20.0)
            for name in nebio.BUTTON_LEDS:
                led.set_button_led(name, 1.0 if name in lit else 0.0)
            led.update()

            now = time.time()
            if now >= next_status:
                next_status = now + 10.0
                if enc_pos != last_enc_log:
                    log("encoders: pitch %+d  speed %+d" % (enc_pos["pitch"], enc_pos["speed"]))
                    last_enc_log = dict(enc_pos)
                if audio is not None:
                    log("audio: %s, %s, files played %d, underruns %d" % (
                        audio.status, os.path.basename(audio.path), audio.loops, audio.underruns))
                log("nebio: %s | CPU this process %.1f %%, whole Pi %.1f %% | temp %s, throttled %s" % (
                    nebio.stats(), cpu.proc_pct, cpu.sys_pct, temperature(), throttled()))
                not_moved = sorted(k for k in codes if k not in reported_moved
                                   and not (k[0] == "knob" and k[1] not in POT_NAMES))
                if not_moved:
                    log("not moved yet: %s" % ", ".join("%s %d" % k for k in not_moved))
            time.sleep(0.02)
    finally:
        log("stopping")
        if audio is not None:
            audio.close()
        for name in nebio.BUTTON_LEDS:
            led.set_button_led(name, 0.0)
        for name in nebio.RGB_LEDS:
            led.set_rgb(name, 0, 0, 0, 0.0)
        led.update()
        time.sleep(0.1)
        nebio.shutdown()
    return 0


def main():
    ap = argparse.ArgumentParser(description="nebio hardware test (stop nebulae first)")
    ap.add_argument("--file", help="play only this file (default: all .wav in %s)" % AUDIO_DIR)
    ap.add_argument("--device", default=DEFAULT_DEVICE, help="ALSA device for aplay")
    ap.add_argument("--no-audio", action="store_true", help="only test inputs and LEDs")
    ap.add_argument("--headless", action="store_true",
                    help="no screen: log to stdout and --log (used by startup.sh)")
    ap.add_argument("--log", help="log file for --headless, e.g. /mnt/memory/hwtest_log.txt")
    args = ap.parse_args()
    args.files = []
    if not args.no_audio:
        args.files = [args.file] if args.file else audio_files(AUDIO_DIR)
        if not args.files and not args.headless:
            sys.exit("no .wav files in %s (use --file or --no-audio)" % AUDIO_DIR)
        missing = [f for f in args.files if not os.path.isfile(f)]
        if missing:
            sys.exit("audio file not found: %s" % missing[0])
    if subprocess.call(["pgrep", "-f", "nebulae.py"], stdout=subprocess.DEVNULL) == 0:
        sys.exit("nebulae.py is running, stop it first: sudo systemctl stop nebulae")
    if args.headless:
        sys.exit(headless(args))
    curses.wrapper(run, args)


if __name__ == "__main__":
    main()
