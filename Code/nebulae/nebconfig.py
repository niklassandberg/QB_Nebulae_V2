# The nebconfig block of an instrument, one "key,value[,value...]" per line:
#   ksmps,64  -B,2048  -b,512  sr,48000      Csound
#   freeze,latching,rising                   button mode and edge
#   speed,rawencoder                         .scd: sclang reads the encoder
#   kernel,rt                                rt | normal | any
#   blocksize,256  -n,3  -r,48000            .scd/.pd/.prog: JACK
#   run,miRings                              .prog: binary or .sh/.py script
#   oscport,3020                             .prog
#   osc:blend,/rings/structure,0,1[,lin|exp|int]
#   speedleds,playback                       .prog: osc:speed is a playback speed, shown on the LEDs
#   speed,pages                              .scd/.prog (implied by page: lines)
#   page:pitch:note,/audrey/note,16,76[,curve[,default[,step]]]
#   cv:pitch,note                            .scd/.prog: page the CV goes to, or none
#   hold:record:speed:echo_cutoff,/audrey/echo_cutoff,100,8000[,curve[,default[,step]]]
#                                            .scd/.prog: the encoder while the button is held
#   hold:record+file:pitch:echo_volume,...   while file is held during the record hold
# Details: Programs/README.md.
#
# Where the entries are:
#   .instr  nebconfigbegin              .scd  /*
#   .prog   ksmps,64                          nebconfigbegin
#           nebconfigend                      speed,rawencoder
#                                             nebconfigend
#                                             */   (sclang never sees it)
#   .pd     one comment box per entry, starting with "nebconfig":
#           nebconfig kernel,rt
# A key given twice: the last one counts. A line starting with # is a comment
# (a whole line only, not after an entry).

import io
import os
import re

import textfile

INSTR_DIRS = {"instr": ("/home/alarm/instr/", ".instr"),
              "supercollider": ("/home/alarm/sc/", ".scd"),
              "puredata": ("/home/alarm/pd/", ".pd"),
              "programs": ("/home/alarm/prog/", ".prog")}

DEFAULT_OSC_PORT = 3020
OSC_CURVES = ("lin", "exp", "int")
PAGE_STEP = 0.01
PAGE_FIELDS = "<path>,<min>,<max>[,curve[,default[,step]]]"
ENCODERS = ("speed", "pitch")
# Buttons on the shift register (controlhandlerEncoders.HOLD_PINS).
HOLD_BUTTONS = ("record", "file", "reset", "freeze", "source")

KERNELS = ("rt", "normal", "any")

BLOCK_SIZES = (32, 64, 128, 256, 512, 1024)
DEFAULT_BLOCK_SIZE = 128
NPERIODS = (2, 3, 4)
DEFAULT_NPERIODS = 3
DEFAULT_SAMPLE_RATE = 48000

PD_STATEMENT = re.compile(r"(?<!\\);[ \t]*\r?\n")
PD_NEBCONFIG = re.compile(r"^#X text -?\d+ -?\d+ nebconfig\s+(.*?);?$", re.S)
PD_WIDTH = re.compile(r",f \d+$")


def instrumentDir(bank):
    return INSTR_DIRS.get(bank, INSTR_DIRS["instr"])[0]


def instrumentPath(bank, instr):
    folder, ext = INSTR_DIRS.get(bank, INSTR_DIRS["instr"])
    return folder + instr + ext


