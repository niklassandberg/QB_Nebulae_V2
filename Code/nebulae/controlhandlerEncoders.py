import digitaldata
import encoderpages
import shiftregister as libSR
from controlhandler import ControlHandler, DIGITAL_CONTROLS

ENCODERS = ("speed", "pitch")
CV_ASSIGN_BUTTONS = ("file", "reset")
HOLD_PINS = {"record": libSR.PIN_RECORD, "file": libSR.PIN_NEXT, "reset": libSR.PIN_RESET,
             "freeze": libSR.PIN_FREEZE, "source": libSR.PIN_SOURCE}
# A hold: button reacts on release, so a hold is no press.
HOLD_EDGE_MODES = ("latching", "triggered", "incremental")

# Base for the SuperCollider and programs banks: encoder sources, button
# modes and encoder pages per instrument.
class EncoderControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(EncoderControlHandler, self).__init__(*args, **kwargs)
        # encoders[name][source]. A paged encoder keeps its hybrid channel for the CV.
        self.encoders = dict()
        for name in ENCODERS:
            self.encoders[name] = {"hybrid": self.channeldict[name]}
        self.pages = {}
        self.holds = {}            # button -> {encoder: EncoderPages}
        self.hold_since = {}       # button -> ms it went down, while down
        self.hold_active = None    # the button whose layer the encoders show
        self.hold_used = False     # an encoder changed the layer: no press
        self.pageState = None
        self.page_sent = {}
        self.cv_assign = False

    def setConfig(self, config, pages_path):  # nebconfig.NebConfig
        for name in ENCODERS:
            source = config.encoderType(name)
            if source not in self.encoders[name] and source != "pages":
                self.classlog.error("%s,%s: not in this bank, hybrid", name, source)
                source = "hybrid"
            new = self.encoders[name]["hybrid" if source == "pages" else source]
            old = self.channeldict[name]
            if new is not old:
                # Same index: resistNormalSettings() pairs channels[i] with altchannels[i].
                self.channels[self.channels.index(old)] = new
                self.channeldict[name] = new
            self.classlog.info("%s: %s", name, source)
        self.setPages(config, pages_path)
        self.setButtonConfig(config)

    def setButtonConfig(self, nebConfig):
        output_period = nebConfig.outputPeriod()
        for ctrl in DIGITAL_CONTROLS:
            chn = self.channeldict.get(ctrl) or self.altchanneldict.get(ctrl)
            config = nebConfig.entry(ctrl) or self.defaultConfig.get(ctrl)
            if chn is None or config is None or len(config) < 2:
                continue
            edge = config[1]
            if ctrl in self.holds:
                if config[0] in HOLD_EDGE_MODES:
                    edge = "falling"
                else:
                    self.classlog.warning("%s,%s: also on while held for its hold: layer", ctrl, config[0])
            chn.setMode(config[0], edge)
            if config[0] == "triggered":
                chn.setOutputPeriod(output_period)
            else:
                chn.setOutputPeriod(digitaldata.DEFAULT_OUTPUT_PERIOD)

    def setPages(self, config, pages_path):
        self.savePages()  # the previous instrument's
        entries, errors = config.encoderPages()
        for error in errors:
            self.classlog.error("nebconfig: %s", error)
        targets = config.cvTargets()
        self.pages = {}
        for name, pages in entries.items():
            if config.encoderType(name) == "pages":
                self.pages[name] = encoderpages.EncoderPages(
                    name, [encoderpages.Page(*p) for p in pages], targets.get(name))
        holds, errors = config.holdPages()
        for error in errors:
            self.classlog.error("nebconfig: %s", error)
        self.holds = {}
        for button, encoders in holds.items():
            self.holds[button] = {
                name: encoderpages.EncoderPages(name, [encoderpages.Page(*p) for p in pages], None, hold=True)
                for name, pages in encoders.items()}
        self.hold_since = {}
        self.hold_active = None
        self.hold_used = False
        self.pageState = encoderpages.PageState(pages_path)
        self.pageState.load(self.allPages())
        self.page_sent = {}
        self.cv_assign = False

    # Saved and sent: the encoder pages, and the hold layers as "<button>:<encoder>".
    def allPages(self):
        out = dict(self.pages)
        for button, encoders in self.holds.items():
            for name, pages in encoders.items():
                out["%s:%s" % (button, name)] = pages
        return out

    def saveInstrument(self):
        super(EncoderControlHandler, self).saveInstrument()
        self.savePages()

    def savePages(self):
        if self.pageState is not None and self.pageState.dirty_time is not None:
            self.pageState.save(self.allPages())

    # What the encoder turns now: the held button's layer, else its pages.
    def encoderPages(self, encoder):
        if self.hold_active is not None:
            layer = self.holds[self.hold_active].get(encoder)
            if layer is not None:
                return layer
        return self.pages.get(encoder)

    def pageStep(self, encoder, steps):
        self.touchedPages(encoder).step(steps)
        self.pageState.changed(self.now)

    def pageJump(self, encoder, steps):
        self.touchedPages(encoder).move(encoderpages.PAGE_JUMP * steps)
        self.pageState.changed(self.now)

    def nextPage(self, encoder):
        self.touchedPages(encoder).nextPage()

    def touchedPages(self, encoder):
        pages = self.encoderPages(encoder)
        if pages.hold:
            self.hold_used = True
        return pages

    def stepCvTarget(self, encoder, steps):
        self.pages[encoder].stepCandidate(steps)

    def cvAssignActive(self):
        return self.cv_assign

    # The buttons get 0 once so a gate on them closes; their release is no press.
    def updateCvAssign(self):
        held_next = self.shiftReg.state(libSR.PIN_NEXT)
        held_reset = self.shiftReg.state(libSR.PIN_RESET)
        if held_next and held_reset and not self.cv_assign and self.pages:
            self.cv_assign = True
            self.hold_active = None
            for pages in self.pages.values():
                pages.startChoosing()
            for name in CV_ASSIGN_BUTTONS:
                self.channeldict[name].setIgnoreNextButton()
                self.sendControl(name, 0)
        elif self.cv_assign and not held_next and not held_reset:
            self.cv_assign = False
            changed = False
            for pages in self.pages.values():
                changed = pages.commitCandidate() or changed
            if changed:
                self.pageState.changed(self.now)
                self.classlog.info("CV targets: %s", ", ".join(
                    "%s -> %s" % (e, p.cv_target or "none") for e, p in self.pages.items()))

    # While the button is down the encoders show and change its layer. Its
    # release is a press only when short (HOLD_MS) and no encoder was used.
    # Runs before the channels read the button, so that release is dropped.
    # Not while choosing CV targets (file + reset).
    def updateHolds(self):
        for button in self.holds:
            if self.shiftReg.state(HOLD_PINS[button]):
                if button not in self.hold_since:
                    self.hold_since[button] = self.now
                    if self.hold_active is None and not self.cv_assign:
                        self.hold_active = button
                        self.hold_used = False
                continue
            since = self.hold_since.pop(button, None)
            if self.hold_active == button:
                self.hold_active = None
                held = since is None or self.now - since >= encoderpages.HOLD_MS
                if self.hold_used or held:
                    self.channeldict[button].setIgnoreNextButton()
                    self.classlog.info("hold %s: %s", button, ", ".join(
                        "%s %s" % (e, p.page().name) for e, p in self.holds[button].items()))

    def sendsControl(self, name):
        if name in self.pages:
            return False
        return not (self.cv_assign and name in CV_ASSIGN_BUTTONS)

    # hybrid = encoder + CV
    def encoderCV(self, encoder):
        chn = self.channeldict[encoder]
        return chn.getValue() - chn.getStaticVal()

    def sendPages(self, full=False):
        sent = self.page_sent
        for key, pages in self.allPages().items():
            cv = 0.0 if pages.hold else self.encoderCV(key)
            for path, out in pages.outputs(cv):
                if full or sent.get(path) != out:
                    self.sendPath(path, out)
                    sent[path] = out
        if self.pageState is not None:
            self.pageState.saveIfDue(self.now, self.allPages())

    def sendControl(self, name, value):
        raise NotImplementedError

    def sendPath(self, path, value):
        raise NotImplementedError
