import digitaldata
import encoderpages
import shiftregister as libSR
from controlhandler import ControlHandler, DIGITAL_CONTROLS

# The encoders an instrument can give another source than hybrid in its
# nebconfig block: "speed,rawencoder" (SuperCollider only) or "speed,pages"
# (pages also when the block has page:speed:... lines).
ENCODERS = ("speed", "pitch")

# The buttons held together to choose where the speed/pitch CV goes.
CV_ASSIGN_BUTTONS = ("file", "reset")

# Base of the control handlers of the banks that send their controls to
# another program: SuperCollider (SCControlHandler) and programs
# (ProgControlHandler). For every instrument, setConfig() sets up its encoders
# (hybrid, rawencoder or pages), its button modes and its encoder pages
# (encoderpages.py). A subclass sends: sendControl() a control by name,
# sendPath() a page value to its OSC path.
class EncoderControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(EncoderControlHandler, self).__init__(*args, **kwargs)
        # The channels of each encoder by source: encoders[name][source]. A
        # subclass adds more sources (SCControlHandler: rawencoder). An encoder
        # with pages keeps its hybrid channel: it reads the encoder's CV.
        self.encoders = dict()
        for name in ENCODERS:
            self.encoders[name] = {"hybrid": self.channeldict[name]}
        self.pages = {}         # encoder name -> EncoderPages, for this instrument
        self.pageState = None   # its <name>.pages
        self.page_sent = {}     # path -> last value sent
        self.cv_assign = False  # file + reset held: choosing CV targets

    # ---- Per instrument -----------------------------------------------------

    # Called for every instrument, also when this handler is reused for the
    # next one: encoders, button modes and pages as its nebconfig declares
    # them. pages_path: its <name>.pages (saved page values).
    def setConfig(self, config, pages_path):  # nebconfig.NebConfig
        for name in ENCODERS:
            source = config.encoderType(name)
            if source not in self.encoders[name] and source != "pages":
                self.classlog.error("%s,%s: not in this bank, hybrid", name, source)
                source = "hybrid"
            new = self.encoders[name]["hybrid" if source == "pages" else source]
            old = self.channeldict[name]
            if new is not old:
                # The channel keeps its place in self.channels, resistNormalSettings()
                # pairs channels[i] with altchannels[i].
                self.channels[self.channels.index(old)] = new
                self.channeldict[name] = new
            self.classlog.info("%s: %s", name, source)
        self.setButtonConfig(config)
        self.setPages(config, pages_path)

    # Button mode and edge as the instrument declares them (e.g.
    # freeze,latching,rising), else the default, the same as
    # ControlHandler.__init__ does for a new handler.
    def setButtonConfig(self, nebConfig):
        output_period = nebConfig.outputPeriod()
        for ctrl in DIGITAL_CONTROLS:
            chn = self.channeldict.get(ctrl) or self.altchanneldict.get(ctrl)
            config = nebConfig.entry(ctrl) or self.defaultConfig.get(ctrl)
            if chn is None or config is None or len(config) < 2:
                continue
            chn.setMode(config[0], config[1])
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
        self.pageState = encoderpages.PageState(pages_path)
        self.pageState.load(self.pages)
        self.page_sent = {}
        self.cv_assign = False

    def savePages(self):
        if self.pageState is not None and self.pageState.dirty_time is not None:
            self.pageState.save(self.pages)

    # ---- Pages (ui.py calls these for an encoder that has pages) -----------

    def encoderPages(self, encoder):
        return self.pages.get(encoder)

    def pageStep(self, encoder, steps):
        self.pages[encoder].step(steps)
        self.pageState.changed(self.now)

    # Held and turned: as pitch, PAGE_JUMP per click (ui.py times them).
    def pageJump(self, encoder, steps):
        self.pages[encoder].move(encoderpages.PAGE_JUMP * steps)
        self.pageState.changed(self.now)

    def nextPage(self, encoder):
        self.pages[encoder].nextPage()

    def stepCvTarget(self, encoder, steps):
        self.pages[encoder].stepCandidate(steps)

    def cvAssignActive(self):
        return self.cv_assign

    # Both CV_ASSIGN_BUTTONS held: they stop being sent (each gets 0 once, so
    # a gate on one of them closes), and the encoders choose their CV targets.
    # Released: the choices are kept and saved, and the release counts as no
    # button press.
    def updateCvAssign(self):
        held_next = self.shiftReg.state(libSR.PIN_NEXT)
        held_reset = self.shiftReg.state(libSR.PIN_RESET)
        if held_next and held_reset and not self.cv_assign and self.pages:
            self.cv_assign = True
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

    # Whether a control is sent as itself: not an encoder with pages (its
    # pages are sent), not file/reset while CV targets are chosen.
    def sendsControl(self, name):
        if name in self.pages:
            return False
        return not (self.cv_assign and name in CV_ASSIGN_BUTTONS)

    # The encoder's CV input alone: the channel's value without what the
    # encoder set (hybrid = encoder + CV).
    def encoderCV(self, encoder):
        chn = self.channeldict[encoder]
        return chn.getValue() - chn.getStaticVal()

    # Each page whose value changed since it was last sent (all if full).
    def sendPages(self, full=False):
        sent = self.page_sent
        for encoder, pages in self.pages.items():
            for path, out in pages.outputs(self.encoderCV(encoder)):
                if full or sent.get(path) != out:
                    self.sendPath(path, out)
                    sent[path] = out
        if self.pageState is not None:
            self.pageState.saveIfDue(self.now, self.pages)

    # ---- Sending: the bank's own ---------------------------------------------

    def sendControl(self, name, value):
        raise NotImplementedError

    def sendPath(self, path, value):
        raise NotImplementedError
