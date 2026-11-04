# An instrument's own settings (the nebconfig block), for every bank.
# The one reader of instrument files: Csound (.instr), SuperCollider (.scd),
# Pure Data (.pd) instruments and programs (.prog) are read here, with the
# same rules, and the instrument folders are named here only.
# (The device's settings are another thing: configsettings.py.)
#
# One entry per line, "key,value[,value...]":
#   ksmps,64                 Csound block size (conductor.py)
#   -B,2048  -b,512  sr,48000
#   freeze,latching,rising   button mode and edge (controlhandler*.py)
#   speed,rawencoder         .scd: the patch reads the encoder itself
#   kernel,rt                rt | normal | any, default normal (kernelswitch.py)
#   blocksize,256            .scd/.pd: JACK period (jack@.service), default 128
#   -n,3                     .scd/.pd: JACK periods in the buffer (jackd -n), default 3
#   -r,48000                 .scd/.pd: JACK sample rate (jackd -r), default 48000,
#                            snapped to the nearest rate the card runs
#                            (.prog: all four JACK/kernel keys as .scd/.pd)
#   run,miRings              .prog: the program to start, a binary or a script
#                            (.sh with sh, .py with python3); a bare name is
#                            looked up in /home/alarm/prog/, then Code/bin/
#   oscport,3020             .prog: the UDP port the program listens on
#   osc:blend,/rings/structure,0,1[,lin|exp|int]
#                            .prog: control "blend" (0..1) is sent to that
#                            OSC path as a float, scaled to min..max (exp:
#                            min and max > 0; int: rounded). One line per
#                            control; no comments after an entry.
#   page:pitch:note,/audrey/note,16,76[,curve[,default]]
#                            .prog: a page of the pitch (or speed) encoder,
#                            as chompi.scd: a click shows the next page,
#                            turning sets its value (0..1, default 0), sent
#                            scaled like osc:. Pages in the order written.
#                            An encoder with pages is not sent as a control.
#   cv:pitch,note            .prog: the page the encoder's CV input is added
#                            to at first (or none); hold file + reset and
#                            turn the encoder to choose another (progpages.py)
#
# Where the entries are:
#   .instr  nebconfigbegin              .scd  /*
#   .prog   ksmps,64                          nebconfigbegin
#           nebconfigend                      speed,rawencoder
#                                             nebconfigend
#                                             */   (sclang never sees it)
#   .pd     one comment box per entry, starting with "nebconfig":
#           nebconfig kernel,rt
#           (Pd saves the comma as "\," and may add the box width
#           ", f 20": both are undone here, so the entry is the same.)
# A key given twice: the last one counts. Blank lines are skipped.

import io
import os
import re

INSTR_DIRS = {"instr": ("/home/alarm/instr/", ".instr"),
              "supercollider": ("/home/alarm/sc/", ".scd"),
              "puredata": ("/home/alarm/pd/", ".pd"),
              "programs": ("/home/alarm/prog/", ".prog")}

# Programs that ship with the firmware (.prog "run," with a bare name, when
# /home/alarm/prog/ has no file of that name).
PROGRAM_BIN_DIR = "/home/alarm/QB_Nebulae_V2/Code/bin/"
DEFAULT_OSC_PORT = 3020
OSC_CURVES = ("lin", "exp", "int")

KERNELS = ("rt", "normal", "any")

# JACK periods an instrument may ask for (frames; at 48 kHz with 3 periods
# 128 is ~8 ms, 256 ~16 ms). Csound does not use JACK: it has ksmps/-b/-B.
BLOCK_SIZES = (32, 64, 128, 256, 512, 1024)
DEFAULT_BLOCK_SIZE = 128
# JACK periods in the sound card's buffer (jackd -n): 3 leaves one spare
# block for a late one (experimental Pd/SC code); 2 = lower latency, less
# margin; 4 = more margin for heavy patches.
NPERIODS = (2, 3, 4)
DEFAULT_NPERIODS = 3
# JACK sample rate (jackd -r) without an entry. nebulae.py snaps a wished
# rate to the nearest one the card really runs (jackRates()).
DEFAULT_SAMPLE_RATE = 48000

# a Pd statement: "#X text X Y nebconfig ..." up to its unescaped ";"
PD_STATEMENT = re.compile(r"(?<!\\);[ \t]*\r?\n")
PD_NEBCONFIG = re.compile(r"^#X text -?\d+ -?\d+ nebconfig\s+(.*?);?$", re.S)
PD_WIDTH = re.compile(r",f \d+$")


