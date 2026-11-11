import encoderpages
import nebio
from controlhandlerEncoders import EncoderControlHandler

# Everything is resent this often, so a program that starts late gets all values.
PROG_RESEND_MS = 1000

# Programs bank: controls go to the program as OSC, by the .prog's osc: lines.
class ProgControlHandler(EncoderControlHandler):

    def __init__(self, *args, **kwargs):
        self.oscPort = kwargs.pop("oscPort")
        bindings = kwargs.pop("bindings")
        super(ProgControlHandler, self).__init__(*args, **kwargs)
        self.bindings = {}  # control -> [(path, min, max, curve)]
        for control, path, lo, hi, curve in bindings:
            self.bindings.setdefault(control, []).append((path, lo, hi, curve))
        self.prog_sent = {}
        self.prog_resend_time = 0

    def closeSockets(self):
        self.saveInstrument()
        super(ProgControlHandler, self).closeSockets()
        nebio.osc_close()

    # Nebulae saves what it sends; /neb/save is for a program's own values.
    def saveInstrument(self):
        super(ProgControlHandler, self).saveInstrument()
        nebio.osc_send("/neb/save", 1)

    def sendControl(self, name, value):
        for path, lo, hi, curve in self.bindings.get(name, []):
            out = encoderpages.scale(value, lo, hi, curve)
            nebio.osc_send(path, out)
            self.prog_sent[path] = out

    def sendPath(self, path, value):
        nebio.osc_send(path, value)

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
        self.saveInstrument()

    def enterNormalMode(self):
        self.enterProgramsMode()

    def sendProgMessages(self, channels):
        full = self.now - self.prog_resend_time >= PROG_RESEND_MS
        if full:
            self.prog_resend_time = self.now
        sent = self.prog_sent
        for chn in channels:
            if not self.sendsControl(chn.name):
                continue
            value = chn.getValue()
            for path, lo, hi, curve in self.bindings.get(chn.name, []):
                out = encoderpages.scale(value, lo, hi, curve)
                if full or sent.get(path) != out:
                    nebio.osc_send(path, out)
                    sent[path] = out
        self.sendPages(full)

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
            self.updateHolds()
            for chn in self.channels:
                if chn.name != "sourcegate":
                    chn.setIgnoreHID(self.buttonBlocked(chn.name))
                chn.update()
            self.sendProgMessages(self.channels)
