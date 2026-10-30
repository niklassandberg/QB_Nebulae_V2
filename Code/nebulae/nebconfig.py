# An instrument's own settings (the nebconfig block), for all three engines.
# The one reader of instrument files: Csound (.instr), SuperCollider (.scd)
# and Pure Data (.pd) instruments are read here, with the same rules, and
# the instrument folders are named here only.
# (The device's settings are another thing: configsettings.py.)
#
# One entry per line, "key,value[,value...]":
#   ksmps,64                 Csound block size (conductor.py)
#   -B,2048  -b,512  sr,48000
#   freeze,latching,rising   button mode and edge (controlhandler*.py)
#   speed,rawencoder         .scd: the patch reads the encoder itself
#   kernel,rt                rt | normal | any (kernelswitch.py)
#
# Where the entries are:
#   .instr  nebconfigbegin              .scd  /*
#           ksmps,64                          nebconfigbegin
#           nebconfigend                      speed,rawencoder
#                                             nebconfigend
#                                             */   (sclang never sees it)
#   .pd     one comment box per entry, starting with "nebconfig":
#           nebconfig kernel,rt
#           (Pd saves the comma as "\," and may add the box width
#           ", f 20": both are undone here, so the entry is the same.)
# A key given twice: the last one counts. Blank lines are skipped.

import io
import re

INSTR_DIRS = {"instr": ("/home/alarm/instr/", ".instr"),
              "supercollider": ("/home/alarm/sc/", ".scd"),
              "puredata": ("/home/alarm/pd/", ".pd")}

KERNELS = ("rt", "normal", "any")

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
        path = instrumentPath(bank, instr)
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
        """rt | normal | any; any without an entry. An unknown value is
        returned as it is (the caller says so and treats it as any)."""
        value = self.value("kernel")
        return value.strip().lower() if value else "any"


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
