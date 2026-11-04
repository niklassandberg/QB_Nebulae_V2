# Encoder pages: several values on the speed or pitch encoder, declared by
# "page:" and "cv:" lines in the nebconfig block. Saved in <name>.pages.
import math
import os

from classlogger import ClassLogger

PAGES_EXT = ".pages"
PAGE_STEP = 0.01
PAGE_JUMP = 0.2
PAGE_JUMP_DELAY_MS = 125
SAVE_DELAY_MS = 1000

# Page 1 has no colour, like the plain encoder.
PAGE_COLOURS = [
    (4095, 4095, 4095),
    (4095, 0, 0),        # red
    (0, 600, 4095),      # blue
    (0, 4095, 300),      # green
    (4095, 0, 2600),     # pink
]
PAGE_DIM = (0.0, 0.01)
PAGE_PULSE_MS = 88
CHOOSE_BRIGHT = 0.4


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
        self.value = default  # 0..1
        self.step = step


class EncoderPages(object):
    def __init__(self, encoder, pages, cv_target):
        self.encoder = encoder
        self.pages = pages
        self.current = 0
        self.cv_target = cv_target if cv_target in self.names() else None
        self.candidate = None  # CV target while choosing

    def names(self):
        return [p.name for p in self.pages]

    def page(self):
        return self.pages[self.current]

    def step(self, steps):
        self.move(steps * self.page().step)

    def move(self, amount):
        p = self.page()
        p.value = min(1.0, max(0.0, round(p.value + amount, 6)))

    def nextPage(self):
        self.current = (self.current + 1) % len(self.pages)

    def startChoosing(self):
        self.candidate = self.cv_target

    # Cycles through every page, then none.
    def stepCandidate(self, steps):
        choices = self.names() + [None]
        i = choices.index(self.candidate) if self.candidate in choices else len(choices) - 1
        self.candidate = choices[(i + (1 if steps > 0 else -1)) % len(choices)]

    def commitCandidate(self):
        changed = self.candidate != self.cv_target
        self.cv_target = self.candidate
        return changed

    def withCV(self, page, cv):
        v = page.value + cv if page.name == self.cv_target else page.value
        return min(1.0, max(0.0, v))

    def outputs(self, cv):
        return [(p.path, scale(self.withCV(p, cv), p.lo, p.hi, p.curve)) for p in self.pages]

    def colour(self, index):
        return PAGE_COLOURS[index % len(PAGE_COLOURS)]


def pulse(now_ms):
    low, high = PAGE_DIM
    phase = (now_ms % PAGE_PULSE_MS) / float(PAGE_PULSE_MS)
    return low + (high - low) * 0.5 * (1.0 - math.cos(2.0 * math.pi * phase))


class PageState(object):
    """Lines "value,<encoder>,<page>,<0..1>" and "cv,<encoder>,<page|none>"."""

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
