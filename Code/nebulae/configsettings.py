# Nebulae's config settings (the configsettings page): read and saved here only.
#
# Nebulae code never opens the file itself: it reads the values from the
# singleton configSettings (configSettings.ledDim, .wifiOn, .quietMode) and
# saves a change through it (configSettings.setLedDim(0.4), ...), which also
# starts the part that switches the system (the shell scripts below).
#
# All settings are in one file, CONFIG_FILE, one "key=value" per line:
#   quiet_mode=2     0 = off, 1-3 = Quiet level      (scripts/quiet.sh)
#   wifi=on          on | off                        (scripts/wifi.sh)
#   led_dim=0.50     0.00 = off .. 1.00 = full
#   log_level=INFO   DEBUG, STATS, INFO .. CRITICAL, set by hand (classlogger.py;
#                    STATS: also the status lines every 10 s)
#   nebio_scan_hz=1200, nebio_digital_hz=400, nebio_adc_hz=400, nebio_fast_gpio=off
#                    nebio's input rates and GPIO access (controlhandler.py);
#                    no UI yet, set by hand
#   csound_rt_priority=70  Csound thread SCHED_FIFO 1-99, 0 = normal
#                    (nebulae.py setRealtime); no UI, set by hand
# The defaults are in the constructor. A missing file is created empty; a
# missing or invalid value keeps its default. Every save writes all values.
# Nothing else reads the file: the system starts with Quiet mode and Wi-Fi
# off, and Nebulae applies the saved settings once it has loaded its first
# instrument (applyAtStart). The shell scripts only switch (quiet.sh, wifi.sh).
#
# A firmware update replaces Code/config: every setting back to its default.
# Knob values of the instruments are not here: settings.py (nebsettings.txt).

import os
import queue
import subprocess
import threading

CONFIG_FILE = "/home/alarm/QB_Nebulae_V2/Code/config/configsettings.txt"
SCRIPTS_DIR = "/home/alarm/QB_Nebulae_V2/Code/scripts/"
QUIET_SCRIPT = SCRIPTS_DIR + "quiet.sh"
WIFI_SCRIPT = SCRIPTS_DIR + "wifi.sh"

QUIET_LEVELS = (0, 1, 2, 3)
LOG_LEVELS = ("DEBUG", "STATS", "INFO", "WARNING", "ERROR", "CRITICAL")


def _rate(text, default):
    """A rate in Hz from the file (whole number 1-10000), else the default."""
    try:
        hz = int(text)
    except (TypeError, ValueError):
        return default
    return hz if 1 <= hz <= 10000 else default


class ConfigSettings(object):

    def __init__(self):
        # Defaults: used when the file has no (valid) value.
        self._quietMode = 0
        self._wifiOn = False
        self._ledDim = 1.0
        self._logLevel = "INFO"
        # nebio input rates: the hardware read as often as the original
        # firmware (0419df1) did, so the CPU use can be compared:
        # - shift register, encoder clicks and ADCs were read once per
        #   updateAll(), measured about 400 times/s -> digital 400 Hz, ADC
        #   400 Hz. The ADC rate is also the highest rate updateAll() runs at.
        # - encoders were polled by their own threads with sleep(0.001), just
        #   under 1 kHz -> scan 1200 Hz (every 3rd scan: exactly 400 Hz).
        # - button debounce: original 3 equal reads, nebio 8 ms = 3 at 400 Hz.
        self._nebioScanHz = 1200
        self._nebioDigitalHz = 400
        self._nebioAdcHz = 400
        # Fast GPIO: shift register + encoder/click pins through /dev/gpiomem
        # (Code/nebio/src/gpiomem.h) instead of libgpiod.
        self._nebioFastGpio = False
        # Csound's performance thread in real-time priority (SCHED_FIFO),
        # below jackd (75); 0 = normal priority.
        self._csoundRtPriority = 70
        self._lock = threading.Lock()
        self._jobs = None  # queue of shell commands, started on first use
        self.load()

    # -------------------------
    # Reading
    # -------------------------

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
            quiet = values.get("quiet_mode")
            if quiet in ("0", "1", "2", "3"):
                self._quietMode = int(quiet)
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
    def quietMode(self):
        return self._quietMode

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

    # -------------------------
    # Applying at Nebulae's start
    # -------------------------

    def applyAtStart(self):
        """The saved settings to the system, which starts with Quiet mode and
        Wi-Fi off. Called by Nebulae after its first instrument load: the
        stick is free then (start_wifi.sh mounts it). Again after a restart
        of Nebulae does no harm (nothing is switched twice)."""
        if self._quietMode:
            self._runInBackground([QUIET_SCRIPT, "change", "0", str(self._quietMode)])
        self._runInBackground([WIFI_SCRIPT, "on" if self._wifiOn else "off"])

    # -------------------------
    # Saving (file + switching the system)
    # -------------------------

    def setQuietMode(self, level):
        if level not in QUIET_LEVELS:
            raise ValueError("quiet mode level 0-3, not %r" % (level,))
        with self._lock:
            old = self._quietMode
            if level == old:
                return
            self._quietMode = level
            self._save()
        self._log().info("Quiet mode %d -> %d", old, level)
        # Quiet mode switches Wi-Fi off when it is turned on; it is saved as off.
        if old == 0 and self._wifiOn:
            self.setWifiOn(False)
        self._runInBackground([QUIET_SCRIPT, "change", str(old), str(level)])

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
        # Only saved: the UI gives it to nebio while it is being turned.
        value = round(min(1.0, max(0.0, float(value))), 2)
        with self._lock:
            if value == self._ledDim:
                return
            self._ledDim = value
            self._save()
        self._log().info("LED dim %.2f", value)

    # -------------------------
    # Internal
    # -------------------------

    def _save(self):
        """All values to a new file, renamed over the old one: a power cut
        leaves the old or the new file, never half a file. The folder is
        synced too: the rename is otherwise only on the SD card after up to
        5 s (ext4 journal), and a Eurorack case switched off sooner started
        with the old values. Called with self._lock held."""
        text = ("quiet_mode=%d\n" % self._quietMode
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

    # The shell scripts run one after the other in one background thread:
    # in the order the settings were changed (Wi-Fi off before the Quiet
    # mode change), and the UI never waits for them.
    def _runInBackground(self, command):
        if self._jobs is None:
            self._jobs = queue.Queue()
            threading.Thread(target=self._worker, name="configsettings", daemon=True).start()
        self._jobs.put(command)

    def _worker(self):
        while True:
            command = self._jobs.get()
            try:
                subprocess.run(["systemd-cat", "-t", "nebulae-config", "/bin/bash"] + command,
                               stdin=subprocess.DEVNULL)
            except OSError as e:
                self._log().error("Could not run %s: %s", " ".join(command), e)
            finally:
                self._jobs.task_done()

    def waitUntilApplied(self):
        """Until the shell scripts of all changes so far have run."""
        if self._jobs is not None:
            self._jobs.join()

    def _log(self):
        # Imported here: classlogger reads logLevel from this module.
        from classlogger import ClassLogger
        return ClassLogger.loggerSetup(self)


# The one instance all of Nebulae uses.
configSettings = ConfigSettings()
