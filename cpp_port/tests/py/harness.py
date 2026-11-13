# Runs the original Python classes (B) from Code/nebulae with only the
# outermost layer faked: nebio's C functions, Csound channels, the clock,
# random numbers and file paths. Same fakes as tests/cpp/fakes.h.
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
NEBULAE = os.path.normpath(os.path.join(HERE, "..", "..", "..", "Code", "nebulae"))

os.environ["NEB_LOG_LEVEL"] = "CRITICAL"


def fmt(v):
    """Value with its Python type, the same text as fmt() in tests/cpp."""
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "b:%s" % v
    if isinstance(v, int):
        return "i:%d" % v
    if isinstance(v, float):
        return "f:" + repr(v)
    if isinstance(v, bytes):
        return "s:" + v.decode("utf-8", "replace").replace("\n", "\\n")
    if isinstance(v, str):
        return "s:" + v.replace("\n", "\\n")
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(fmt(x) for x in v) + "]"
    return "?" + type(v).__name__


class FakeClock(object):
    """time.time() and time.sleep() for the modules under test."""

    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeRandom(object):
    """random.randint from a queue (scenario "rand")."""

    def __init__(self):
        self.queue = []

    def randint(self, a, b):
        if not isinstance(a, int) or not isinstance(b, int):
            raise TypeError("'float' object cannot be interpreted as an integer")
        v = self.queue.pop(0) if self.queue else a
        return min(b, max(a, v))


class FakeCLib(object):
    """nebio's C functions (include/nebio.h): state plus a call log."""

    def __init__(self):
        self.calls = []
        self.adc = [0] * 16
        self.gpio = [-1] * 64
        self.sr = 0
        self.snap_n = 0
        self.ret = {}

    def log(self, name, *args):
        self.calls.append("%s(%s)" % (name, ",".join(fmt(a) for a in args)))

    def r(self, name, default=0):
        return self.ret.get(name, default)

    # Inputs
    def nebio_inputs_init(self):
        self.log("inputs_init")
        return self.r("inputs_init")

    def nebio_snapshot(self):
        self.snap_n += 1
        return self.snap_n

    def nebio_adc_codes(self, arr, n):
        for i in range(n):
            arr[i] = self.adc[i]
        return n

    def nebio_gpio_levels(self, arr, n):
        for i in range(n):
            arr[i] = self.gpio[i]
        return n

    def nebio_sr_bits(self):
        return self.sr

    def nebio_last_error(self):
        return b"fake error"

    def nebio_stats(self):
        return b"fake stats"

    def __getattr__(self, name):
        if not name.startswith("nebio_"):
            raise AttributeError(name)
        short = name[len("nebio_"):]

        def call(*args):
            self.log(short, *[a.value if hasattr(a, "value") else a for a in args])
            return self.r(short)
        return call


def setup():
    """Fake modules, then import the originals. Returns the shared fakes."""
    if NEBULAE not in sys.path:
        sys.path.insert(0, NEBULAE)

    ctcsound = types.ModuleType("ctcsound")
    ctcsound.CSOUND_CONTROL_CHANNEL = 1
    ctcsound.CSOUND_INPUT_CHANNEL = 16
    ctcsound.CSOUND_OUTPUT_CHANNEL = 32
    sys.modules["ctcsound"] = ctcsound

    fileloader = types.ModuleType("fileloader")
    fileloader.FileLoader = FakeUsb
    sys.modules["fileloader"] = fileloader

    import nebio
    import neb_globals
    neb_globals.remount_fs = False
    clock = FakeClock()
    clib = FakeCLib()
    nebio._lib = clib
    nebio.time = clock
    return clock, clib


class FakeCsound(object):
    """channelPtr() memory, setControlChannel() calls and function tables."""

    def __init__(self):
        self.chans = {}
        self.calls = []
        self.tables = {}

    def table(self, number):
        import numpy as np
        self.calls.append("table(%d)" % number)
        return self.tables.get(number, np.zeros(0))

    def channelPtr(self, name, flags):
        import ctypes
        self.calls.append("channelPtr(%s,%d)" % (name, flags))
        if name not in self.chans:
            self.chans[name] = (ctypes.c_double * 1)()  # Csound's MYFLT memory
        return self.chans[name], None

    def setControlChannel(self, name, value):
        self.calls.append("setControlChannel(%s,%s)" % (name, fmt(value)))
        self.channelPtr(name, 0)
        self.calls.pop()
        self.chans[name][0] = value


class FakeUsb(object):
    """fileloader.FileLoader for WaveWriter: mount state and a call log."""
    mounted = True
    calls = []

    def mount(self):
        FakeUsb.calls.append("mount")

    def umount(self):
        FakeUsb.calls.append("umount")

    def isUSBMounted(self):
        return FakeUsb.mounted


def tokens(line):
    """Whitespace separated; "\\_" is a space inside a token."""
    return [t.replace("\\_", " ") for t in line.split()]


def number(text):
    """A scenario number: int if it has no '.', 'e', 'inf' or 'nan'."""
    low = text.lower()
    if any(c in low for c in ".e") or "inf" in low or "nan" in low:
        return float(text)
    return int(text)


class FatalStop(BaseException):
    """fatal._exit() in the tests: past every "except Exception"."""
