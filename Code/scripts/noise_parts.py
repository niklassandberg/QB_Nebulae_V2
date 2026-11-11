#!/usr/bin/env python3
# Noise of each part of the Pi, one at a time: A B A B A recordings from
# noise_test.sh's silence state. Root, detached (the lan part cuts ssh):
#   systemd-run --unit noise-parts python3 noise_parts.py run [PARTS]
#       [--secs 10] [--reps 2] [--gain 23] [--label TEXT]
#   noise_parts.py baseline LABEL          only the A states
#   noise_parts.py boot nohlt|hdmi         the next boot only with that
#   noise_parts.py sequence start|stop     normal, nohlt, hdmi, with reboots
#   noise_parts.py tap on|off              Csound records its input (fout)
#   systemd-run --unit noise-parts --collect python3 noise_parts.py nebulae [PARTS]
#                                          beside a playing granular looper
#   noise_parts.py report [DIR]
#   noise_parts.py compare DIR...
#   noise_parts.py pulses DIR             pulses of a run's recordings again
# Results in /home/alarm/noise_parts/.
import glob
import json
import os
import shutil
import subprocess
import sys
import syslog
import threading
import time
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import noise_measure  # noqa: E402  (record, analyse)

CODE = "/home/alarm/QB_Nebulae_V2/Code"
NOISE_TEST = HERE + "/noise_test.sh"
WIFI = HERE + "/wifi.sh"
# Newer kernels: brcmfmac is held by brcmfmac_cyw, plain -r fails silently.
WIFI_UNLOAD = "modprobe -r brcmfmac_cyw brcmfmac 2>/dev/null || modprobe -r brcmfmac"
SPIN = HERE + "/spin.sh"
RAM_DIR = "/tmp/noise_parts"
KEEP_DIR = "/home/alarm/noise_parts"
SD_TEST_FILE = "/home/alarm/noise_parts_sdtest.bin"
USB_DEV = "0000:01:00.0"
USB_DRV = "/sys/bus/pci/drivers/xhci_hcd"
ACT_LED = "/sys/class/leds/ACT" if os.path.exists("/sys/class/leds/ACT") else "/sys/class/leds/led0"
PWR_LED = "/sys/class/leds/PWR" if os.path.exists("/sys/class/leds/PWR") else "/sys/class/leds/led1"
LAN = "end0" if os.path.exists("/sys/class/net/end0") else "eth0"

TAP = "/tmp/noise_tap.raw"   # Csound's input, raw 32-bit float stereo (fout format 0)
TAP_INSTR = "/home/alarm/instr/a_granularlooper.instr"
TAP_AFTER = "ainl, ainr inch 1, 2"
TAP_LINE = 'fout "%s", 0, ainl, ainr' % TAP
# Not in the instrument folder: fileloader.py would see an extra file.
TAP_BACKUP = "/home/alarm/.noise_parts_instr_backup"
CONFIG = CODE + "/config/configsettings.txt"

OUT = None  # this run's folder in RAM_DIR
opts = {"secs": 10, "reps": 2, "gain": 23, "label": ""}


def log(line):
    line = time.strftime("%H:%M:%S ") + line
    print(line, flush=True)
    if OUT:
        with open(OUT + "/log.txt", "a") as f:
            f.write(line + "\n")


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and r.returncode:
        log("FAILED (%d): %s\n%s" % (r.returncode, cmd, r.stdout))
    return r.stdout.strip()


def write(path, value):
    try:
        with open(path, "w") as f:
            f.write(value)
    except OSError as e:
        log("could not write %s: %s" % (path, e))


def wait(seconds, why):
    log("  settle %d s (%s)" % (seconds, why))
    time.sleep(seconds)


# ---------------------------------------------------------------------------
# Helpers running in the background while a state is measured
# ---------------------------------------------------------------------------

class Background(object):
    """A thread doing something until stop()."""

    def __init__(self, fn):
        self.stop_flag = threading.Event()
        self.t = threading.Thread(target=fn, args=(self.stop_flag,), daemon=True)
        self.t.start()

    def stop(self):
        self.stop_flag.set()
        self.t.join()


def log_lines(stop):
    # Like a busy Nebulae log: 20 lines a second to the journal.
    n = 0
    while not stop.wait(0.05):
        syslog.syslog(syslog.LOG_INFO, "noise_parts log line %d" % n)
        n += 1


def sd_writes(stop):
    # 64 KB to the SD card and fsync, once a second.
    block = os.urandom(65536)
    with open(SD_TEST_FILE, "wb") as f:
        while not stop.wait(1.0):
            f.seek(0)
            f.write(block)
            f.flush()
            os.fsync(f.fileno())


bg = {}


def bg_start(name, fn):
    bg_stop(name)
    bg[name] = Background(fn)


def bg_stop(name):
    if name in bg:
        bg.pop(name).stop()


