import time

import control
import nebio
import scsender
import digitaldata
from controlhandler import ControlHandler, DIGITAL_CONTROLS

# Encoders a .scd can declare as "rawencoder" in its nebconfig block.
RAW_ENCODERS = ("speed", "pitch")

# Control handler for the SuperCollider bank. Owns the OSC link to sclang (scSock).
class SCControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(SCControlHandler, self).__init__(*args, **kwargs)
        self.scSock = scsender.ScSend()
        self.rawReady = False  # patch loaded, sclang can take the raw encoders
        # Both channels of each encoder, built once: encoders[name][source].
        self.encoders = dict()
        for name in RAW_ENCODERS:
            self.encoders[name] = dict()
            self.encoders[name]["hybrid"] = self.channeldict[name] # built by ControlHandler
            self.encoders[name]["rawencoder"] = control.ControlChannel(None, name, 0, "rawencoder")

    def closeSockets(self):
        self.setRawActive(False)
        super(SCControlHandler, self).closeSockets()
        if self.scSock.is_connected():
            self.scSock.close()

    # ---- rawencoder -------------------------------------------------------

    def rawChannels(self):
        return [chn for chn in self.channels if chn.source == "rawencoder"]

    # Called for every patch, also when this handler is reused for the next
    # .scd: speed/pitch become rawencoder or hybrid as the patch declares them.
    # The channel keeps its place in self.channels, resistNormalSettings()
    # pairs channels[i] with altchannels[i].
    def setConfig(self, scParser):
        self.setRawActive(False)
        self.rawReady = False
        nebio.led_clear_sc()  # the old patch's LED colours
        for name in RAW_ENCODERS:
            source = scParser.getType(name)
            old = self.channeldict[name]
            new = self.encoders[name][source]
            if new is old:
                continue
            self.channels[self.channels.index(old)] = new
            self.channeldict[name] = new
            self.classlog.info("%s: %s", name, source)
        self.setButtonConfig(scParser)

    # Button mode and edge as the .scd declares them (e.g. freeze,latching,rising),
    # else the default, the same as ControlHandler.__init__ does for a new handler.
    def setButtonConfig(self, scParser):
        output_period = scParser.getOutputPeriod()
        for ctrl in DIGITAL_CONTROLS:
            chn = self.channeldict.get(ctrl) or self.altchanneldict.get(ctrl)
            config = scParser.configEntry(ctrl) or self.defaultConfig.get(ctrl)
            if chn is None or config is None or len(config) < 2:
                continue
            chn.setMode(config[0], config[1])
            if config[0] == "triggered":
                chn.setOutputPeriod(output_period)
            else:
                chn.setOutputPeriod(digitaldata.DEFAULT_OUTPUT_PERIOD)

    # Declared rawencoder by the loaded .scd (in supercollider mode Python
    # never sets its value or LEDs).
    def isRaw(self, name):
        chn = self.channeldict.get(name)
        return chn is not None and chn.source == "rawencoder"

    # Raw routing in nebio: only in supercollider mode and once the patch is loaded.
    # Also the press/release of both encoders (raw or hybrid) goes to sclang
    # in the same window, so a patch always knows when speed/pitch are clicked.
    def setRawActive(self, state):
        for chn in self.rawChannels():
            chn.input.setActive(state)
        for name in RAW_ENCODERS:
            nebio.encoder_set_click(name, state)

    # NebInterface's input clip detector reports to nebio (/sc/clip).
    def inputClipCount(self):
        return nebio.sc_clip_count()

    # After loadScSynth(): the patch is running, sclang can take the raw encoders.
    def startRawEncoders(self):
        self.rawReady = True
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

    # The SC bank has no Csound "normal" mode: leaving secondary controls or the
    # instr selector (ui.py) goes back to supercollider mode.
    def enterNormalMode(self):
        self.enterSuperColliderMode()

    def enterSecondaryMode(self):
        if not self.scSock.is_connected() and self.control_mode == "supercollider" :
            self.classlog.info("def enterSecondaryMode: Connecting to SC Socket")
            #TODO: why call this???!!
            self.scSock.connectSender()
        self.setRawActive(False)  # Python needs the encoders in secondary controls
        super(SCControlHandler, self).enterSecondaryMode()

    def enterInstrSelMode(self):
        self.setRawActive(False)  # and in the instr selector
        super(SCControlHandler, self).enterInstrSelMode()

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
                if chn.source == "rawencoder":
                    continue # nebio and sclang handle it
                if chn.name != "sourcegate":
                    chn.setIgnoreHID(False)
                chn.update() #update all control values
                self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message

    # specific supercollider things




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
            self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message
        for chn in self.altchannels:
            chn.update()
            self.scSock.send(chn.name, chn.getValue()) ##for each channel I send a OSC message

