# A text file that is not UTF-8 (textfile.py) is damaged or saved in another
# encoding; read wrong it can do harm, so Nebulae stops: the LEDs stay red
# (scripts/nebulae_leds.sh, run again by nebulae.service's ExecStopPost), the
# report goes to the stick (neb_error.txt) and exit code 3 is not restarted.
# An instrument's files are taken out so the next start works: deleted on the
# Pi, renamed .bad on the stick (the loader skips them). A system file stays:
# the firmware has to be reinstalled.
# Only Nebulae itself sets enabled; elsewhere (NebFile) BadTextFile is raised.
import os
import subprocess
import sys
import time

import neb_globals

EXIT_CODE = 3
MARKER = "/run/nebulae-fatal"
STICK = "/mnt/memory/"
REPORT = "neb_error.txt"
SCRIPTS = "/home/alarm/QB_Nebulae_V2/Code/scripts/"
STATE_EXTS = (".pages", ".state")
JOURNAL_LINES = 50

enabled = False


class BadTextFile(OSError):
    pass


def badFile(path, pos):
    if not enabled:
        raise BadTextFile("%s is not UTF-8 (byte %d)" % (path, pos))
    try:
        _stop(path, pos)
    except Exception as e:  # a step that fails must not change the exit code
        _log("Could not finish the stop: %r" % e)
    _exit(EXIT_CODE)


def _stop(path, pos):
    report = ["Nebulae stopped: %s is not a UTF-8 text file (byte %d)." % (path, pos)]
    _log(report[0])
    _touch(MARKER)
    _stopNebio()
    _run(["sh", SCRIPTS + "nebulae_leds.sh"])
    # Silence: SuperCollider and JACK are services of their own; a program or
    # Pd is a child of Nebulae and goes with it.
    _run(["systemctl", "stop", "sclang.service", "jack@*.service"])
    instrument = instrumentOf(path)
    if instrument is not None and neb_globals.remount_fs is True:
        _run(["sh", SCRIPTS + "mountfs.sh", "rw"])
    mounted = _mountStick()
    if instrument is None:
        report.append("It is a Nebulae system file: reinstall the firmware.")
    else:
        report += _takeOut(instrument, mounted)
    for line in report[1:]:
        _log(line)
    if mounted:
        _writeReport(report)
        _run(["umount", "/dev/sda1"])


# (bank, name) when path is an instrument's file on the Pi or the stick.
def instrumentOf(path):
    import nebconfig  # nebconfig reads its files with textfile
    folder = os.path.dirname(os.path.abspath(path)) + "/"
    name, ext = os.path.splitext(os.path.basename(path))
    for bank, (bankFolder, bankExt) in nebconfig.INSTR_DIRS.items():
        if folder == bankFolder and (ext == bankExt or ext in STATE_EXTS):
            return bank, name
        if folder == STICK and (ext == bankExt or ext in STATE_EXTS
                                and os.path.isfile(STICK + name + bankExt)):
            return bank, name
    return None


def _takeOut(instrument, mounted):
    import nebconfig
    bank, name = instrument
    folder, ext = nebconfig.INSTR_DIRS[bank]
    lines = ["Instrument %s (%s) is taken out of Nebulae." % (name, bank)]
    for f in _files(folder, name, ext):
        try:
            os.remove(f)
            lines.append("Deleted on Nebulae: %s" % f)
        except OSError as e:
            lines.append("Could not delete %s: %s" % (f, e.strerror))
    for f in _files(STICK, name, ext) if mounted else []:
        try:
            os.replace(f, f + ".bad")
            lines.append("Renamed on the stick: %s -> %s.bad" % (os.path.basename(f), os.path.basename(f)))
        except OSError as e:
            lines.append("Could not rename %s: %s" % (f, e.strerror))
    lines.append("Save the file as UTF-8, give it its name back and load the instrument again.")
    return lines


def _files(folder, name, ext):
    return [folder + name + e for e in (ext,) + STATE_EXTS if os.path.isfile(folder + name + e)]


def _mountStick():
    if _stickMounted():
        return True
    _run(["bash", SCRIPTS + "usb_power.sh", "on"])
    _run(["mount", "/dev/sda1", STICK.rstrip("/")])
    return _stickMounted()


def _writeReport(report):
    text = _now() + "\n" + "\n".join(report) + "\n\nLast log lines:\n"
    text += _run(["journalctl", "-u", "nebulae", "-n", str(JOURNAL_LINES), "--no-pager", "-o", "short-iso"])
    try:
        with open(STICK + REPORT, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        _log("Could not write %s: %s" % (STICK + REPORT, e))


# The rest is replaced by the tests.

def _log(line):
    sys.stderr.write("<2>CRITICAL [fatal.py]: %s\n" % line)
    sys.stderr.flush()


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _touch(path):
    try:
        open(path, "w").close()
    except OSError as e:
        _log("Could not write %s: %s" % (path, e))


# The LED thread must not write after nebulae_leds.sh. nebio may still be
# importing (configsettings reads its file during that import).
def _stopNebio():
    shutdown = getattr(sys.modules.get("nebio"), "shutdown", None)
    if shutdown is not None:
        shutdown()


def _stickMounted():
    try:
        with open("/proc/mounts") as f:
            return any(line.split()[1] == STICK.rstrip("/") for line in f if line.strip())
    except OSError:
        return False


def _run(cmd):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
                              encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.SubprocessError) as e:
        _log("%s: %s" % (" ".join(cmd), e))
        return ""


def _exit(code):
    os._exit(code)
