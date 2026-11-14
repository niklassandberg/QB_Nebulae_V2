import encoderpages
import nebio
from controlhandlerEncoders import EncoderControlHandler

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
        self.speed_leds = False

    def setConfig(self, config, pages_path):
        super(ProgControlHandler, self).setConfig(config, pages_path)
        self.speed_leds = config.speedLeds() == "playback" and "speed" in self.bindings

    # The playback speed sent for speed (speedleds,playback), else None.
    def playbackSpeed(self):
        if not self.speed_leds or "speed" in self.pages:
            return None
        path, lo, hi, curve = self.bindings["speed"][0]
        return encoderpages.scale(self.channeldict["speed"].getValue(), lo, hi, curve)

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

    # nebulae.py starts the handler once the program listens: everything goes
    # on the first pass, then only changes.
    def sendProgMessages(self, channels):
        sent = self.prog_sent
        for chn in channels:
            if not self.sendsControl(chn.name):
                continue
            value = chn.getValue()
            for path, lo, hi, curve in self.bindings.get(chn.name, []):
                out = encoderpages.scale(value, lo, hi, curve)
                if sent.get(path) != out:
                    nebio.osc_send(path, out)
                    sent[path] = out
        self.sendPages()

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
