import time

import pdsender
from controlhandler import ControlHandler

# Until the patch answers "nebready" with "ready", everything is resent this
# often (with "nebready"): a patch without the answer still gets all values.
PD_RESEND_MS = 1000

class PDControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(PDControlHandler, self).__init__(*args, **kwargs)
        self.pdSock = pdsender.PdSend()
        self.pd_sent = {}
        self.pd_resend_time = 0
        self.pd_ready = False

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
        self.saveInstrument()

    def enterNormalMode(self):
        self.enterPureDataMode()

    def enterSecondaryMode(self):
        if not self.pdSock.is_connected() and self.control_mode == "puredata" :
            self.classlog.info("def enterSecondaryMode: Connecting to PD Socket")
            self.pdSock.connect()
        super(PDControlHandler, self).enterSecondaryMode()

    # The patch's "ready" gets everything once, then only changes. A failed
    # send forgets what was sent and that it was ready, so everything goes again.
    def sendPdMessages(self, channels):
        if not self.pd_ready and self.pdSock.takeReady():
            self.classlog.info("pd: the patch is ready")
            self.pd_ready = True
            self.pd_sent.clear()
        full = not self.pd_ready and self.now - self.pd_resend_time >= PD_RESEND_MS
        sent = self.pd_sent
        msgs = []
        changed = {}
        for chn in channels:
            name = chn.name
            value = chn.getValue()
            if full or name not in sent or sent[name] != value:
                msgs.append(name + ' ' + str(value))
                changed[name] = value
        if full:
            msgs.append("nebready")
        if not msgs:
            return
        try:
            if self.pdSock.send(msgs):
                sent.update(changed)
                if full:
                    self.pd_resend_time = self.now
            else:
                sent.clear()
                self.pd_ready = False
        except Exception as e:
            sent.clear()
            self.pd_ready = False
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
