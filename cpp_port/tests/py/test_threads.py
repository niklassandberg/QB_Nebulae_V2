# configsettings.py under threads, as on the device: the background job thread
# (applyAtStart's _syncCmdline) beside the main thread (setPowerRegulator),
# NebFile's CherryPy threads writing requests, and Nebulae taking them.
import os
import shutil
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402

harness.setup()
import configsettings  # noqa: E402

ROUNDS = int(os.environ.get("NEB_THREAD_ROUNDS", "400"))
CMDLINE = "console=tty1 root=/dev/mmcblk0p2 rw rootwait"


class Errors(object):
    def __init__(self):
        self.items = []
        self.lock = threading.Lock()

    def add(self, text):
        with self.lock:
            self.items.append(text)

    # ConfigSettings._log(): the worker logs what it could not run.
    def error(self, fmt, *args):
        self.add(fmt % args)

    warning = error

    def info(self, *a):
        pass

    debug = info


class ThreadTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="nebport_threads_")
        configsettings.CONFIG_FILE = os.path.join(self.dir, "configsettings.txt")
        configsettings.REQUEST_FILE = os.path.join(self.dir, "config_request")
        configsettings.CMDLINE = os.path.join(self.dir, "cmdline.txt")
        configsettings._kernelHasNohlt = lambda: False
        configsettings.subprocess.run = lambda *a, **k: None  # the scripts
        self.errors = Errors()
        configsettings.ConfigSettings._log = lambda s: self.errors

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_threads(self, *targets):
        threads = [threading.Thread(target=t) for t in targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # applyAtStart() queues _syncCmdline while the panel sets the power regulator.
    def test_cmdline_job_and_panel(self):
        with open(configsettings.CMDLINE, "w") as f:
            f.write(CMDLINE + "\n")
        c = configsettings.ConfigSettings()

        def jobs():
            for _ in range(ROUNDS):
                c._runInBackground(c._syncCmdline)

        def panel():
            for i in range(ROUNDS):
                try:
                    c.setPowerRegulator("nohlt" if i % 2 == 0 else "off")
                except Exception as e:
                    self.errors.add("setPowerRegulator: %r" % e)

        self.run_threads(jobs, panel)
        c._jobs.join()
        with open(configsettings.CMDLINE) as f:
            words = f.read().split()
        self.assertEqual([w for w in words if w != "nohlt"], CMDLINE.split())
        self.assertEqual(words.count("nohlt"), 0)  # "off" last
        self.assertFalse(os.path.exists(configsettings.CMDLINE + ".new"))
        self.assertEqual(self.errors.items, [])

    # CherryPy serves the web page from a thread pool: saves can overlap.
    def test_web_requests_overlap(self):
        def page(n):
            def save():
                for i in range(ROUNDS):
                    try:
                        configsettings.writeRequest({"led_dim": "0.%d" % n, "gate_holdoff_ms": str(i % 50)})
                    except Exception as e:
                        self.errors.add("writeRequest: %r" % e)
            return save

        self.run_threads(*[page(n) for n in range(1, 7)])
        self.assertEqual(self.errors.items, [])
        request = configsettings.takeRequest()
        self.assertEqual(sorted(request), ["gate_holdoff_ms", "led_dim"])

    # The page saves while Nebulae takes: the last save must arrive.
    def test_request_taken_while_written(self):
        lost = 0
        for trial in range(ROUNDS // 4):
            taken = []
            done = threading.Event()
            last = "%.1f" % (trial % 90 + 0.5)

            def page():
                for v in range(30):
                    configsettings.writeRequest({"gate_holdoff_ms": "%.1f" % (v + 0.1)})
                configsettings.writeRequest({"gate_holdoff_ms": last})
                done.set()

            def nebulae():
                while not done.is_set():
                    r = configsettings.takeRequest()
                    if r:
                        taken.append(r["gate_holdoff_ms"])
                r = configsettings.takeRequest()
                if r:
                    taken.append(r["gate_holdoff_ms"])

            self.run_threads(page, nebulae)
            if not taken or taken[-1] != float(last):
                lost += 1
        self.assertEqual(lost, 0, "the last save was lost in %d of %d trials" % (lost, ROUNDS // 4))

    # Setters from two threads while a third reads the file: always whole.
    def test_settings_file_always_whole(self):
        c = configsettings.ConfigSettings()
        stop = threading.Event()
        bad = []

        def reader():
            while not stop.is_set():
                try:
                    with open(configsettings.CONFIG_FILE) as f:
                        keys = [line.split("=")[0] for line in f if "=" in line]
                except FileNotFoundError:
                    continue
                if keys and len(keys) != 14:
                    bad.append(len(keys))

        def ui():
            for i in range(ROUNDS):
                c.setLedDim(i % 100 / 100.0)
                c.setNoPwm(i % 2 == 0)

        def web():
            for i in range(ROUNDS):
                c.setGateHoldoffMs(i % 100)
                c.setNebioRates(1000 + i % 500, None, None)

        r = threading.Thread(target=reader)
        r.start()
        self.run_threads(ui, web)
        stop.set()
        r.join()
        self.assertEqual(bad, [])
        self.assertEqual(self.errors.items, [])


if __name__ == "__main__":
    unittest.main()
