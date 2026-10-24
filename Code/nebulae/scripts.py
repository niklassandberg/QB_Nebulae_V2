import glob
import os
import subprocess
import threading
from classlogger import ClassLogger
from configsettings import configSettings

# The 4th page of the instr selector: scripts and compiled executables.
# Firmware scripts (FIRMWARE_DIR) come first, then the user's from the USB
# stick (USER_DIR, copied by fileloader like instruments).
#
# A script is run with no arguments when it is selected (speed click), in
# the background as root; the instrument keeps playing. Output goes to the
# journal: journalctl -t nebscript-<name>.
# "<script> status" tells its state for the slot LED: exit 0 = on (bright),
# exit 1 = off (dim), anything else = no state (dim, like an instr slot).
# Only scripts that contain STATUS_MARKER (e.g. in a comment) are asked:
# a script that ignores its arguments would otherwise be run by the status check.
FIRMWARE_DIR = "/home/alarm/QB_Nebulae_V2/Code/nebscripts/"
USER_DIR = "/home/alarm/scripts/"
EXTENSIONS = [".sh", ".neb"]  # .neb: any executable (compiled program)
# .ui: handled inside Nebulae (ui.py), not run; firmware only. The mode is
# the name after the number: 4_led_dim.ui -> "led_dim". Their slot LED shows
# the config setting (UI_STATES, from configsettings.py).
UI_EXTENSION = ".ui"
UI_STATES = {"wifi": lambda: configSettings.wifiOn,
             "quiet": lambda: configSettings.quietMode > 0}
STATUS_TIMEOUT_S = 2.0
STATUS_MARKER = b"nebulae-status"

ON = 1
OFF = 0
NO_STATE = -1

class ScriptHandler(object):
    def __init__(self):
        self.log = ClassLogger.loggerSetup(self)
        self.files = self.find(FIRMWARE_DIR, EXTENSIONS + [UI_EXTENSION]) + self.find(USER_DIR, EXTENSIONS)
        self.fileCount = len(self.files)
        self.states = [NO_STATE] * self.fileCount
        self.has_status = [self.hasStatus(f) for f in self.files]
        self.running = {}   # idx -> Popen of a run that has not ended
        self.lock = threading.Lock()

    def find(self, directory, extensions):
        files = []
        for ext in extensions:
            files.extend(glob.glob(directory + '*' + ext))
        files.sort(key=lambda v: (v.upper(), v[0].islower()))
        return files

    def hasStatus(self, path):
        try:
            with open(path, "rb") as f:
                return STATUS_MARKER in f.read(4096)
        except OSError:
            return False

    # Same interface as FileHandler, for the instr selector.
    def numFiles(self):
        return self.fileCount

    def getFilename(self, idx):
        if idx < self.fileCount:
            return os.path.splitext(os.path.basename(self.files[idx]))[0]

    def getIndex(self, name):
        return None  # a script is never the current instrument

    # The mode of a .ui entry ("led_dim"), None for a script that is run.
    def uiMode(self, idx):
        if idx < self.fileCount and self.files[idx].endswith(UI_EXTENSION):
            return self.getFilename(idx).split("_", 1)[-1]
        return None

    def command(self, idx, *args):
        path = self.files[idx]
        if path.endswith(".sh"):
            return ["/bin/bash", path] + list(args)
        return [path] + list(args)

    def run(self, idx):
        if idx >= self.fileCount or self.uiMode(idx) is not None:
            return
        name = self.getFilename(idx)
        proc = self.running.get(idx)
        if proc is not None and proc.poll() is None:
            self.log.info("Script %s is still running, not started again", name)
            return
        self.log.info("Running script %s", self.files[idx])
        try:
            # Output to the journal: journalctl -t nebscript-<name>.
            # systemd-cat execs the script, so proc is the script itself.
            proc = subprocess.Popen(["systemd-cat", "-t", "nebscript-" + name]
                                    + self.command(idx),
                                    stdin=subprocess.DEVNULL,
                                    start_new_session=True)
            self.running[idx] = proc
            threading.Thread(target=self.refreshWhenDone, args=(proc,), daemon=True).start()
        except OSError as e:
            self.log.error("Could not run script %s: %s", name, e)

    # LED state of each slot; read by the UI, filled by refresh().
    def state(self, idx):
        with self.lock:
            return self.states[idx] if idx < self.fileCount else NO_STATE

    # "status" is read once when the configsettings page is shown and once after a
    # script has ended (the states only change by running one), in a thread
    # so a slow script never holds up the UI loop. It was polled every
    # second: each poll started bash + systemctl, a burst of activity heard
    # in the audio as a steady beat while the page was shown.
    def startPolling(self):
        self.refresh()

    def stopPolling(self):
        pass

    def refresh(self):
        threading.Thread(target=self.readAll, daemon=True).start()

    def readAll(self):
        for idx in range(self.fileCount):
            if self.has_status[idx]:
                s = self.readStatus(idx)
                with self.lock:
                    self.states[idx] = s

    def refreshWhenDone(self, proc):
        proc.wait()
        self.readAll()

    def readStatus(self, idx):
        mode = self.uiMode(idx)
        if mode is not None:
            return (ON if UI_STATES[mode]() else OFF) if mode in UI_STATES else NO_STATE
        try:
            r = subprocess.run(self.command(idx, "status"), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                               timeout=STATUS_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired):
            return NO_STATE
        if r.returncode == 0:
            return ON
        if r.returncode == 1:
            return OFF
        return NO_STATE
