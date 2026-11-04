# Encoder pages of the programs bank (a .prog's "page:" and "cv:" lines,
# nebconfig.py), as chompi.scd does it for the SuperCollider bank:
#   - turning speed or pitch changes the value of the page shown,
#   - a click shows the next page,
#   - the encoder's two LEDs show the page (colour) and its value (crossfade),
#   - the encoder's CV input (speed CV, pitch CV) is added to one page, its CV
#     target; holding file + reset and turning the encoder chooses it.
# Values and CV targets are saved per program, 1 s after the last change
# (as NebInterface settings are for a .scd), and back at the next load.
import math
import os

from classlogger import ClassLogger

STATE_DIR = "/home/alarm/QB_Nebulae_V2/Code/config/prog/"
PAGE_STEP = 0.01      # per encoder step (chompi.scd: 0.02 over a smaller range)
SAVE_DELAY_MS = 1000  # after the last change

# LED colours per page index, (neg, pos) as r, g, b 0..4095; at the minimum
# only the left LED (neg) glows, at the maximum only the right one (pos).
PAGE_COLOURS = [
    ((4095, 4095, 4095), (4095, 4095, 4095)),  # 1 white
    ((0, 2600, 4095), (0, 0, 4095)),           # 2 cyan -> blue
    ((4095, 3000, 0), (4095, 0, 0)),           # 3 yellow -> red
    ((0, 4095, 1500), (0, 4095, 0)),           # 4 mint -> green
    ((3037, 200, 3825), (4095, 0, 2000)),      # 5 pink -> magenta
]
LED_BRIGHT = 0.4  # as chompi.scd


def scale(value, lo, hi, curve):
    """0..1 to lo..hi: lin, exp (lo, hi > 0) or int (rounded)."""
    v = min(1.0, max(0.0, float(value)))
    if curve == "exp":
        return lo * math.pow(hi / lo, v)
    out = lo + (hi - lo) * v
    if curve == "int":
        return float(round(out))
    return out


class Page(object):
    def __init__(self, name, path, lo, hi, curve, default):
        self.name = name
        self.path = path
        self.lo = lo
        self.hi = hi
        self.curve = curve
        self.value = default  # 0..1, what the encoder sets


class EncoderPages(object):
    def __init__(self, encoder, pages, cv_target):
        self.encoder = encoder
        self.pages = pages
        self.current = 0  # the page always starts at page 1
        self.cv_target = cv_target if cv_target in self.names() else None
        self.candidate = None  # CV target being chosen (hold file + reset)

    def names(self):
        return [p.name for p in self.pages]

    def page(self):
        return self.pages[self.current]

    def step(self, steps):
        p = self.page()
        p.value = min(1.0, max(0.0, round(p.value + steps * PAGE_STEP, 4)))

    def nextPage(self):
        self.current = (self.current + 1) % len(self.pages)

    # The CV target choices: every page, then none.
    def startChoosing(self):
        self.candidate = self.cv_target

    def stepCandidate(self, steps):
        choices = self.names() + [None]
        i = choices.index(self.candidate) if self.candidate in choices else len(choices) - 1
        self.candidate = choices[(i + (1 if steps > 0 else -1)) % len(choices)]

    def commitCandidate(self):
        changed = self.candidate != self.cv_target
        self.cv_target = self.candidate
        return changed

    def outputs(self, cv):
        """[(path, value)] of every page; cv (the encoder's CV, in the
        same units as its 0..1 value) is added to the CV target's page."""
        out = []
        for p in self.pages:
            v = p.value + cv if p.name == self.cv_target else p.value
            out.append((p.path, scale(v, p.lo, p.hi, p.curve)))
        return out

    def colours(self, index):
        return PAGE_COLOURS[index % len(PAGE_COLOURS)]


class ProgState(object):
    """The saved page values and CV targets of one program, a text file of
    lines "value,<encoder>,<page>,<0..1>" and "cv,<encoder>,<page|none>"."""

    def __init__(self, prog_name):
        self.log = ClassLogger.loggerSetup(self)
        self.path = os.path.join(STATE_DIR, prog_name + ".txt")
        self.dirty_time = None

    def load(self, encoders):
        try:
            with open(self.path) as f:
                lines = f.read().splitlines()
        except OSError:
            return
        for line in lines:
            parts = line.strip().split(",")
            if len(parts) < 3 or parts[1] not in encoders:
                continue
            pages = encoders[parts[1]]
            if parts[0] == "value" and len(parts) == 4 and parts[2] in pages.names():
                try:
                    pages.pages[pages.names().index(parts[2])].value = min(1.0, max(0.0, float(parts[3])))
                except ValueError:
                    pass
            elif parts[0] == "cv":
                target = None if parts[2] == "none" else parts[2]
                if target is None or target in pages.names():
                    pages.cv_target = target

    def changed(self, now):
        self.dirty_time = now

    # Writes 1 s after the last change.
    def saveIfDue(self, now, encoders):
        if self.dirty_time is None or now - self.dirty_time < SAVE_DELAY_MS:
            return
        self.dirty_time = None
        self.save(encoders)

    def save(self, encoders):
        lines = []
        for name, pages in encoders.items():
            for p in pages.pages:
                lines.append("value,%s,%s,%s" % (name, p.name, repr(round(p.value, 4))))
            lines.append("cv,%s,%s" % (name, pages.cv_target or "none"))
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                f.write("\n".join(lines) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except OSError as e:
            self.log.error("Could not save %s: %s", self.path, e)
