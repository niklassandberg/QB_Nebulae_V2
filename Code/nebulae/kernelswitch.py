# Kernel per instrument: an instrument can ask for the real-time kernel
# (PREEMPT_RT, Resources/kernel/nebulae-rt.config). nebulae.py asks
# switchFor() with the instrument's NebConfig (nebconfig.py, read once by
# nebulae.py) before it starts the instrument; when the running kernel is the
# wrong one, the boot setting is changed and the Pi restarts (a kernel cannot
# be changed while it runs). bootinstr.txt is already written, so the Pi
# comes back on the same instrument, now on the kernel it wants.
#
# In the instrument:
#   kernel,rt in its nebconfig (nebconfig.py: the block of a .instr/.scd,
#   a comment box "nebconfig kernel,rt" in a .pd)
# Values:
#   rt      the RT kernel; restarts into it when it is not running
#   normal  the normal kernel; restarts back when the RT kernel is running.
#           Also when there is no line (or an unknown value): an instrument
#           that does not ask for RT plays on the normal kernel.
#   any     either one, never a restart (only when the line says so)
#
# The normal kernel is whatever the card boots without the switch's line
# (stock kernel8.img, or a kernel= line set by hand). The switch owns one
# block only, at the end of BOOT_FILE (the last kernel= line wins):
#   [all] / RT_COMMENT / RT_ARM64 / RT_LINE
# and removes exactly that block again. RT_ARM64 is in it because the
# firmware starts a kernel with its own name (not kernel8.img) in 32-bit mode
# without arm_64bit=1, also on a Pi 4: the 64-bit kernel then hangs at once
# (2026-10-31, an image older than the release image had no arm_64bit=1).
#
# Safety:
# - RT kernel not on the card (image or modules missing): no restart, the
#   instrument plays on the running kernel.
# - No restart loop: before the restart, MARKER gets the wanted kernel and
#   the boot id. When the Pi comes back still on the other kernel, it is
#   not tried again (until an instrument wants something else).
# - The RT kernel does not start at all: remove RT_LINE from
#   nebulae-image.txt on the boot partition (a FAT drive on a PC).

import glob
import os
import subprocess

import neb_globals
import nebconfig
from classlogger import ClassLogger

BOOT_FILE = "/boot/nebulae-image.txt"  # included from config.txt (the image's own settings)
RT_IMAGE = "kernel8-nebulae-rt.img"
RT_LINE = "kernel=" + RT_IMAGE
RT_COMMENT = "# real-time kernel, set and removed by Nebulae (kernelswitch.py)"
RT_ARM64 = "arm_64bit=1"  # a kernel= name the firmware does not know starts 32-bit without it
MARKER = "/home/alarm/QB_Nebulae_V2/Code/config/kernel_switch.txt"
MOUNTFS = "/home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh"


def runningRt():
    """The running kernel is a PREEMPT_RT kernel (/sys/kernel/realtime only
    exists there)."""
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
    """(target, boot_id) of the last switch, or (None, None)."""
    try:
        with open(MARKER) as f:
            fields = dict(line.strip().split(",", 1) for line in f if "," in line)
        return fields.get("target"), fields.get("boot_id")
    except (OSError, ValueError):
        return None, None


def _safeWrite(path, text):
    """New file, fsync, rename, fsync folder (as configsettings.py): a power
    cut leaves the old or the new file."""
    tmp = path + ".new"
    with open(tmp, "w") as f:
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
    """MARKER with the wanted kernel and this boot's id, or removed (None)."""
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
    """Our block ([all], RT_COMMENT, RT_ARM64, RT_LINE) at the end of
    BOOT_FILE, or removed. Other lines stay as they are, also an arm_64bit=1
    of the image itself (only the one right after RT_COMMENT is ours)."""
    try:
        with open(BOOT_FILE) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []
    kept = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if line == RT_COMMENT:
            # our [all] before it, our arm_64bit=1 after it (older switches
            # wrote the block without it)
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
        """rt | normal | any from the instrument's NebConfig (normal without
        an entry); an unknown value is normal."""
        value = config.kernel()
        if value not in nebconfig.KERNELS:
            self.log.warning("%s: unknown kernel value '%s' (rt, normal, any): normal", instr, value)
            return "normal"
        return value

    def switchFor(self, instr, config):
        """Before the instrument starts. True: the Pi is restarting into the
        kernel the instrument wants (the caller must not start it)."""
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
