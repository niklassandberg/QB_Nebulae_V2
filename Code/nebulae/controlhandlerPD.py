import time

import pdsender
from controlhandler import ControlHandler

# Everything is resent this often, for a [netreceive] opened late.
PD_RESEND_MS = 1000

class PDControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(PDControlHandler, self).__init__(*args, **kwargs)
        self.pdSock = pdsender.PdSend()
        self.pd_sent = {}
        self.pd_resend_time = 0

    def closeSockets(self):
        super(PDControlHandler, self).closeSockets()
        if self.pdSock.is_connected():
            self.pdSock.close()

    def enterPureDataMode(self):
        self.prev_control_mode = self.control_mode
        if self.modeChangeControl is not None:
            self.channeldict[self.modeChangeControl].setIgnoreNextButton()
        if self.control_mode == "secondary controls":
            self.resistSecondarySettings()
        for chn in self.channels:
            chn.muteCSound(True)
        if not self.pdSock.is_connected():
            self.classlog.info("def enterPureDataMode: Connecting to PD Socket")
            self.pdSock.connect()
        self.control_mode = "puredata"

    def enterNormalMode(self):
        self.enterPureDataMode()

    def enterSecondaryMode(self):
        if not self.pdSock.is_connected() and self.control_mode == "puredata" :
            self.classlog.info("def enterSecondaryMode: Connecting to PD Socket")
            self.pdSock.connect()
        super(PDControlHandler, self).enterSecondaryMode()

    # A failed send forgets what was sent, so everything goes again.
    def sendPdMessages(self, channels):
        full = self.now - self.pd_resend_time >= PD_RESEND_MS
        sent = self.pd_sent
        msgs = []
        changed = {}
        for chn in channels:
            name = chn.name
            value = chn.getValue()
            if full or name not in sent or sent[name] != value:
                msgs.append(name + ' ' + str(value))
                changed[name] = value
        if not msgs:
            return
        try:
            if self.pdSock.send(msgs):
                sent.update(changed)
                if full:
                    self.pd_resend_time = self.now
            else:
                sent.clear()
        except Exception as e:
            sent.clear()
            if self.pdSock.is_connected():
                self.classlog.error("pd: Could not send messages to PD. Connected, but error?: %s", e)
            else:
                self.classlog.error("pd: Could not send messgaes to PD. No connection?': %s", e)

    def updateAll(self):
        self.countUpdateAll()
        self.shiftReg.update()
        self.handleSourceHold()

        if self.control_mode == "secondary controls":
            time.sleep(0.001)
            for chn in self.channels + self.altchannels:
                #chn.setIgnoreHID(False)
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
