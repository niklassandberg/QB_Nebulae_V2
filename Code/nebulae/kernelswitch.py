# "kernel,rt|normal|any" in an instrument restarts the Pi into that kernel.
# The switch owns one block at the end of BOOT_FILE: [all] / RT_COMMENT /
# RT_ARM64 / RT_LINE. MARKER (wanted kernel + boot id) stops a restart loop.
# If the RT kernel does not boot: remove RT_LINE from nebulae-image.txt on
# the boot partition.

import glob
import os
import subprocess

import neb_globals
import nebconfig
import textfile
from classlogger import ClassLogger

BOOT_FILE = "/boot/nebulae-image.txt"
RT_IMAGE = "kernel8-nebulae-rt.img"
RT_LINE = "kernel=" + RT_IMAGE
RT_COMMENT = "# real-time kernel, set and removed by Nebulae (kernelswitch.py)"
RT_ARM64 = "arm_64bit=1"  # else a renamed kernel starts in 32-bit mode and hangs
MARKER = "/home/alarm/QB_Nebulae_V2/Code/config/kernel_switch.txt"
MOUNTFS = "/home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh"


def runningRt():
    if os.path.exists("/sys/kernel/realtime"):
        return True
    return "PREEMPT_RT" in os.uname().version


def rtInstalled():
    return (os.path.isfile("/boot/" + RT_IMAGE)
            and bool(glob.glob("/usr/lib/modules/*-nebulae-rt/modules.dep")))


def _bootId():
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()
    except OSError:
        return ""


def _readMarker():
    try:
        fields = dict(line.strip().split(",", 1) for line in textfile.lines(MARKER) if "," in line)
        return fields.get("target"), fields.get("boot_id")
    except (OSError, ValueError):
        return None, None


def _safeWrite(path, text):
    tmp = path + ".new"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    folder = os.open(os.path.dirname(path), os.O_RDONLY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def _writeMarker(target):
    if neb_globals.remount_fs is True:
        os.system("sh " + MOUNTFS + " rw")
    try:
        if target is None:
            if os.path.exists(MARKER):
                os.remove(MARKER)
        else:
            _safeWrite(MARKER, "target,%s\nboot_id,%s\n" % (target, _bootId()))
    finally:
        if neb_globals.remount_fs is True:
            os.system("sh " + MOUNTFS + " ro")


def _setBootLine(rt):
    try:
        lines = textfile.read(BOOT_FILE).splitlines()
    except FileNotFoundError:
        lines = []
    kept = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if line == RT_COMMENT:
            if kept and kept[-1].strip() == "[all]":
                kept.pop()
            if i < len(lines) and lines[i].strip() == RT_ARM64:
                i += 1
        elif line != RT_LINE:
            kept.append(lines[i - 1])
    if rt:
        kept += ["[all]", RT_COMMENT, RT_ARM64, RT_LINE]
    _safeWrite(BOOT_FILE, "\n".join(kept) + "\n")


class KernelSwitch(object):
    def __init__(self):
        self.log = ClassLogger.loggerSetup(self)

    def wanted(self, instr, config):
        value = config.kernel()
        if value not in nebconfig.KERNELS:
            self.log.warning("%s: unknown kernel value '%s' (rt, normal, any): normal", instr, value)
            return "normal"
        return value

    # True: the Pi is restarting, the instrument must not start.
    def switchFor(self, instr, config):
        try:
            want = self.wanted(instr, config)
            onRt = runningRt()
            target, bootId = _readMarker()
            if want == "any" or (want == "rt") == onRt:
                if want != "any":
                    self.log.info("%s wants the %s kernel: already running", instr, want)
                if target is not None:
                    _writeMarker(None)
                return False
            if want == "rt" and not rtInstalled():
                self.log.warning("%s wants the RT kernel, but /boot/%s or its modules are "
                                 "missing: plays on the running kernel", instr, RT_IMAGE)
                return False
            if target == want and bootId != _bootId():
                self.log.error("%s wants the %s kernel, but the restart for it did not "
                               "switch (running %s): not tried again", instr, want, os.uname().release)
                return False
            self.log.info("%s wants the %s kernel (running %s): restarting the Pi",
                          instr, want, os.uname().release)
            _setBootLine(want == "rt")
            _writeMarker(want)
            subprocess.Popen(["systemctl", "reboot"])
            return True
        except Exception as e:
            self.log.error("Kernel switch for %s failed: %s", instr, e)
            return False
