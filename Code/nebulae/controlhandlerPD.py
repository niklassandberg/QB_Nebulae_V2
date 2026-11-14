import time

import nebio
from controlhandler import ControlHandler

# Pd listens for OSC here: [netreceive -u -b 3000] -> [oscparse] -> [list trim]
# (pdconvert.py converts the old TCP patches).
PD_PORT = 3000

class PDControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(PDControlHandler, self).__init__(*args, **kwargs)
        self.pd_sent = {}

    def closeSockets(self):
        super(PDControlHandler, self).closeSockets()
        nebio.osc_close()

    def enterPureDataMode(self):
        self.prev_control_mode = self.control_mode
        if self.modeChangeControl is not None:
            self.channeldict[self.modeChangeControl].setIgnoreNextButton()
        if self.control_mode == "secondary controls":
            self.resistSecondarySettings()
        for chn in self.channels:
            chn.muteCSound(True)
        nebio.osc_open(PD_PORT)
        self.control_mode = "puredata"
        self.saveInstrument()

    def enterNormalMode(self):
        self.enterPureDataMode()

    # nebulae.py starts the handler once Pd listens: everything goes on the
    # first pass, then only changes. "/start 0.5" arrives as "start 0.5".
    def sendPdMessages(self, channels):
        sent = self.pd_sent
        for chn in channels:
            name = chn.name
            value = chn.getValue()
            if name not in sent or sent[name] != value:
                nebio.osc_send("/" + name, value)
                sent[name] = value

    def updateAll(self):
        self.countUpdateAll()
        self.shiftReg.update()
        self.handleSourceHold()

        if self.control_mode == "secondary controls":
            time.sleep(0.001)
            for chn in self.channels + self.altchannels:
                chn.update()
            self.sendPdMessages(self.channels + self.altchannels)
            self.setInputLevel(self.altchanneldict["speed_alt"].getValue())
        elif self.control_mode == "instr selector":
            self.updateInstrSelector()
        else: # puredata
            time.sleep(0.001)
            for chn in self.channels:
                if chn.name != "sourcegate":
                    chn.setIgnoreHID(False)
                chn.update()
            self.sendPdMessages(self.channels)
