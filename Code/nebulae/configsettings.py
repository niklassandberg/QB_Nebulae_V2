# The config settings, "key=value" lines in CONFIG_FILE:
#   power_regulator=off    off | yield | shell | nohlt (nohlt: the Pi restarts)
#   no_pwm=off             file and freeze LEDs without PWM
#   led_stagger=on
#   services_quiet=off
#   wifi=on
#   led_dim=0.50
#   log_level=INFO         DEBUG, STATS, INFO .. CRITICAL (by hand)
#   nebio_scan_hz=1200, nebio_digital_hz=400, nebio_adc_hz=400,
#   nebio_fast_gpio=off    (by hand)
#   csound_rt_priority=70  SCHED_FIFO 1-99, 0 = normal (by hand)
# A missing or invalid value keeps its default.

import os
import queue
import subprocess
import threading

CONFIG_FILE = "/home/alarm/QB_Nebulae_V2/Code/config/configsettings.txt"
SCRIPTS_DIR = "/home/alarm/QB_Nebulae_V2/Code/scripts/"
QUIET_SCRIPT = SCRIPTS_DIR + "quiet.sh"
WIFI_SCRIPT = SCRIPTS_DIR + "wifi.sh"

CMDLINE = "/boot/cmdline.txt"

POWER_REGULATOR = ("off", "yield", "shell", "nohlt")


def _kernelHasNohlt():
    try:
        with open("/proc/cmdline") as f:
            return "nohlt" in f.read().split()
    except OSError:
        return False
LOG_LEVELS = ("DEBUG", "STATS", "INFO", "WARNING", "ERROR", "CRITICAL")


def _rate(text, default):
    try:
        hz = int(text)
    except (TypeError, ValueError):
        return default
    return hz if 1 <= hz <= 10000 else default


