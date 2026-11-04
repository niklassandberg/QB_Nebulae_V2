import encoderpages
import nebio
from controlhandlerEncoders import EncoderControlHandler

# Only changed values are sent to the program, and every value again at least
# this often: a program that starts (or restarts) late gets them all.
PROG_RESEND_MS = 1000

# Control handler for the programs bank (a .prog: any program that listens
# for OSC, e.g. miRings). Owns the OSC link to the program (nebio OscLink on
# the .prog's port). Which control goes to which OSC path, and in which range,
# is in the .prog (osc: lines, nebconfig.py oscBindings()); a control without
# a binding is not sent. Encoders, button modes and pages per .prog:
# EncoderControlHandler.
class ProgControlHandler(EncoderControlHandler):

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
        self.savePages()
        super(ProgControlHandler, self).closeSockets()
        nebio.osc_close()

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

    # The programs bank has no Csound "normal" mode: leaving secondary
    # controls or the instr selector (ui.py) goes back to programs mode.
    def enterNormalMode(self):
        self.enterProgramsMode()

    # Sends each bound channel and page whose value changed since it was last
    # sent (all of them every PROG_RESEND_MS).
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
