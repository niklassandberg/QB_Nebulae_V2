import time

import pdsender
from controlhandler import ControlHandler

# Control handler for the Pure Data bank. Owns the socket to Pure Data (pdSock).
class PDControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(PDControlHandler, self).__init__(*args, **kwargs)
        self.pdSock = pdsender.PdSend() # connects only in enterPureDataMode()

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

    # The PD bank has no Csound "normal" mode: leaving secondary controls or the
    # instr selector (ui.py) goes back to puredata mode.
    def enterNormalMode(self):
        self.enterPureDataMode()

    def enterSecondaryMode(self):
        if not self.pdSock.is_connected() and self.control_mode == "puredata" :
            self.classlog.info("def enterSecondaryMode: Connecting to PD Socket")
            self.pdSock.connect()
        super(PDControlHandler, self).enterSecondaryMode()

    # Sends "name value" for each channel to Pure Data in one batch.
    def sendPdMessages(self, channels):
        msgs = []
        for chn in channels:
            msgs.append(chn.name + ' ' + str(chn.getValue()))
        try:
            self.pdSock.send(msgs)
        except Exception as e:
            if self.pdSock.is_connected():
                self.classlog.error("pd: Could not send messages to PD. Connected, but error?: %s", e)
            else:
                self.classlog.error("pd: Could not send messgaes to PD. No connection?': %s", e)

    # Only the puredata part of ControlHandler.updateAll(): no Csound
    # (end of loop, record status, file handling) and no SuperCollider.
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
