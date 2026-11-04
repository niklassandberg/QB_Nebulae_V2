# Encoder pages: more values than knobs on the speed and pitch encoders, for
# any bank that uses them (controlhandlerEncoders.py: SuperCollider and
# programs). Declared in the instrument's nebconfig block ("page:" and "cv:"
# lines, nebconfig.py), as chompi.scd does it in sclang:
#   - turning speed or pitch changes the value of the page shown,
#   - a click shows the next page,
#   - the encoder's two LEDs show the value as pitch does (ui.py), and the
#     LED pitch leaves dark pulses dimly in the page's colour,
#   - the encoder's CV input (speed CV, pitch CV) is added to one page, its CV
#     target; holding file + reset, each click of the encoder chooses the next.
# Values and CV targets are saved per instrument, 1 s after the last change,
# and back at the next load: <name>.pages next to the .scd/.prog, out of the
# firmware folder (a firmware update keeps it, a USB load leaves it, a newer
# one on the stick replaces it: fileloader.py).
import math
import os

from classlogger import ClassLogger

PAGES_EXT = ".pages"
PAGE_STEP = 0.01      # per encoder click, of the range 0..1, without a step in the page: line
PAGE_JUMP = 0.2       # per click while the encoder is held, as pitch (an octave, a colour)
PAGE_JUMP_DELAY_MS = 125  # between two jumps, as pitch
SAVE_DELAY_MS = 1000  # after the last change

# The colour of each page (r, g, b 0..4095), by index, pulsing dimly on the
# LED that the value leaves dark. Page 1 has none: it looks like the plain
# encoder, also while choosing the CV target (LEDs off).
PAGE_COLOURS = [
    (4095, 4095, 4095),  # 1 none (not shown)
    (4095, 0, 0),        # 2 red
    (0, 600, 4095),      # 3 blue
    (0, 4095, 300),      # 4 green
    (4095, 0, 2600),     # 5 pink
]
PAGE_DIM = (0.0, 0.01)   # brightness of the page colour: pulses between these
PAGE_PULSE_MS = 88       # one pulse
CHOOSE_BRIGHT = 0.4      # choosing the CV target: the chosen page's colour, steady


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
    def __init__(self, name, path, lo, hi, curve, default, step=PAGE_STEP):
        self.name = name
        self.path = path
        self.lo = lo
        self.hi = hi
        self.curve = curve
        self.value = default  # 0..1, what the encoder sets
        self.step = step      # per encoder click, of 0..1 (smaller = finer)


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
        self.move(steps * self.page().step)

    # Moves the page shown by `amount` of its range (a jump: PAGE_JUMP).
    def move(self, amount):
        p = self.page()
        p.value = min(1.0, max(0.0, round(p.value + amount, 6)))

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

    # A page's value with the encoder's CV (cv, in the same units as the
    # 0..1 value) when it is the CV target: what is sent, 0..1.
    def withCV(self, page, cv):
        v = page.value + cv if page.name == self.cv_target else page.value
        return min(1.0, max(0.0, v))

    def outputs(self, cv):
        """[(path, value)] of every page, the CV target's with the CV."""
        return [(p.path, scale(self.withCV(p, cv), p.lo, p.hi, p.curve)) for p in self.pages]

    def colour(self, index):
        return PAGE_COLOURS[index % len(PAGE_COLOURS)]


def pulse(now_ms):
    """The page colour's brightness at this moment (a slow sine breath)."""
    low, high = PAGE_DIM
    phase = (now_ms % PAGE_PULSE_MS) / float(PAGE_PULSE_MS)
    return low + (high - low) * 0.5 * (1.0 - math.cos(2.0 * math.pi * phase))


class PageState(object):
    """The saved page values and CV targets of one instrument (path: its
    <name>.pages), a text file of lines "value,<encoder>,<page>,<0..1>" and
    "cv,<encoder>,<page|none>"."""

    def __init__(self, path):
        self.log = ClassLogger.loggerSetup(self)
        self.path = path
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
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                f.write("\n".join(lines) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except OSError as e:
            self.log.error("Could not save %s: %s", self.path, e)
