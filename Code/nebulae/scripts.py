import glob
import os
import subprocess
import threading
from classlogger import ClassLogger
from configsettings import configSettings

# The configsettings page. A script runs as root in the background, output
# in journalctl -t nebscript-<name>. Scripts containing STATUS_MARKER are
# asked "<script> status" for their LED: exit 0 = on, 1 = off.
FIRMWARE_DIR = "/home/alarm/QB_Nebulae_V2/Code/nebscripts/"
USER_DIR = "/home/alarm/scripts/"
EXTENSIONS = [".sh", ".neb"]  # .neb: any executable
# .ui: handled by ui.py, mode from the name: 6_led_dim.ui -> "led_dim".
UI_EXTENSION = ".ui"
UI_STATES = {"wifi": lambda: configSettings.wifiOn,
             "power_regulator": lambda: configSettings.powerRegulator != "off",
             "no_pwm": lambda: configSettings.noPwm,
             "led_stagger": lambda: configSettings.ledStagger,
             "services_quiet": lambda: configSettings.servicesQuiet}
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
        self.running = {}   # idx -> Popen
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

    def numFiles(self):
        return self.fileCount

    def getFilename(self, idx):
        if idx < self.fileCount:
            return os.path.splitext(os.path.basename(self.files[idx]))[0]

    def getIndex(self, name):
        return None

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
            proc = subprocess.Popen(["systemd-cat", "-t", "nebscript-" + name]
                                    + self.command(idx),
                                    stdin=subprocess.DEVNULL,
                                    start_new_session=True)
            self.running[idx] = proc
            threading.Thread(target=self.refreshWhenDone, args=(proc,), daemon=True).start()
        except OSError as e:
            self.log.error("Could not run script %s: %s", name, e)

    def state(self, idx):
        with self.lock:
            return self.states[idx] if idx < self.fileCount else NO_STATE

    # Not polled: each status call was heard in the audio.
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
