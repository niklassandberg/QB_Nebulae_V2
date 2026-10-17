import time

import scsender
from controlhandler import ControlHandler

# Control handler for the SuperCollider bank. Owns the OSC link to sclang (scSock).
class SCControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(SCControlHandler, self).__init__(*args, **kwargs)
        self.scSock = scsender.ScSend()

    def startScOscServer(self):
        self.classlog.info("startScOscServer")
        self.scSock.connectSender()
        # /sc/up and /neb/ready are handled inside nebio (see scsender.py),
        # read with synthIsUpStatus()/sclangHandshakeStatus(); no callbacks.
        self.scSock.addResiver('/sc/up', None)
        self.scSock.addResiver('/neb/ready', None)
        #TODO: add other listener
        self.scSock.startListener()

    def waitOnScLang(self):
        self.classlog.info("waitOnScang")
        self.scSock.zeroSclangHandshake()
        retries = 0
        while not self.scSock.sclangHandshakeStatus():
            self.classlog.info("sclang is not ready yet, waiting...")
            self.scSock.send('ready', 0)
            retries += 1
            if retries > 50:
                self.classlog.info("Timeout waiting for sclang to be ready!")
                break
            time.sleep(0.1)
        if retries >= 50:
            self.classlog.info("sclang is not ready after 50 retries!")
            #sys.exit(50)

    def synthIsUpStatus(self):
        try:
            retries = 0
            self.classlog.info("Waiting for synth handshake...")
            while not self.scSock.waitSynthIsUp(timeout=0.5):
                self.classlog.info("synth is not up yet, pinging SC...")
                self.scSock.pingLoaded()
                retries += 1
                if retries > 50:
                    self.classlog.error("Synth did not respond after 50 pings, giving up!")
                    return
            self.classlog.info("Synth is up!")
        except Exception as e:
            self.classlog.error("Error in synthIsUpStatus(): %s", e)

    def loadScSynth(self, patch):
        self.scSock.setSynthIsDown()
        self.scSock.send('loadScFile', patch)
        self.synthIsUpStatus()

    def closeSockets(self):
        super(SCControlHandler, self).closeSockets()
        if self.scSock.is_connected():
            self.scSock.close()

    def closeScSynthProcess(self):
        try:
            self.scSock.send("quit", 0)
        except Exception as e:
            self.classlog.error("Error in closeScSynthProcess(): %s", e)

    def sendScOscMessages(self):
        for chn in self.channels: #for each of the adc channels
            chn.update()
            self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message
        for chn in self.altchannels:
            chn.update()
            self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message

    def enterSuperColliderMode(self): ##added supercollider mode, very similar to the PD mode
        self.prev_control_mode = self.control_mode
        for chn in self.channels: #mutes csound
            chn.muteCSound(True)
        #TODO: wtf is this!!! self.control_mode = "supercollider" above!!!
        if self.control_mode == "secondary controls":
            self.resistSecondarySettings()
        self.control_mode = "supercollider"
        self.settings.update(self.now)
        self.settings.write()
        self.altchanneldict["source_alt"].setValue(0)
        if self.pdSock.is_connected(): #kills pure data
            self.pdSock.close()
        #TODO: HERE ADD ALL SUPERCOLLIDER INITS!!!
        if not self.scSock.is_connected():
            self.classlog.info("def enterSuperColliderMode: Connecting to SC Socket")
            self.scSock.connectSender()
        for chn in self.channels:
            self.classlog.info("def enterSuperColliderMode: initializin %s value %s", chn.name, str(chn.getValue()))

    # The SC bank has no Csound "normal" mode: leaving secondary controls or the
    # instr selector (ui.py) goes back to supercollider mode.
    def enterNormalMode(self):
        self.enterSuperColliderMode()

    def enterSecondaryMode(self):
        if not self.scSock.is_connected() and self.control_mode == "supercollider" :
            self.classlog.info("def enterSecondaryMode: Connecting to SC Socket")
            #TODO: why call this???!!
            self.scSock.connectSender()
        super(SCControlHandler, self).enterSecondaryMode()

    # Only the supercollider part of ControlHandler.updateAll(): no Csound
    # (end of loop, record status, file handling) and no Pure Data.
    def updateAll(self):
        self.countUpdateAll()
        self.shiftReg.update()
        self.handleSourceHold()

        if self.control_mode == "secondary controls":
            self.sendScOscMessages() # all channels and alt channels
            self.setInputLevel(self.altchanneldict["speed_alt"].getValue())
        elif self.control_mode == "instr selector":
            self.updateInstrSelector()
        else: # supercollider
            for chn in self.channels: #for each of the adc channels
                if chn.name != "sourcegate":
                    chn.setIgnoreHID(False)
                chn.update() #update all control values
                self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message