class NebConfig(object):
    def __init__(self, entries, body=""):
        self._dict = dict()
        for line in entries:
            line = line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            values = line.split(",")
            self._dict[values.pop(0)] = values
        self.body = body  # the file without the block

    @classmethod
    def read(cls, bank, instr):
        return cls.readFile(instrumentPath(bank, instr))

    @classmethod
    def readFile(cls, path):
        text = textfile.read(path)
        if path.endswith(".pd"):
            return cls(_pdEntries(text), text)
        entries, body = _blockEntries(text)
        return cls(entries, body)

    def entry(self, name):
        return self._dict.get(name)

    def value(self, name, default=None):
        values = self._dict.get(name)
        return values[0] if values else default

    def asDict(self):
        return self._dict

    def encoderType(self, name):
        value = self.value(name)
        value = value.strip().lower() if value else ""
        if value in ("rawencoder", "pages"):
            return value
        prefix = "page:%s:" % name
        if any(key.startswith(prefix) for key in self._dict):
            return "pages"
        return "hybrid"

    # "playback": the speed control's osc: value is a playback speed (1 =
    # normal, negative = backward), shown on the speed LEDs as the granular
    # looper shows its speed.
    def speedLeds(self):
        value = (self.value("speedleds") or "").strip().lower()
        return value if value == "playback" else None

    def outputPeriod(self):
        ksmps = int(self.value("ksmps", "128"))
        sr = int(self.value("sr", "48000"))
        block_ms = (ksmps / float(sr)) * 1000.0
        return max(100.0, block_ms * 75)

    def holdWithTriggCombos(self):
        return []

    def kernel(self):
        value = self.value("kernel")
        return value.strip().lower() if value else "normal"

    def blockSize(self):
        return self._choice("blocksize", BLOCK_SIZES, DEFAULT_BLOCK_SIZE)

    def nPeriods(self):
        return self._choice("-n", NPERIODS, DEFAULT_NPERIODS)

    def sampleRate(self):
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
        value = self.value("run")
        if not value or not value.strip():
            return None
        value = value.strip()
        if os.path.isabs(value):
            return value
        return os.path.join(INSTR_DIRS["programs"][0], value)

    def oscPort(self):
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

    # ([(control, path, min, max, curve)], [error, ...])
    def oscBindings(self):
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

    # ({encoder: [(name, path, min, max, curve, default, step)]}, [error, ...])
    def encoderPages(self):
        pages, errors = {}, []
        usage = "page:<speed|pitch>:<name>," + PAGE_FIELDS
        for key, values in self._dict.items():
            if not key.startswith("page:"):
                continue
            values = [v.strip() for v in values]
            try:
                parts = key.split(":")
                if len(parts) != 3 or parts[1] not in ENCODERS or not parts[2]:
                    raise ValueError(usage)
                pages.setdefault(parts[1], []).append((parts[2],) + _pageFields(values, usage))
            except ValueError as e:
                errors.append("%s,%s: %s" % (key, ",".join(values), e))
        return pages, errors

    # The encoders while a button is held ("record"), or while a second one is
    # pressed during that hold ("record+file"): as encoderPages, by layer.
    # ({layer: {encoder: [(name, path, min, max, curve, default, step)]}}, [error, ...])
    def holdPages(self):
        holds, errors = {}, []
        usage = "hold:<%s>[+<button>]:<speed|pitch>:<name>,%s" % ("|".join(HOLD_BUTTONS), PAGE_FIELDS)
        for key, values in self._dict.items():
            if not key.startswith("hold:"):
                continue
            values = [v.strip() for v in values]
            try:
                parts = key.split(":")
                if len(parts) != 4 or parts[2] not in ENCODERS or not parts[3]:
                    raise ValueError(usage)
                buttons = parts[1].split("+")
                if len(buttons) > 2 or len(set(buttons)) != len(buttons) \
                        or any(b not in HOLD_BUTTONS for b in buttons):
                    raise ValueError(usage)
                holds.setdefault(parts[1], {}).setdefault(parts[2], []).append(
                    (parts[3],) + _pageFields(values, usage))
            except ValueError as e:
                errors.append("%s,%s: %s" % (key, ",".join(values), e))
        return holds, errors

    def cvTargets(self):
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


# (path, min, max, curve, default, step) of a page: or hold: line.
def _pageFields(values, usage):
    if len(values) < 3 or not values[0].startswith("/"):
        raise ValueError(usage)
    lo, hi = float(values[1]), float(values[2])
    curve = values[3].lower() if len(values) > 3 and values[3] else "lin"
    if curve not in OSC_CURVES:
        raise ValueError("curve one of %s" % (OSC_CURVES,))
    if curve == "exp" and (lo <= 0 or hi <= 0):
        raise ValueError("exp needs min and max > 0")
    default = float(values[4]) if len(values) > 4 and values[4] else 0.0
    step = float(values[5]) if len(values) > 5 and values[5] else PAGE_STEP
    if not 0.0 < step <= 1.0:
        raise ValueError("step: a part of the range per click, 0 < step <= 1")
    return (values[0], lo, hi, curve, min(1.0, max(0.0, default)), step)


def _blockEntries(text):
    inside = False
    entries = []
    body = []
    for line in io.StringIO(text):
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


# Undoes Pd's escaped commas and the ", f 20" box width.
def _pdEntries(text):
    entries = []
    for statement in PD_STATEMENT.split(text):
        m = PD_NEBCONFIG.match(" ".join(statement.split()))
        if not m:
            continue
        entry = m.group(1).replace("\\,", ",").replace("\\;", ";").replace("\\$", "$")
        entry = re.sub(r"\s*,\s*", ",", entry.strip())
        entries.append(PD_WIDTH.sub("", entry))
    return entries
