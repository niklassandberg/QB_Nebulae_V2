import time

import control
import nebio
import scsender
from controlhandlerEncoders import EncoderControlHandler, ENCODERS

class SCControlHandler(EncoderControlHandler):

    def __init__(self, *args, **kwargs):
        super(SCControlHandler, self).__init__(*args, **kwargs)
        self.scSock = scsender.ScSend()
        self.rawReady = False
        for name in ENCODERS:
            self.encoders[name]["rawencoder"] = control.ControlChannel(None, name, 0, "rawencoder")

    def closeSockets(self):
        self.setRawActive(False)
        self.savePages()
        super(SCControlHandler, self).closeSockets()
        if self.scSock.is_connected():
            self.scSock.close()

    def sendControl(self, name, value):
        self.scSock.send(name, value)

    def sendPath(self, path, value):
        nebio.sc_send_path_float(path, value)

    def rawChannels(self):
        return [chn for chn in self.channels if chn.source == "rawencoder"]

    def setConfig(self, config, pages_path):
        self.setRawActive(False)
        self.rawReady = False
        nebio.led_clear_sc()  # the old patch's LED colours
        super(SCControlHandler, self).setConfig(config, pages_path)

    def isRaw(self, name):
        chn = self.channeldict.get(name)
        return chn is not None and chn.source == "rawencoder"

    # Also routes the clicks of both encoders (raw or hybrid) to sclang.
    def setRawActive(self, state):
        for chn in self.rawChannels():
            chn.input.setActive(state)
        for name in ENCODERS:
            nebio.encoder_set_click(name, state)

    def startRawEncoders(self):
        self.rawReady = True
        self.page_sent = {}  # the patch's NebPage buses exist now
        if self.control_mode == "supercollider":
            self.setRawActive(True)

    def enterSuperColliderMode(self): ##added supercollider mode, very similar to the PD mode
        self.prev_control_mode = self.control_mode
        for chn in self.channels: #mutes csound
            chn.muteCSound(True)
        if self.control_mode == "secondary controls":
            self.resistSecondarySettings()
        self.control_mode = "supercollider"
        self.settings.update(self.now)
        self.settings.write()
        self.altchanneldict["source_alt"].setValue(0)
        #TODO: HERE ADD ALL SUPERCOLLIDER INITS!!!
        if not self.scSock.is_connected():
            self.classlog.info("def enterSuperColliderMode: Connecting to SC Socket")
            self.scSock.connectSender()
        for chn in self.channels:
            self.classlog.info("def enterSuperColliderMode: initializin %s value %s", chn.name, str(chn.getValue()))
        if self.rawReady:
            self.setRawActive(True)

    def enterNormalMode(self):
        self.enterSuperColliderMode()

    def enterSecondaryMode(self):
        if not self.scSock.is_connected() and self.control_mode == "supercollider" :
            self.classlog.info("def enterSecondaryMode: Connecting to SC Socket")
            #TODO: why call this???!!
            self.scSock.connectSender()
        self.setRawActive(False)
        super(SCControlHandler, self).enterSecondaryMode()

    def enterInstrSelMode(self):
        self.setRawActive(False)
        super(SCControlHandler, self).enterInstrSelMode()

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
            self.updateCvAssign()
            for chn in self.channels: #for each of the adc channels
                if chn.source == "rawencoder":
                    continue # nebio and sclang handle it
                if chn.name != "sourcegate":
                    chn.setIgnoreHID(False)
                chn.update() #update all control values
                if self.sendsControl(chn.name):
                    self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message
            self.sendPages()

    # specific supercollider things




    def startScOscServer(self):
        self.classlog.info("startScOscServer")
        self.scSock.connectSender()
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

    # A loadScFile sent before sclang listens is lost: the bank stays silent.
    def waitForSclangPort(self, timeout=30.0):
        self.classlog.info("wait until sclang lisen on port %d", scsender.ScSend.rPort)
        port = ":%04X" % scsender.ScSend.rPort
        start = time.time()
        while time.time() - start < timeout:
            for table in ("/proc/net/udp", "/proc/net/udp6"):
                try:
                    with open(table) as f:
                        next(f)  # header
                        if any(line.split()[1].endswith(port) for line in f):
                            return True
                except (OSError, IndexError, StopIteration):
                    pass
            time.sleep(0.1)
        self.classlog.warning("sclang does not listen on %d after %.0f s, loading anyway",
                              scsender.ScSend.rPort, timeout)
        return False

    def loadScSynth(self, patch):
        self.scSock.setSynthIsDown()
        self.waitForSclangPort()
        self.scSock.send('loadScFile', patch)
        self.synthIsUpStatus()

    def closeScSynthProcess(self):
        try:
            self.scSock.send("quit", 0)
        except Exception as e:
            self.classlog.error("Error in closeScSynthProcess(): %s", e)

    def sendScOscMessages(self):
        for chn in self.channels: #for each of the adc channels
            if chn.source == "rawencoder":
                continue # nebio and sclang handle it
            chn.update()
            if self.sendsControl(chn.name):
                self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message
        for chn in self.altchannels:
            chn.update()
            self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message
        self.sendPages()

