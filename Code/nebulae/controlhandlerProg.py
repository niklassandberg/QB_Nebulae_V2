import math

import nebio
from controlhandler import ControlHandler

# Only changed values are sent to the program, and every value again at least
# this often: a program that starts (or restarts) late gets them all.
PROG_RESEND_MS = 1000

# Control handler for the programs bank (a .prog: any program that listens
# for OSC, e.g. miRings). Which control goes to which OSC path, and in which
# range, is in the .prog (nebconfig.py oscBindings()); a control without a
# binding is not sent.
class ProgControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        self.oscPort = kwargs.pop("oscPort")
        bindings = kwargs.pop("bindings")
        super(ProgControlHandler, self).__init__(*args, **kwargs)
        # control name -> [(path, min, max, curve)]
        self.bindings = {}
        for control, path, lo, hi, curve in bindings:
            self.bindings.setdefault(control, []).append((path, lo, hi, curve))
        self.prog_sent = {}  # path -> last value sent
        self.prog_resend_time = 0

    def closeSockets(self):
        super(ProgControlHandler, self).closeSockets()
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

    # A control's value (0..1 for knobs and CV, 0/1 for buttons) in the
    # binding's range.
    @staticmethod
    def scale(value, lo, hi, curve):
        v = min(1.0, max(0.0, float(value)))
        if curve == "exp":
            return lo * math.pow(hi / lo, v)
        out = lo + (hi - lo) * v
        if curve == "int":
            return float(round(out))
        return out

    # Sends each bound channel whose value changed since it was last sent
    # (all of them every PROG_RESEND_MS).
    def sendProgMessages(self, channels):
        full = self.now - self.prog_resend_time >= PROG_RESEND_MS
        if full:
            self.prog_resend_time = self.now
        sent = self.prog_sent
        for chn in channels:
            targets = self.bindings.get(chn.name)
            if not targets:
                continue
            value = chn.getValue()
            for path, lo, hi, curve in targets:
                out = self.scale(value, lo, hi, curve)
                if full or sent.get(path) != out:
                    nebio.osc_send(path, out)
                    sent[path] = out

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
            for chn in self.channels:
                if chn.name != "sourcegate":
                    chn.setIgnoreHID(False)
                chn.update()
            self.sendProgMessages(self.channels)
