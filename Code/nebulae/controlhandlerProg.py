import nebio
import progpages
import shiftregister as libSR
from controlhandler import ControlHandler

# Only changed values are sent to the program, and every value again at least
# this often: a program that starts (or restarts) late gets them all.
PROG_RESEND_MS = 1000

# The buttons held together to choose where the speed/pitch CV goes.
CV_ASSIGN_BUTTONS = ("file", "reset")

# Control handler for the programs bank (a .prog: any program that listens
# for OSC, e.g. miRings). Which control goes to which OSC path, and in which
# range, is in the .prog (nebconfig.py oscBindings()); a control without a
# binding is not sent. Speed and pitch can have pages instead (progpages.py).
class ProgControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        self.oscPort = kwargs.pop("oscPort")
        bindings = kwargs.pop("bindings")
        pages = kwargs.pop("pages", {})
        cv_targets = kwargs.pop("cvTargets", {})
        prog_name = kwargs.pop("progName")
        super(ProgControlHandler, self).__init__(*args, **kwargs)
        # Encoders with pages: encoder name -> EncoderPages
        self.pages = {}
        for encoder, entries in pages.items():
            self.pages[encoder] = progpages.EncoderPages(
                encoder, [progpages.Page(*e) for e in entries], cv_targets.get(encoder))
        self.state = progpages.ProgState(prog_name)
        self.state.load(self.pages)
        # control name -> [(path, min, max, curve)]; an encoder with pages
        # is sent through its pages instead.
        self.bindings = {}
        for control, path, lo, hi, curve in bindings:
            if control not in self.pages:
                self.bindings.setdefault(control, []).append((path, lo, hi, curve))
        self.prog_sent = {}  # path -> last value sent
        self.prog_resend_time = 0
        self.cv_assign = False

    scale = staticmethod(progpages.scale)

    def closeSockets(self):
        super(ProgControlHandler, self).closeSockets()
        if self.state.dirty_time is not None:  # a change not saved yet
            self.state.save(self.pages)
        nebio.osc_close()

    def enterProgramsMode(self):
        self.prev_control_mode = self.control_mode
        if self.modeChangeControl is not None:
            self.channeldict[self.modeChangeControl].setIgnoreNextButton()
        if self.control_mode == "secondary controls":
            self.resistSecondarySettings()
        for chn in self.channels:
            chn.muteCSound(True)
        nebio.osc_open(self.oscPort)
        self.control_mode = "programs"

    # The programs bank has no Csound "normal" mode: leaving secondary
    # controls or the instr selector (ui.py) goes back to programs mode.
    def enterNormalMode(self):
        self.enterProgramsMode()

    # ---- Pages (ui.py calls these for an encoder that has pages) ----

    def encoderPages(self, encoder):
        return self.pages.get(encoder)

    def pageStep(self, encoder, steps):
        self.pages[encoder].step(steps)
        self.state.changed(self.now)

    def nextPage(self, encoder):
        self.pages[encoder].nextPage()

    def stepCvTarget(self, encoder, steps):
        self.pages[encoder].stepCandidate(steps)

    def cvAssignActive(self):
        return self.cv_assign

    # Both CV_ASSIGN_BUTTONS held: their bindings stop (a gate on one of them
    # gets 0 once), and the encoders choose their CV targets. Released: the
    # choices are kept and saved, and the release counts as no button press.
    def updateCvAssign(self):
        held = self.shiftReg.state(libSR.PIN_NEXT) and self.shiftReg.state(libSR.PIN_RESET)
        if held and not self.cv_assign and self.pages:
            self.cv_assign = True
            for pages in self.pages.values():
                pages.startChoosing()
            for name in CV_ASSIGN_BUTTONS:
                self.channeldict[name].setIgnoreNextButton()
                for path, lo, hi, curve in self.bindings.get(name, []):
                    out = self.scale(0, lo, hi, curve)
                    nebio.osc_send(path, out)
                    self.prog_sent[path] = out
        elif self.cv_assign and not self.shiftReg.state(libSR.PIN_NEXT) \
                and not self.shiftReg.state(libSR.PIN_RESET):
            self.cv_assign = False
            changed = False
            for pages in self.pages.values():
                changed = pages.commitCandidate() or changed
            if changed:
                self.state.changed(self.now)
                self.classlog.info("CV targets: %s", ", ".join(
                    "%s -> %s" % (e, p.cv_target or "none") for e, p in self.pages.items()))

    # The encoder's CV input alone: the channel's value without what the
    # encoder set (hybrid = encoder + CV).
    def encoderCV(self, encoder):
        chn = self.channeldict[encoder]
        return chn.getValue() - chn.getStaticVal()

    # Sends each bound channel and page whose value changed since it was last
    # sent (all of them every PROG_RESEND_MS).
    def sendProgMessages(self, channels):
        full = self.now - self.prog_resend_time >= PROG_RESEND_MS
        if full:
            self.prog_resend_time = self.now
        sent = self.prog_sent
        for chn in channels:
            if self.cv_assign and chn.name in CV_ASSIGN_BUTTONS:
                continue
            targets = self.bindings.get(chn.name)
            if not targets:
                continue
            value = chn.getValue()
            for path, lo, hi, curve in targets:
                out = self.scale(value, lo, hi, curve)
                if full or sent.get(path) != out:
                    nebio.osc_send(path, out)
                    sent[path] = out
        for encoder, pages in self.pages.items():
            for path, out in pages.outputs(self.encoderCV(encoder)):
                if full or sent.get(path) != out:
                    nebio.osc_send(path, out)
                    sent[path] = out
        self.state.saveIfDue(self.now, self.pages)

    # Only the programs part of ControlHandler.updateAll(): no Csound (end
    # of loop, record status, file handling).
    def updateAll(self):
        self.countUpdateAll()
        self.shiftReg.update()
        self.handleSourceHold()

        if self.control_mode == "secondary controls":
            for chn in self.channels + self.altchannels:
                chn.update()
            self.sendProgMessages(self.channels + self.altchannels)
            self.setInputLevel(self.altchanneldict["speed_alt"].getValue())
        elif self.control_mode == "instr selector":
            self.updateInstrSelector()
        else: # programs
            self.updateCvAssign()
            for chn in self.channels:
                if chn.name != "sourcegate":
                    chn.setIgnoreHID(False)
                chn.update()
            self.sendProgMessages(self.channels)