def instrumentDir(bank):
    """Folder of a bank (instr, supercollider, puredata); an unknown bank is
    the Csound folder."""
    return INSTR_DIRS.get(bank, INSTR_DIRS["instr"])[0]


def instrumentPath(bank, instr):
    folder, ext = INSTR_DIRS.get(bank, INSTR_DIRS["instr"])
    return folder + instr + ext


class NebConfig(object):
    def __init__(self, entries, body=""):
        self._dict = dict()
        for line in entries:
            line = line.rstrip()
            if not line:
                continue
            values = line.split(",")
            self._dict[values.pop(0)] = values
        self.body = body  # the file without the nebconfig block (the Csound orchestra)

    @classmethod
    def read(cls, bank, instr):
        """The instrument's settings, read once per load (nebulae.py passes
        the object on). OSError when the file cannot be read."""
        return cls.readFile(instrumentPath(bank, instr))

    @classmethod
    def readFile(cls, path):
        """As read(), for a file anywhere (e.g. a .prog on the USB stick)."""
        with open(path, "r") as f:
            text = f.read()
        if path.endswith(".pd"):
            return cls(_pdEntries(text), text)
        entries, body = _blockEntries(text)
        return cls(entries, body)

    def entry(self, name):
        """The values of a key, e.g. ["latching", "rising"], or None."""
        return self._dict.get(name)

    def value(self, name, default=None):
        """The first value of a key, or default."""
        values = self._dict.get(name)
        return values[0] if values else default

    def asDict(self):
        """All entries {key: [values]}, for ControlHandler / SettingManager.
        The object itself, not a copy: nebulae.py adds output_period to it."""
        return self._dict

    def encoderType(self, name):
        """speed/pitch: "rawencoder" if the instrument declares it, else "hybrid"."""
        value = self.value(name)
        if value and value.strip().lower() == "rawencoder":
            return "rawencoder"
        return "hybrid"

    def outputPeriod(self):
        ksmps = int(self.value("ksmps", "128"))
        sr = int(self.value("sr", "48000"))
        block_ms = (ksmps / float(sr)) * 1000.0
        return max(100.0, block_ms * 75)

    def holdWithTriggCombos(self):
        # Parsed on feature_userDefinedSupercollider (80bc280) only; on this
        # branch always empty.
        return []

    def kernel(self):
        """rt | normal | any; normal without an entry. An unknown value is
        returned as it is (the caller says so and treats it as normal)."""
        value = self.value("kernel")
        return value.strip().lower() if value else "normal"

    def blockSize(self):
        """The JACK period, DEFAULT_BLOCK_SIZE without an entry. ValueError
        for a value not in BLOCK_SIZES (the caller says so and uses the
        default)."""
        return self._choice("blocksize", BLOCK_SIZES, DEFAULT_BLOCK_SIZE)

    def nPeriods(self):
        """JACK periods in the buffer ("-n,3", as jackd -n),
        DEFAULT_NPERIODS without an entry. ValueError as blockSize()."""
        return self._choice("-n", NPERIODS, DEFAULT_NPERIODS)

    def sampleRate(self):
        """The wished JACK sample rate ("-r,48000", as jackd -r),
        DEFAULT_SAMPLE_RATE without an entry; not checked against the card
        (nebulae.py snaps it). ValueError for no positive number."""
        value = self.value("-r")
        if value is None:
            return DEFAULT_SAMPLE_RATE
        try:
            rate = int(value.strip())
        except ValueError:
            rate = 0
        if rate <= 0:
            raise ValueError("-r %r: a sample rate in Hz, e.g. 48000" % value)
        return rate

    def run(self):
        """.prog: the program's path, or None without a run entry. A bare
        name: /home/alarm/prog/<name> if it exists, else Code/bin/<name>."""
        value = self.value("run")
        if not value or not value.strip():
            return None
        value = value.strip()
        if os.path.isabs(value):
            return value
        local = os.path.join(INSTR_DIRS["programs"][0], value)
        if os.path.exists(local):
            return local
        return os.path.join(PROGRAM_BIN_DIR, value)

    def oscPort(self):
        """.prog: the program's OSC port, DEFAULT_OSC_PORT without an entry.
        ValueError for no port number."""
        value = self.value("oscport")
        if value is None:
            return DEFAULT_OSC_PORT
        try:
            port = int(value.strip())
        except ValueError:
            port = 0
        if not 1024 <= port <= 65535:
            raise ValueError("oscport %r: a UDP port, 1024..65535" % value)
        return port

    def oscBindings(self):
        """.prog: [(control, path, min, max, curve)] from the osc:<control>
        lines. A line that cannot be read is skipped and listed in the
        second value: (bindings, [error text, ...])."""
        bindings, errors = [], []
        for key, values in self._dict.items():
            if not key.startswith("osc:"):
                continue
            control = key[4:].strip()
            values = [v.strip() for v in values]
            try:
                if not control or len(values) < 3 or not values[0].startswith("/"):
                    raise ValueError("osc:<control>,<path>,<min>,<max>[,curve]")
                lo, hi = float(values[1]), float(values[2])
                curve = values[3].lower() if len(values) > 3 and values[3] else "lin"
                if curve not in OSC_CURVES:
                    raise ValueError("curve one of %s" % (OSC_CURVES,))
                if curve == "exp" and (lo <= 0 or hi <= 0):
                    raise ValueError("exp needs min and max > 0")
                bindings.append((control, values[0], lo, hi, curve))
            except ValueError as e:
                errors.append("%s,%s: %s" % (key, ",".join(values), e))
        return bindings, errors

    def encoderPages(self):
        """.prog: {encoder: [(name, path, min, max, curve, default)]} from
        the page:<encoder>:<name> lines, in the order written, and a list of
        error texts for lines that cannot be read."""
        pages, errors = {}, []
        for key, values in self._dict.items():
            if not key.startswith("page:"):
                continue
            values = [v.strip() for v in values]
            try:
                parts = key.split(":")
                if len(parts) != 3 or parts[1] not in ("speed", "pitch") or not parts[2]:
                    raise ValueError("page:<speed|pitch>:<name>,<path>,<min>,<max>[,curve[,default]]")
                if len(values) < 3 or not values[0].startswith("/"):
                    raise ValueError("page:<speed|pitch>:<name>,<path>,<min>,<max>[,curve[,default]]")
                lo, hi = float(values[1]), float(values[2])
                curve = values[3].lower() if len(values) > 3 and values[3] else "lin"
                if curve not in OSC_CURVES:
                    raise ValueError("curve one of %s" % (OSC_CURVES,))
                if curve == "exp" and (lo <= 0 or hi <= 0):
                    raise ValueError("exp needs min and max > 0")
                default = float(values[4]) if len(values) > 4 and values[4] else 0.0
                pages.setdefault(parts[1], []).append(
                    (parts[2], values[0], lo, hi, curve, min(1.0, max(0.0, default))))
            except ValueError as e:
                errors.append("%s,%s: %s" % (key, ",".join(values), e))
        return pages, errors

    def cvTargets(self):
        """.prog: {encoder: page name or None} from the cv:<encoder> lines."""
        targets = {}
        for encoder in ("speed", "pitch"):
            value = self.value("cv:" + encoder)
            if value is not None:
                value = value.strip()
                targets[encoder] = None if value in ("", "none") else value
        return targets

    def _choice(self, key, choices, default):
        value = self.value(key)
        if value is None:
            return default
        try:
            number = int(value.strip())
        except ValueError:
            number = None
        if number not in choices:
            raise ValueError("%s %r: one of %s" % (key, value, choices))
        return number


def _blockEntries(text):
    """.instr/.scd: (lines inside nebconfigbegin..nebconfigend, the rest)."""
    inside = False
    entries = []
    body = []
    for line in io.StringIO(text):  # lines as reading the file gives them
        if line.startswith("nebconfigbegin"):
            inside = True
        if inside:
            if line.startswith("nebconfigend"):
                inside = False
            elif not line.startswith("nebconfigbegin"):
                entries.append(line)
        else:
            body.append(line)
    return entries, "".join(body)


def _pdEntries(text):
    """.pd: the comment boxes that start with "nebconfig", as key,value lines."""
    entries = []
    for statement in PD_STATEMENT.split(text):
        m = PD_NEBCONFIG.match(" ".join(statement.split()))
        if not m:
            continue
        entry = m.group(1).replace("\\,", ",").replace("\\;", ";").replace("\\$", "$")
        entry = re.sub(r"\s*,\s*", ",", entry.strip())
        entries.append(PD_WIDTH.sub("", entry))
    return entries
