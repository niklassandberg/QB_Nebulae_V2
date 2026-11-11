import digitaldata
import encoderpages
import shiftregister as libSR
from controlhandler import ControlHandler, DIGITAL_CONTROLS

ENCODERS = ("speed", "pitch")
CV_ASSIGN_BUTTONS = ("file", "reset")

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
        self.setButtonConfig(config)
        self.setPages(config, pages_path)

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

    def saveInstrument(self):
        super(EncoderControlHandler, self).saveInstrument()
        self.savePages()

    def savePages(self):
        if self.pageState is not None and self.pageState.dirty_time is not None:
            self.pageState.save(self.pages)

    def encoderPages(self, encoder):
        return self.pages.get(encoder)

    def pageStep(self, encoder, steps):
        self.pages[encoder].step(steps)
        self.pageState.changed(self.now)

    def pageJump(self, encoder, steps):
        self.pages[encoder].move(encoderpages.PAGE_JUMP * steps)
        self.pageState.changed(self.now)

    def nextPage(self, encoder):
        self.pages[encoder].nextPage()

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
        for encoder, pages in self.pages.items():
            for path, out in pages.outputs(self.encoderCV(encoder)):
                if full or sent.get(path) != out:
                    self.sendPath(path, out)
                    sent[path] = out
        if self.pageState is not None:
            self.pageState.saveIfDue(self.now, self.pages)

    def sendControl(self, name, value):
        raise NotImplementedError

    def sendPath(self, path, value):
        raise NotImplementedError