class ConfigSettings(object):

    def __init__(self):
        self._powerRegulator = "off"
        self._noPwm = False
        self._ledStagger = True
        self._servicesQuiet = False
        self._wifiOn = False
        self._ledDim = 1.0
        self._logLevel = "INFO"
        # As often as the original firmware read the hardware.
        self._nebioScanHz = 1200
        self._nebioDigitalHz = 400
        self._nebioAdcHz = 400
        self._nebioFastGpio = False
        self._csoundRtPriority = 70  # below jackd's 75
        self._lock = threading.Lock()
        self._jobs = None
        self.load()

    def load(self):
        # No logging in here: classlogger reads logLevel before logging is set up.
        values = {}
        try:
            with open(CONFIG_FILE) as f:
                for line in f:
                    key, sep, value = line.strip().partition("=")
                    if sep:
                        values[key.strip()] = value.strip()
        except FileNotFoundError:
            try:
                open(CONFIG_FILE, "a").close()
            except OSError:
                pass
        except OSError:
            pass
        with self._lock:
            if values.get("power_regulator") in POWER_REGULATOR:
                self._powerRegulator = values["power_regulator"]
            if values.get("no_pwm") in ("on", "off"):
                self._noPwm = values["no_pwm"] == "on"
            if values.get("led_stagger") in ("on", "off"):
                self._ledStagger = values["led_stagger"] == "on"
            if values.get("services_quiet") in ("on", "off"):
                self._servicesQuiet = values["services_quiet"] == "on"
            wifi = values.get("wifi")
            if wifi in ("on", "off"):
                self._wifiOn = wifi == "on"
            try:
                self._ledDim = min(1.0, max(0.0, float(values["led_dim"])))
            except (KeyError, ValueError):
                pass
            level = values.get("log_level", "").upper()
            if level in LOG_LEVELS:
                self._logLevel = level
            self._nebioScanHz = _rate(values.get("nebio_scan_hz"), self._nebioScanHz)
            self._nebioDigitalHz = _rate(values.get("nebio_digital_hz"), self._nebioDigitalHz)
            self._nebioAdcHz = _rate(values.get("nebio_adc_hz"), self._nebioAdcHz)
            fast = values.get("nebio_fast_gpio")
            if fast in ("on", "off"):
                self._nebioFastGpio = fast == "on"
            try:
                prio = int(values["csound_rt_priority"])
                if 0 <= prio <= 99:
                    self._csoundRtPriority = prio
            except (KeyError, ValueError):
                pass

    @property
    def powerRegulator(self):
        return self._powerRegulator

    @property
    def powerNeedsRestart(self):
        return self._wantNohlt() != _kernelHasNohlt()

    @property
    def noPwm(self):
        return self._noPwm

    @property
    def ledStagger(self):
        return self._ledStagger

    @property
    def servicesQuiet(self):
        return self._servicesQuiet

    @property
    def wifiOn(self):
        return self._wifiOn

    @property
    def ledDim(self):
        return self._ledDim

    @property
    def logLevel(self):
        return self._logLevel

    @property
    def nebioScanHz(self):
        return self._nebioScanHz

    @property
    def nebioDigitalHz(self):
        return self._nebioDigitalHz

    @property
    def nebioAdcHz(self):
        return self._nebioAdcHz

    @property
    def nebioFastGpio(self):
        return self._nebioFastGpio

    @property
    def csoundRtPriority(self):
        return self._csoundRtPriority

    # The system boots with Quiet mode and Wi-Fi off. Called after the first
    # instrument load: start_wifi.sh mounts the stick.
    def applyAtStart(self):
        if self._servicesQuiet:
            self._runInBackground([QUIET_SCRIPT, "services", "on"])
        if self._powerRegulator in ("yield", "shell"):
            self._runInBackground([QUIET_SCRIPT, "spin", self._powerRegulator])
        self._runInBackground([WIFI_SCRIPT, "on" if self._wifiOn else "off"])
        self._runInBackground(self._syncCmdline)

    # Returns True when the Pi must restart (nohlt is read at boot).
    def setPowerRegulator(self, value):
        if value not in POWER_REGULATOR:
            raise ValueError("power_regulator %s, not %r" % ("|".join(POWER_REGULATOR), value))
        with self._lock:
            if value == self._powerRegulator:
                return False
            self._powerRegulator = value
            self._save()
        self._log().info("Power regulator: %s", value)
        self._syncCmdline()   # not in the background: a reboot may follow
        if self.powerNeedsRestart:
            return True
        self._runInBackground([QUIET_SCRIPT, "spin", value if value != "nohlt" else "off"])
        return False

    def setNoPwm(self, on):
        on = bool(on)
        with self._lock:
            if on == self._noPwm:
                return
            self._noPwm = on
            self._save()
        self._log().info("No PWM: %s", "on" if on else "off")

    def setLedStagger(self, on):
        on = bool(on)
        with self._lock:
            if on == self._ledStagger:
                return
            self._ledStagger = on
            self._save()
        self._log().info("LED stagger: %s", "on" if on else "off")

    def setServicesQuiet(self, on):
        on = bool(on)
        with self._lock:
            if on == self._servicesQuiet:
                return
            self._servicesQuiet = on
            self._save()
        self._log().info("Services no sounds: %s", "on" if on else "off")
        self._runInBackground([QUIET_SCRIPT, "services", "on" if on else "off"])

    def setWifiOn(self, on):
        on = bool(on)
        with self._lock:
            if on == self._wifiOn:
                return
            self._wifiOn = on
            self._save()
        self._log().info("Wi-Fi %s", "on" if on else "off")
        self._runInBackground([WIFI_SCRIPT, "on" if on else "off"])

    def setLedDim(self, value):
        value = round(min(1.0, max(0.0, float(value))), 2)
        with self._lock:
            if value == self._ledDim:
                return
            self._ledDim = value
            self._save()
        self._log().info("LED dim %.2f", value)

    # Synced with its folder: else the rename reaches the SD card only after
    # up to 5 s, and a case switched off sooner keeps the old values.
    # Called with self._lock held.
    def _save(self):
        text = ("power_regulator=%s\n" % self._powerRegulator
                + "no_pwm=%s\n" % ("on" if self._noPwm else "off")
                + "led_stagger=%s\n" % ("on" if self._ledStagger else "off")
                + "services_quiet=%s\n" % ("on" if self._servicesQuiet else "off")
                + "wifi=%s\n" % ("on" if self._wifiOn else "off")
                + "led_dim=%.2f\n" % self._ledDim
                + "log_level=%s\n" % self._logLevel
                + "nebio_scan_hz=%d\n" % self._nebioScanHz
                + "nebio_digital_hz=%d\n" % self._nebioDigitalHz
                + "nebio_adc_hz=%d\n" % self._nebioAdcHz
                + "nebio_fast_gpio=%s\n" % ("on" if self._nebioFastGpio else "off")
                + "csound_rt_priority=%d\n" % self._csoundRtPriority)
        tmp = CONFIG_FILE + ".new"
        try:
            with open(tmp, "w") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CONFIG_FILE)
            folder = os.open(os.path.dirname(CONFIG_FILE), os.O_RDONLY)
            try:
                os.fsync(folder)
            finally:
                os.close(folder)
        except OSError as e:
            self._log().error("Could not save %s: %s", CONFIG_FILE, e)

    # One thread: the scripts run in the order the settings were changed.
    def _runInBackground(self, command):
        if self._jobs is None:
            self._jobs = queue.Queue()
            threading.Thread(target=self._worker, name="configsettings", daemon=True).start()
        self._jobs.put(command)

    def _worker(self):
        while True:
            command = self._jobs.get()
            try:
                if callable(command):
                    command()
                else:
                    subprocess.run(["systemd-cat", "-t", "nebulae-config", "/bin/bash"] + command,
                                   stdin=subprocess.DEVNULL)
            except Exception as e:
                self._log().error("Could not run %s: %s", command, e)
            finally:
                self._jobs.task_done()

    def _wantNohlt(self):
        return self._powerRegulator == "nohlt"

    def _syncCmdline(self):
        want = self._wantNohlt()
        with open(CMDLINE) as f:
            words = f.read().split()
        if ("nohlt" in words) == want:
            return
        words = [w for w in words if w != "nohlt"] + (["nohlt"] if want else [])
        tmp = CMDLINE + ".new"
        with open(tmp, "w") as f:
            f.write(" ".join(words) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CMDLINE)
        folder = os.open(os.path.dirname(CMDLINE), os.O_RDONLY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
        self._log().info("%s nohlt in %s: active from the next restart",
                         "Added" if want else "Removed", CMDLINE)

    def waitUntilApplied(self):
        if self._jobs is not None:
            self._jobs.join()

    def _log(self):
        from classlogger import ClassLogger  # circular import
        return ClassLogger.loggerSetup(self)


configSettings = ConfigSettings()