# LEDs: a helper process holds nebio's LED driver (front panel at half
# brightness) until it is killed; without it the LEDs are static off.
LED_HELPER = r"""
import sys, time
sys.path.insert(0, "/home/alarm/QB_Nebulae_V2/Code/nebulae")
import nebio
stagger, nopwm = sys.argv[1] == "on", sys.argv[2] == "on"
driver = nebio.LedDriver()
nebio.led_set_stagger(stagger)
nebio.led_set_no_pwm(nopwm)
for name in ("speed_pos", "speed_neg", "pitch_pos", "pitch_neg"):
    driver.set_rgb(name, 0, 4095, 0, 0.5)
for name in ("record", "next", "source", "reset", "freeze"):
    driver.set_button_led(name, 0.5)
driver.update()
while True:
    time.sleep(60)
"""
led_proc = None


def leds(state):
    """off | pwm (stagger on) | sync (stagger off) | nopwm (stagger on, file+freeze without PWM)"""
    global led_proc
    if led_proc:
        led_proc.terminate()
        led_proc.wait()
        led_proc = None
    sh("pkill -x gpioset")  # noise_test.sh holds the reset LED pin; nebio needs it
    time.sleep(0.3)
    if state == "off":
        sh("python3 - <<'EOF'\n" + LEDS_STATIC_OFF + "EOF")
        sh("(gpioset -z -c gpiochip0 12=1) 2>/dev/null")
        return
    stagger = "off" if state == "sync" else "on"
    nopwm = "on" if state == "nopwm" else "off"
    led_proc = subprocess.Popen(["python3", "-c", LED_HELPER, stagger, nopwm],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


LEDS_STATIC_OFF = """import fcntl, os
fd = os.open("/dev/i2c-1", os.O_RDWR)
fcntl.ioctl(fd, 0x0703, 0x40)
for reg, val in ((0xFA, 0), (0xFB, 0x10), (0xFC, 0), (0xFD, 0)):
    os.write(fd, bytes([reg, val]))
os.close(fd)
"""


def spin(kind):
    sh("pkill -f 'spin.sh .* noise_parts'")
    if kind != "off":
        subprocess.Popen("chrt --idle 0 bash %s %s %d noise_parts" % (SPIN, kind, os.cpu_count()),
                         shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL)


def pi_leds(on):
    if on:
        write(ACT_LED + "/trigger", "mmc0")
        write(PWR_LED + "/trigger", "default-on")
    else:
        for led in (ACT_LED, PWR_LED):
            write(led + "/trigger", "none")
            write(led + "/brightness", "0")


def usb(on):
    bound = os.path.exists(USB_DRV + "/" + USB_DEV)
    if on and not bound:
        write(USB_DRV + "/bind", USB_DEV)
    elif not on and bound:
        sh("umount /mnt/memory 2>/dev/null")
        write(USB_DRV + "/unbind", USB_DEV)


def wifi_driver(on):
    if on:
        sh("bash %s driver" % WIFI)        # loaded, radio blocked
    else:
        sh("bash %s off; %s" % (WIFI, WIFI_UNLOAD))


def wifi_ap(on):
    if on:
        sh("bash %s on" % WIFI)            # access point (USB off: no home profile)
    else:
        sh("bash %s off; %s" % (WIFI, WIFI_UNLOAD))


def lan(on):
    sh("ip link set %s %s" % (LAN, "up" if on else "down"))


def journal(where):
    # Both states log 20 lines/s; only where the journal keeps them differs.
    bg_start("log", log_lines)
    sh("journalctl --flush" if where == "sd" else "journalctl --relinquish-var")


def journal_end():
    bg_stop("log")
    sh("journalctl --relinquish-var")


def sd_write(on):
    if on:
        bg_start("sd", sd_writes)
    else:
        bg_stop("sd")


def sd_write_end():
    bg_stop("sd")
    try:
        os.remove(SD_TEST_FILE)
    except OSError:
        pass


# name: (A label, set A, B label, set B, settle s after a switch, end, note)
# A is the reference; every part starts and ends in A (= the silence state,
# except the LED comparisons, which need the LEDs on in both).
PARTS = [
    ("pi_leds", "off", lambda: pi_leds(False), "on", lambda: pi_leds(True), 3, None,
     "the Pi board's green (SD access) and red LEDs"),
    ("led_pwm", "off", lambda: leds("off"), "pwm", lambda: leds("pwm"), 3, lambda: leds("off"),
     "front panel LEDs at half brightness (PWM, stagger on) vs static off"),
    ("led_stagger", "sync", lambda: leds("sync"), "stagger", lambda: leds("pwm"), 3, lambda: leds("off"),
     "LEDs at half: all PWM channels switching together vs spread (stagger)"),
    ("led_no_pwm", "pwm", lambda: leds("pwm"), "nopwm", lambda: leds("nopwm"), 3, lambda: leds("off"),
     "LEDs at half: file+freeze LEDs with PWM vs without (Silent PWM LED)"),
    ("spin_yield", "off", lambda: spin("off"), "yield", lambda: spin("yield"), 4, lambda: spin("off"),
     "power regulator yield (CPU never sleeps) vs off"),
    ("spin_shell", "off", lambda: spin("off"), "shell", lambda: spin("shell"), 4, lambda: spin("off"),
     "power regulator shell vs off"),
    ("usb", "off", lambda: usb(False), "on", lambda: usb(True), 8, lambda: usb(False),
     "USB controller (VL805) bound and powered vs unbound; Pi 4 only"),
    ("wifi_driver", "off", lambda: wifi_driver(False), "driver", lambda: wifi_driver(True), 10,
     lambda: wifi_driver(False), "Wi-Fi chip driver loaded, radio blocked vs driver removed"),
    ("wifi_ap", "off", lambda: wifi_ap(False), "ap", lambda: wifi_ap(True), 30,
     lambda: wifi_ap(False), "Wi-Fi access point running (beacons) vs driver removed"),
    ("lan", "down", lambda: lan(False), "up", lambda: lan(True), 8, lambda: lan(True),
     "LAN link up (cable in) vs interface down"),
    ("journal", "ram", lambda: journal("ram"), "sd", lambda: journal("sd"), 6, journal_end,
     "20 log lines/s, journal kept in RAM vs written to the SD card"),
    ("sd_write", "idle", lambda: sd_write(False), "write", lambda: sd_write(True), 3, sd_write_end,
     "64 KB written + fsync to the SD card every second vs nothing"),
]


# ---------------------------------------------------------------------------
# Beside a running Nebulae: every part ends as Nebulae had it
# ---------------------------------------------------------------------------

def trigger(led):
    try:
        text = open(led + "/trigger").read()
        return text[text.index("[") + 1:text.index("]")]
    except (OSError, ValueError):
        return "none"


def config_value(key, default):
    try:
        for line in open(CONFIG):
            k, sep, v = line.strip().partition("=")
            if sep and k == key:
                return v
    except OSError:
        pass
    return default


before = {}


def remember():
    before.update({"act": trigger(ACT_LED), "pwr": trigger(PWR_LED),
                   "usb": os.path.exists(USB_DRV + "/" + USB_DEV),
                   "wifi": config_value("wifi", "off"),
                   "power": config_value("power_regulator", "off"),
                   "quiet": config_value("services_quiet", "off"),
        "no_pwm": config_value("no_pwm", "off"),
        "led_stagger": config_value("led_stagger", "on")})


def back_pi_leds():
    write(ACT_LED + "/trigger", before["act"])
    write(PWR_LED + "/trigger", before["pwr"])
    if before["act"] == "none":
        write(ACT_LED + "/brightness", "0")
    if before["pwr"] == "none":
        write(PWR_LED + "/brightness", "0")


def back_spin():
    spin("off")
    if before["power"] in ("yield", "shell"):
        sh("bash %s/quiet.sh spin %s" % (HERE, before["power"]))


def spin_beside(kind):
    sh("bash %s/quiet.sh spin off" % HERE)   # Nebulae's own spin (power regulator)
    spin(kind)


def back_wifi():
    sh("bash %s driver" % WIFI)
    sh("bash %s %s" % (WIFI, "on" if before["wifi"] == "on" else "off"))


def back_journal():
    bg_stop("log")
    sh("journalctl --relinquish-var" if before["quiet"] == "on" else "journalctl --flush")


def services_quiet(on):
    sh("bash %s/quiet.sh services %s" % (HERE, "on" if on else "off"))


def tap_wait(timeout):
    """Until Csound writes the tap again (after a Nebulae restart)."""
    end = time.time() + timeout
    last = -1
    while time.time() < end:
        size = os.path.getsize(TAP) if os.path.exists(TAP) else -1
        if 0 < last < size:
            return True
        last = size
        time.sleep(2)
    return False


# Nebulae reads no_pwm and led_stagger only when it starts.
def led_setting(key, value):
    if config_value(key, None) != value:
        with open(CONFIG) as f:
            lines = [l for l in f.read().splitlines() if not l.startswith(key + "=")]
        with open(CONFIG + ".new", "w") as f:
            f.write("\n".join(lines + ["%s=%s" % (key, value)]) + "\n")
        os.rename(CONFIG + ".new", CONFIG)
    log("  %s=%s, restarting Nebulae" % (key, value))
    sh("systemctl restart nebulae.service")
    time.sleep(3)
    if not tap_wait(120):
        raise RuntimeError("no tap 2 minutes after the Nebulae restart")


def back_leds():
    for key in ("no_pwm", "led_stagger"):
        if config_value(key, None) != before[key]:
            led_setting(key, before[key])


NEB_PARTS = [
    ("pi_leds", "off", lambda: pi_leds(False), "on", lambda: pi_leds(True), 3, back_pi_leds,
     "the Pi board's green (SD access) and red LEDs"),
    ("spin_yield", "off", lambda: spin_beside("off"), "yield", lambda: spin_beside("yield"), 4, back_spin,
     "power regulator yield (CPU never sleeps) vs off"),
    ("spin_shell", "off", lambda: spin_beside("off"), "shell", lambda: spin_beside("shell"), 4, back_spin,
     "power regulator shell vs off"),
    ("usb", "off", lambda: usb(False), "on", lambda: usb(True), 8, lambda: usb(before["usb"]),
     "USB controller (VL805) bound and powered vs unbound; Pi 4 only"),
    ("wifi_driver", "off", lambda: wifi_driver(False), "driver", lambda: wifi_driver(True), 10, back_wifi,
     "Wi-Fi chip driver loaded, radio blocked vs driver removed"),
    ("wifi_ap", "off", lambda: sh("bash %s off" % WIFI), "ap", lambda: wifi_ap(True), 30, back_wifi,
     "Wi-Fi access point running (beacons) vs Wi-Fi off (driver loaded, radio blocked)"),
    ("lan", "down", lambda: lan(False), "up", lambda: lan(True), 8, lambda: lan(True),
     "LAN link up (cable in) vs interface down"),
    ("journal", "ram", lambda: journal("ram"), "sd", lambda: journal("sd"), 6, back_journal,
     "20 log lines/s, journal kept in RAM vs written to the SD card"),
    ("sd_write", "idle", lambda: sd_write(False), "write", lambda: sd_write(True), 3, sd_write_end,
     "64 KB written + fsync to the SD card every second vs nothing"),
    ("services_quiet", "on", lambda: services_quiet(True), "off", lambda: services_quiet(False), 15,
     lambda: services_quiet(before["quiet"] == "on"),
     "Services no sounds on (Pi LEDs, USB, timers, time sync, netctl-auto off, log in RAM) vs off"),
    ("led_no_pwm", "on", lambda: led_setting("no_pwm", "on"), "off", lambda: led_setting("no_pwm", "off"),
     10, back_leds, "No PWM on vs off (setting + Nebulae restart; LEDs as the instrument shows them)"),
    ("led_stagger", "on", lambda: led_setting("led_stagger", "on"), "off",
     lambda: led_setting("led_stagger", "off"), 10, back_leds,
     "LED stagger on vs off (setting + Nebulae restart; LEDs as the instrument shows them)"),
]


def nebulae_run(names):
    global OUT
    if not os.path.exists(TAP):
        sys.exit("no tap (%s): noise_parts.py tap on first" % TAP)
    opts["tap"] = True
    OUT = "%s/%s" % (RAM_DIR, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(OUT)
    remember()
    gain = sh("amixer -D hw:sndrpiproto sget Capture | sed -n 's/.*Left: Capture \\([0-9]*\\).*/\\1/p'")
    info = {"label": opts["label"], "secs": opts["secs"], "reps": opts["reps"], "gain": gain,
            "model": open("/proc/device-tree/model").read().strip("\0"),
            "kernel": sh("uname -r"), "cmdline": open("/proc/cmdline").read().strip(),
            "hdmi": sh("grep -E '^hdmi' /boot/config.txt"), "lan": LAN, "mode": "nebulae (tap)",
            "before": before}
    with open(OUT + "/info.json", "w") as f:
        json.dump(info, f, indent=1)
    log("noise_parts beside Nebulae: %s, kernel %s, %s" % (info["model"], info["kernel"], opts["label"]))
    if not os.path.exists("/tmp/nebulae_spin"):
        sh("gcc -O2 -o /tmp/nebulae_spin %s/spin.c" % HERE, check=True)
    results = []
    try:
        for part in NEB_PARTS:
            if names and part[0] not in names:
                continue
            if part[0] == "usb" and (is_pi3() or not os.path.exists("/sys/bus/pci/devices/" + USB_DEV)):
                log("== usb: skipped (Pi 3: USB and LAN are one chip)")
                continue
            results.append(measure_part(part))
            with open(OUT + "/results.json", "w") as f:
                json.dump(results, f)
    finally:
        for name in list(bg):
            bg_stop(name)
        lan(True)
        sd_write_end()
        try:
            back_leds()
        except RuntimeError as e:
            log("restoring the LED settings: %s" % e)
        keep = KEEP_DIR + "/" + os.path.basename(OUT)
        os.makedirs(KEEP_DIR, exist_ok=True)
        shutil.copytree(OUT, keep)
        sh("chown -R alarm:alarm %s" % KEEP_DIR)
        log("results: %s" % keep)
    print(report(OUT))


def tap(on):
    # Same size and mtime, or fileloader.py copies the stick's instruments.
    if on:
        st = os.stat(TAP_INSTR)
        with open(TAP_INSTR, "rb") as f:
            lines = f.read().split(b"\n")   # bytes: the size must stay exact
        bare = [l.rstrip(b"\r") for l in lines]
        tap_line = TAP_LINE.encode()
        if any(l.startswith(tap_line) for l in bare):
            print("tap already in")
        else:
            if TAP_AFTER.encode() not in bare:
                sys.exit("%s not found in %s" % (TAP_AFTER, TAP_INSTR))
            start = bare.index(TAP_AFTER.encode()) + 1
            for i in range(start, min(start + 10, len(lines))):
                if bare[i].startswith(b";") and len(bare[i]) >= len(tap_line) + 1:
                    break
            else:
                sys.exit("no long enough comment line after %s" % TAP_AFTER)
            shutil.copy2(TAP_INSTR, TAP_BACKUP)
            new = tap_line + b" " + b";" * (len(bare[i]) - len(tap_line) - 1)
            lines[i] = new + lines[i][len(bare[i]):]   # keeps a \r
            with open(TAP_INSTR, "wb") as f:
                f.write(b"\n".join(lines))
            os.utime(TAP_INSTR, (st.st_atime, st.st_mtime))
            print("tap in line %d (size %d -> %d)" % (i + 1, st.st_size, os.path.getsize(TAP_INSTR)))
    else:
        if os.path.exists(TAP_BACKUP):
            shutil.copy2(TAP_BACKUP, TAP_INSTR)
            os.remove(TAP_BACKUP)
        try:
            os.remove(TAP)
        except OSError:
            pass
    print("restarting Nebulae", flush=True)
    sh("systemctl restart nebulae.service")


def is_pi3():
    try:
        with open("/proc/device-tree/model") as f:
            return "Pi 3" in f.read()
    except OSError:
        return False


def tap_record(seconds):
    """What Csound wrote to the tap during the next seconds."""
    s0 = os.path.getsize(TAP)
    time.sleep(seconds)
    s1 = os.path.getsize(TAP)
    s0, s1 = s0 - s0 % 8, s1 - s1 % 8
    with open(TAP, "rb") as f:
        f.seek(s0)
        raw = f.read(s1 - s0)
    return np.frombuffer(raw, dtype="<f4").astype(np.float64).reshape(-1, 2).T


LISTEN_DB = 40   # the clips are raised this much: the noise is near -90 dBFS


def save_wav(path, x):
    y = np.clip(x * 10 ** (LISTEN_DB / 20.0), -1, 32767 / 32768.0)
    w = wave.open(path, "wb")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(noise_measure.RATE)
    w.writeframes((y.T * 32768).astype("<i2").tobytes())
    w.close()


def recording(name, state, i):
    x = tap_record(opts["secs"]) if opts.get("tap") else noise_measure.record(opts["secs"])
    base = "%s/%s_%s_%d" % (OUT, name, state, i)
    np.save(base + ".npy", x.astype(np.float32))
    save_wav("%s_+%ddB.wav" % (base, LISTEN_DB), x)
    temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000.0
    ch = []
    for c in x:
        rms, floor, tones, at = noise_measure.analyse(c)
        ch.append({"rms": rms, "floor": floor, "tones": [[f, lv] for lv, f in tones],
                   "pulse": noise_measure.pulses(c)})
    p = ch[0]["pulse"]
    log("    %-12s %-8s #%d  rms L %.1f R %.1f  floor %.1f %.1f  %.0f C  tones L: %s" % (
        name, state, i, ch[0]["rms"], ch[1]["rms"], ch[0]["floor"], ch[1]["floor"], temp,
        ", ".join("%.0f Hz %.1f" % (f, lv) for f, lv in ch[0]["tones"][:4]) or "none"))
    log("    %-12s %-8s     pulses L: >%d Hz peak %.1f p99.9 %.1f  %.1f/s +%.1f dB  "
        "repeat %.1f ms (%.2f) sync %.1f +%.1f dB" % (
            "", "", noise_measure.HP_HZ, p["hp_peak"], p["hp_p999"], p["per_s"], p["height"],
            p["period_ms"], p["period_corr"], p["sync_db"], p["sync_height"]))
    return {"state": state, "i": i, "temp": temp, "ch": ch}


def measure_part(part):
    name, la, set_a, lb, set_b, settle, end, note = part
    log("== %s: %s" % (name, note))
    runs = []
    set_a()
    wait(settle, la)
    runs.append(recording(name, la, 0))
    for i in range(opts["reps"]):
        set_b()
        wait(settle, lb)
        runs.append(recording(name, lb, i))
        set_a()
        wait(settle, la)
        runs.append(recording(name, la, i + 1))
    if end:
        end()
    return {"name": name, "a": la, "b": lb, "note": note, "runs": runs}


def setup():
    global OUT
    OUT = "%s/%s" % (RAM_DIR, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(OUT)
    state = {
        "gain": sh("amixer -D hw:sndrpiproto sget Capture | sed -n 's/.*Left: Capture \\([0-9]*\\).*/\\1/p'"),
        "nebulae": sh("systemctl is-active nebulae"),
    }
    with open(OUT + "/before.json", "w") as f:
        json.dump(state, f)
    info = {"label": opts["label"], "secs": opts["secs"], "reps": opts["reps"], "gain": opts["gain"],
            "model": open("/proc/device-tree/model").read().strip("\0"),
            "kernel": sh("uname -r"), "cmdline": open("/proc/cmdline").read().strip(),
            "hdmi": sh("grep -E '^hdmi' /boot/config.txt"), "lan": LAN,
            "lan_carrier": sh("cat /sys/class/net/%s/carrier" % LAN)}
    with open(OUT + "/info.json", "w") as f:
        json.dump(info, f, indent=1)
    log("noise_parts: %s, kernel %s, %s" % (info["model"], info["kernel"], opts["label"]))
    # Compile spin.sh's loop now, not inside a settle time.
    if not os.path.exists("/tmp/nebulae_spin"):
        sh("gcc -O2 -o /tmp/nebulae_spin %s/spin.c" % HERE, check=True)
    log("silence state (noise_test.sh start silence)")
    log(sh("bash %s start silence" % NOISE_TEST))
    sh("amixer -q -D hw:sndrpiproto sset Capture %d" % opts["gain"])
    return state


def restore(state):
    log("restoring")
    for name in list(bg):
        bg_stop(name)
    leds("off")
    spin("off")
    lan(True)
    sd_write_end()
    sh("journalctl --relinquish-var")
    sh("amixer -q -D hw:sndrpiproto sset Capture %s" % (state.get("gain") or 23))
    log(sh("bash %s stop" % NOISE_TEST))   # Nebulae starts again (its own settings)
    keep = KEEP_DIR + "/" + os.path.basename(OUT)
    os.makedirs(KEEP_DIR, exist_ok=True)
    shutil.copytree(OUT, keep)
    log("results: %s (and %s)" % (keep, OUT))
    sh("chown -R alarm:alarm %s" % KEEP_DIR)


def run(names):
    state = setup()
    results = []
    try:
        for part in PARTS:
            if names and part[0] not in names:
                continue
            if part[0] == "usb" and is_pi3():
                log("== usb: skipped on a Pi 3 (USB and LAN are one chip)")
                continue
            if part[0] == "usb" and not os.path.exists("/sys/bus/pci/devices/" + USB_DEV):
                log("== usb: no PCI USB controller, skipped")
                continue
            results.append(measure_part(part))
            with open(OUT + "/results.json", "w") as f:
                json.dump(results, f)
    finally:
        restore(state)
    print(report(OUT))


def baseline(label):
    opts["label"] = label
    if opts.get("nebulae"):
        return baseline_nebulae(label)
    state = setup()
    try:
        runs = []
        wait(5, "silence")
        for i in range(opts["reps"] + 1):
            runs.append(recording("baseline", label, i))
        with open(OUT + "/results.json", "w") as f:
            json.dump([{"name": "baseline", "a": label, "b": label, "note": label, "runs": runs}], f)
    finally:
        restore(state)


def baseline_nebulae(label):
    """(reps + 1) recordings through the tap, Nebulae as it plays. Returns
    the folder on the SD card."""
    global OUT
    if not os.path.exists(TAP):
        sys.exit("no tap (%s): noise_parts.py tap on first" % TAP)
    opts["tap"] = True
    OUT = "%s/%s" % (RAM_DIR, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(OUT)
    info = {"label": label, "secs": opts["secs"], "reps": opts["reps"],
            "gain": sh("amixer -D hw:sndrpiproto sget Capture | sed -n 's/.*Left: Capture \\([0-9]*\\).*/\\1/p'"),
            "model": open("/proc/device-tree/model").read().strip("\0"),
            "kernel": sh("uname -r"), "cmdline": open("/proc/cmdline").read().strip(),
            "hdmi": sh("grep -E '^hdmi' /boot/config.txt"), "mode": "nebulae (tap)"}
    with open(OUT + "/info.json", "w") as f:
        json.dump(info, f, indent=1)
    log("baseline %s beside Nebulae: kernel %s, nohlt %s" % (label, info["kernel"],
                                                             "yes" if "nohlt" in info["cmdline"].split() else "no"))
    runs = [recording("baseline", label, i) for i in range(opts["reps"] + 1)]
    with open(OUT + "/results.json", "w") as f:
        json.dump([{"name": "baseline", "a": label, "b": label, "note": label, "runs": runs}], f)
    keep = KEEP_DIR + "/" + os.path.basename(OUT)
    os.makedirs(KEEP_DIR, exist_ok=True)
    shutil.copytree(OUT, keep)
    sh("chown -R alarm:alarm %s" % KEEP_DIR)
    return keep


# ---------------------------------------------------------------------------
# Boot sequence: normal, nohlt, hdmi, each measured beside a playing Nebulae
# ---------------------------------------------------------------------------

SEQ_STATE = KEEP_DIR + "/sequence.json"
SEQ_LOG = KEEP_DIR + "/sequence.log"
SEQ_UNIT = "/etc/systemd/system/noise-parts-seq.service"
SEQ_STEPS = ("normal", "nohlt", "hdmi")
SEQ_UNIT_TEXT = """[Unit]
Description=noise_parts.py boot sequence (a test; removes itself at the end)
After=nebulae.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 %s sequence step

[Install]
WantedBy=multi-user.target
""" % os.path.abspath(__file__)


def seq_log(line):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + line
    print(line, flush=True)
    os.makedirs(KEEP_DIR, exist_ok=True)
    with open(SEQ_LOG, "a") as f:
        f.write(line + "\n")


def seq_save(state):
    with open(SEQ_STATE, "w") as f:
        json.dump(state, f)


def seq_unit(install):
    if install:
        write(SEQ_UNIT, SEQ_UNIT_TEXT)
        sh("systemctl daemon-reload; systemctl enable noise-parts-seq.service")
    else:
        sh("systemctl disable noise-parts-seq.service")
        try:
            os.remove(SEQ_UNIT)
        except OSError:
            pass
        sh("systemctl daemon-reload")


def seq_wait_ready():
    """Until Csound plays and writes the tap, then a settle time for the rest
    of the boot (file loading, Wi-Fi setting, ...). False after 5 minutes."""
    end = time.time() + 300
    last = -1
    while time.time() < end:
        size = os.path.getsize(TAP) if os.path.exists(TAP) else -1
        if last > 0 and size > last:
            seq_log("tap is written; settle 30 s")
            time.sleep(30)
            return True
        last = size
        time.sleep(3)
    return False


def sequence(cmd):
    if cmd == "start":
        state = {"step": 0, "dirs": []}
        seq_save(state)
        seq_log("sequence start: %s" % " -> ".join(SEQ_STEPS))
        seq_unit(True)
        tap(True)                   # restarts Nebulae with the tap
        sh("systemctl start --no-block noise-parts-seq.service")
        print("started; progress: %s" % SEQ_LOG)
    elif cmd == "stop":
        seq_log("sequence stopped by hand")
        seq_unit(False)
        tap(False)
    elif cmd == "step":
        state = json.load(open(SEQ_STATE))
        name = SEQ_STEPS[state["step"]]
        seq_log("step %d: %s" % (state["step"], name))
        if not seq_wait_ready():
            seq_log("no tap after 5 minutes: sequence aborted")
            seq_unit(False)
            tap(False)
            return
        state["dirs"].append(baseline_nebulae(name))
        state["step"] += 1
        seq_save(state)
        seq_log("%s measured: %s" % (name, state["dirs"][-1]))
        if state["step"] < len(SEQ_STEPS):
            boot(SEQ_STEPS[state["step"]])   # sets the next boot up, reboots
            return
        text = compare(state["dirs"])
        with open(KEEP_DIR + "/sequence_compare.txt", "w") as f:
            f.write(text + "\n")
        seq_log("done:\n" + text)
        seq_unit(False)
        tap(False)
        seq_log("rebooting to normal")
        sh("sync; systemctl reboot")
    else:
        sys.exit("sequence start|stop|step")


def boot(what):
    if what == "nohlt":
        words = open("/boot/cmdline.txt").read().split()
        if "nohlt" not in words:
            write("/boot/cmdline.txt", " ".join(words + ["nohlt"]) + "\n")
    elif what == "hdmi":
        lines = [l for l in open("/boot/config.txt").read().splitlines()
                 if not l.startswith("hdmi_ignore_hotplug") and not l.startswith("hdmi_force_hotplug")]
        write("/boot/config.txt", "\n".join(lines + ["hdmi_force_hotplug=1"]) + "\n")
    else:
        sys.exit("boot nohlt|hdmi")
    sh("sync")
    print("next boot with %s; rebooting" % what, flush=True)
    sh("systemctl reboot")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def mean(values):
    return float(np.mean(values)) if values else float("nan")


def report(folder=None):
    if folder is None:
        dirs = sorted(glob.glob(KEEP_DIR + "/2*")) or sorted(glob.glob(RAM_DIR + "/2*"))
        folder = dirs[-1]
    results = json.load(open(folder + "/results.json"))
    info = json.load(open(folder + "/info.json"))
    lines = ["Noise per part: %s  (%s, kernel %s, gain step %s, %d s x %d)" % (
        os.path.basename(folder), info["model"], info["kernel"], info["gain"], info["secs"], info["reps"]),
        "label: %s" % (info["label"] or "-"),
        "delta = B - A in dB (rms 20 Hz-20 kHz, floor = median between the tones); "
        "+ = B is noisier. spread = max-min of the A recordings (what chance alone gives).",
        "",
        "%-12s %-7s %-7s %8s %8s %8s %8s %7s  %s" % ("part", "A", "B", "A rms", "B rms", "d rms", "d floor",
                                                    "spread", "tones only in B (L, Hz dBFS)")]
    for r in results:
        a = [x for x in r["runs"] if x["state"] == r["a"]]
        b = [x for x in r["runs"] if x["state"] == r["b"]]
        if r["a"] == r["b"]:   # baseline
            a, b = r["runs"], r["runs"]
        ar = mean([np.mean([c["rms"] for c in x["ch"]]) for x in a])
        br = mean([np.mean([c["rms"] for c in x["ch"]]) for x in b])
        af = mean([np.mean([c["floor"] for c in x["ch"]]) for x in a])
        bf = mean([np.mean([c["floor"] for c in x["ch"]]) for x in b])
        spread = max(np.mean([c["rms"] for c in x["ch"]]) for x in a) - \
            min(np.mean([c["rms"] for c in x["ch"]]) for x in a)
        a_tones = [t for x in a for t in x["ch"][0]["tones"]]
        new = {}
        for x in b:
            for f, lv in x["ch"][0]["tones"]:
                near = [alv for af_, alv in a_tones if abs(af_ - f) < 5]
                if not near or lv > max(near) + 6:
                    key = int(round(f))
                    new[key] = max(new.get(key, -999), lv)
        tones = ", ".join("%d %.0f" % (f, lv) for f, lv in sorted(new.items(), key=lambda t: -t[1])[:4])
        lines.append("%-12s %-7s %-7s %8.1f %8.1f %+8.1f %+8.1f %7.1f  %s" % (
            r["name"], r["a"], r["b"], ar, br, br - ar, bf - af, spread, tones or "-"))
    lines += pulse_report(results)
    text = "\n".join(lines)
    with open(folder + "/report.txt", "w") as f:
        f.write(text + "\n")
    return text


def pulse_report(results):
    """Pulses (left channel, above noise_measure.HP_HZ), A -> B; runs without
    pulse data (before pulses()) are left out."""
    lines = ["", "Pulses (L, >%d Hz): p99.9 = level 0.1 %% of the time is over (dBFS); "
             "pulses/s = 1 ms windows %d dB over the median; sync = the strongest repeat "
             "(20 ms - 1 s), folded: its level and how far over the rest of its period." % (
                 noise_measure.HP_HZ, noise_measure.OVER_DB),
             "%-14s %-7s %-7s %15s %15s %13s %15s  %s" % (
                 "part", "A", "B", "p99.9 A>B", "peak A>B", "pulses/s A>B", "sync dB A>B", "repeat in B")]
    for r in results:
        if r["a"] == r["b"]:
            continue
        a = [x["ch"][0]["pulse"] for x in r["runs"] if x["state"] == r["a"] and "pulse" in x["ch"][0]]
        b = [x["ch"][0]["pulse"] for x in r["runs"] if x["state"] == r["b"] and "pulse" in x["ch"][0]]
        if not a or not b:
            continue

        def m(runs, key):
            return mean([p[key] for p in runs])
        rep = max(b, key=lambda p: p["sync_height"])
        lines.append("%-14s %-7s %-7s %7.1f>%-7.1f %7.1f>%-7.1f %6.1f>%-6.1f %7.1f>%-7.1f  %.1f ms +%.1f dB" % (
            r["name"], r["a"], r["b"], m(a, "hp_p999"), m(b, "hp_p999"), m(a, "hp_peak"), m(b, "hp_peak"),
            m(a, "per_s"), m(b, "per_s"), m(a, "sync_db"), m(b, "sync_db"),
            rep["period_ms"], rep["sync_height"]))
    return lines


def pulses_again(folder):
    """pulses() over a run's saved recordings (also older runs)."""
    lines = []
    for path in sorted(glob.glob(folder + "/*.npy")):
        raw = np.load(path)
        x = raw.astype(np.float64) / (32768.0 if raw.dtype.kind == "i" else 1.0)
        p = noise_measure.pulses(x[0])
        lines.append("%-28s p99.9 %6.1f peak %6.1f  %5.1f/s +%4.1f dB  repeat %6.1f ms (%.2f) sync %6.1f +%4.1f dB" % (
            os.path.basename(path)[:-4], p["hp_p999"], p["hp_peak"], p["per_s"], p["height"],
            p["period_ms"], p["period_corr"], p["sync_db"], p["sync_height"]))
    return "\n".join(lines)


def compare(folders):
    """Baselines of several boots side by side (e.g. normal, nohlt, hdmi)."""
    lines = ["%-28s %-22s %8s %8s  %s" % ("run", "label", "rms", "floor", "strongest tones (L, Hz dBFS)")]
    for folder in folders:
        info = json.load(open(folder + "/info.json"))
        runs = [x for r in json.load(open(folder + "/results.json")) for x in r["runs"]]
        rms = mean([np.mean([c["rms"] for c in x["ch"]]) for x in runs])
        floor = mean([np.mean([c["floor"] for c in x["ch"]]) for x in runs])
        tones = {}
        for x in runs:
            for f, lv in x["ch"][0]["tones"]:
                tones[int(round(f))] = max(tones.get(int(round(f)), -999), lv)
        top = ", ".join("%d %.0f" % (f, lv) for f, lv in sorted(tones.items(), key=lambda t: -t[1])[:5])
        lines.append("%-28s %-22s %8.1f %8.1f  %s" % (os.path.basename(folder), info["label"][:22], rms, floor, top))
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__ or open(__file__).read().split("\nimport")[0])
        sys.exit(2)
    cmd, rest = args[0], args[1:]
    names = []
    i = 0
    while i < len(rest):
        if rest[i] == "--nebulae":   # a flag, no value
            opts["nebulae"] = True
            i += 1
        elif rest[i].startswith("--"):
            key = rest[i][2:]
            opts[key] = rest[i + 1] if key == "label" else int(rest[i + 1])
            i += 2
        else:
            names += rest[i].split(",")
            i += 1
    if cmd in ("run", "baseline", "boot", "nebulae", "tap", "sequence") and os.geteuid() != 0:
        sys.exit("run as root")
    if cmd == "sequence":
        return sequence(names[0] if names else "")
    if cmd == "run":
        run(names)
    elif cmd == "nebulae":
        nebulae_run(names)
    elif cmd == "tap":
        tap(names[:1] == ["on"])
    elif cmd == "baseline":
        baseline(names[0] if names else "baseline")
    elif cmd == "boot":
        boot(names[0] if names else "")
    elif cmd == "report":
        print(report(names[0] if names else None))
    elif cmd == "compare":
        print(compare(names))
    elif cmd == "pulses":
        print(pulses_again(names[0]))
    else:
        sys.exit("unknown command %s (run | nebulae | tap on|off | baseline LABEL | boot nohlt|hdmi"
                 " | report [DIR] | compare DIR... | pulses DIR)" % cmd)


if __name__ == "__main__":
    main()
