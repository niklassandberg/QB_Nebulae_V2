# Main Nebulae Source File
import sys
import os
import shutil
import fatal
fatal.enabled = True  # before the imports below: configsettings reads its file on import
import ctcsound
import controlhandler as ch
import controlhandlerSC as chSC
import controlhandlerPD as chPD
import controlhandlerProg as chProg
import encoderpages
import conductor
import nebconfig
import ui
import fileloader
import time
import socket
import struct
import logger
import neb_globals
import multiprocessing
import subprocess
import threading

import nebmixer
import nebio
import loopprofile
import kernelswitch
import textfile
from classlogger import ClassLogger
from configsettings import configSettings

# Csound's own handlers ignore SIGTERM: systemd would wait 90 s for SIGKILL.
ctcsound.csoundInitialize(ctcsound.CSOUNDINIT_NO_SIGNAL_HANDLER)

cfg_path = "/home/alarm/QB_Nebulae_V2/Code/config/"

debug = False 
debug_controls = False

class Nebulae(object):

    def __init__(self):
        self.log = logger.NebLogger()
        self.classlog = ClassLogger.loggerSetup(self)
        try:
            if neb_globals.remount_fs is False:
                self.classlog.info("Nebulae is operating in \"Read/Write\" mode.")
                self.classlog.info("Filesystem will not be remounted during operation.")
                os.system("/home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
            self.classlog.info("Nebulae Initializing")
            self.instr_cfg = cfg_path + "bootinstr.txt"
            self.orc_handle = conductor.Conductor() # Initialize Audio File Tables and Csound Score/Orchestra
            self.kernel_switch = kernelswitch.KernelSwitch() # RT or normal kernel, as the instrument asks
            #self.currentInstr = "a_granularlooper"
            self.c = None
            self.pt = None 
            self.st = None
            self.ui = None
            self.c_handle = None
            self.led_process = None
            self.prog = None
            # Check the config file for last instr
            self.new_bank = None
            self.new_instr = None
            if os.path.isfile(self.instr_cfg) and os.path.getsize(self.instr_cfg) > 0:
                # Get bank/instr from factory
                self.classlog.info("Reading bootinstr.txt")
                for line in textfile.lines(self.instr_cfg):
                    templist = line.strip().split(',')
                    if templist[0] == 'bank':
                        self.new_bank = templist[1]
                    elif templist[0] == 'instr':
                        self.new_instr = templist[1]
            if self.new_bank not in nebconfig.INSTR_DIRS or not self.new_instr or \
                    not os.path.isfile(nebconfig.instrumentPath(self.new_bank, self.new_instr)):
                if self.new_bank is not None:
                    self.classlog.info("Boot instrument %s (%s) not found", self.new_instr, self.new_bank)
                self.new_bank, self.new_instr = self.firstInstrument()
            self.currentInstr = self.new_instr
            self.first_run = True
            nebmixer.disable()
            self.last_debug_print = time.time()
        except Exception as e:
            self.classlog.error("Error in __init__: %s", e)

    def firstInstrument(self):
        for bank in ("instr", "supercollider", "puredata", "programs"):
            folder, ext = nebconfig.INSTR_DIRS[bank]
            try:
                names = sorted(f[:-len(ext)] for f in os.listdir(folder) if f.endswith(ext))
            except OSError:
                names = []
            if names:
                self.classlog.info("Starting %s (%s)", names[0], bank)
                return bank, names[0]
        folder = nebconfig.instrumentDir("instr")
        self.classlog.info("No instrument at all: adding the granular looper")
        os.makedirs(folder, exist_ok=True)
        shutil.copy2("/home/alarm/QB_Nebulae_V2/Code/instr/a_granularlooper.instr", folder)
        return "instr", "a_granularlooper"

    # At normal priority even SCHED_IDLE threads interrupt the performance
    # thread: dropouts on a Pi 3 while recording.
    def setRealtime(self, new_threads):
        prio = configSettings.csoundRtPriority
        if prio == 0:
            return
        if len(new_threads) != 1:
            self.classlog.warning("Csound thread not found (new threads: %s): normal priority",
                                  sorted(new_threads))
            return
        tid = int(new_threads.pop())
        try:
            os.sched_setscheduler(tid, os.SCHED_FIFO, os.sched_param(prio))
            self.classlog.info("Csound thread %d: real-time priority %d (SCHED_FIFO)", tid, prio)
        except OSError as e:
            self.classlog.error("Csound thread %d: no real-time priority: %s", tid, e)

    def getSysCores(self):
        try:
            return multiprocessing.cpu_count()
        except Exception as e:
            self.classlog.error("Error in getSysCores(): %s", e)
            return 1

    # Restarts the Pi into the kernel the instrument wants; waits for it.
    def kernelSwitch(self, instr, config):
        if not self.kernel_switch.switchFor(instr, config):
            return
        self.launch_bootled()
        time.sleep(60)
        self.classlog.error("No restart after 60 s: starting %s on this kernel", instr)
        self.kill_bootled()

    def startMark(self, step):
        now = time.monotonic()
        self.classlog.info("csound start: %s at %.3f s (+%.3f s)", step, now, now - self.start_mark)
        self.start_mark = now

    def watchScoreStart(self):
        def watch():
            marks = [(0.0, "score running (sample tables loaded)"), (1.0, "score time 1 s (instr 1 starts)")]
            end = time.monotonic() + 30
            while marks and time.monotonic() < end:
                if self.c.scoreTime() > marks[0][0]:
                    self.startMark(marks.pop(0)[1])
                time.sleep(0.005)
        threading.Thread(target=watch, daemon=True).start()

    def start(self, instr, instr_bank):
        try:
            self.start_mark = time.monotonic()
            self.startMark("begin")
            self.leave_jack()  # Csound opens the card itself
            self.classlog.info("Nebulae Starting")
            if self.currentInstr != self.new_instr:
                reset_settings_flag = True
            else:
                reset_settings_flag = False
            self.currentInstr = instr
            if self.c is None:
                self.c = ctcsound.Csound()
            self.log.spill_basic_info()
            floader = fileloader.FileLoader()
            floader.reload()
            self.startMark("files loaded from the stick")
            config = nebconfig.NebConfig.read("instr", instr)
            self.kernelSwitch(instr, config)
            self.orc_handle.generate_orc(instr, instr_bank, config)
            self.startMark("orchestra generated (%d files)" % self.orc_handle.numFiles())
            configData = self.orc_handle.getConfigDict()
            
            self.c.setOption("-iadc:hw:0,0")
            self.c.setOption("-odac:hw:0,0") 
            
            #self.c.setOption("-iadc") # FOR JACK!!!
            #self.c.setOption("-odac") # FOR JACK!!!
            
            if "-B" in configData:
                self.c.setOption("-B"+str(configData.get("-B")[0]))
            else:
                self.c.setOption("-B512") # Liberal Buffer

            #self.c.setOption("-j "+str(self.getSysCores())) # EXPERMENTAL, see if it works!!

            if "-b" in configData:
                self.c.setOption("-b"+str(configData.get("-b")[0]))
            self.c.setOption("--realtime")
            self.c.setOption("-+rtaudio=alsa") # Set option for Csound
            #self.c.setOption("-+rtaudio=jack") # FOR JACK!!!

            if debug is True:
                self.c.setOption("-m7")
            else:
                self.c.setOption("-m0")  # Set option for Csound
                self.c.setOption("-d")
            self.c.compileOrc(self.orc_handle.curOrc)     # Compile Orchestra from String
            self.startMark("compileOrc")
            self.c.readScore(self.orc_handle.curSco)     # Read in Score generated from notes
            self.startMark("readScore")
            self.c.start() # Start Csound
            self.startMark("start (global code incl. filepeak, audio card open)")
            self.c_handle = ch.ControlHandler(self.c, self.orc_handle.numFiles(), configData, self.new_instr, bank=self.new_bank) # Create handler for all csound comm.
            self.startMark("ControlHandler")
            self.loadUI()
            self.startMark("UI")
            threads = set(os.listdir("/proc/self/task"))
            self.pt = ctcsound.CsoundPerformanceThread(self.c.csound()) # Create CsoundPerformanceThread
            self.setRealtime(set(os.listdir("/proc/self/task")) - threads)
            self.c_handle.setCsoundPerformanceThread(self.pt)
            self.pt.play() # Begin Performing the Score in the perforamnce thread
            self.startMark("play")
            self.watchScoreStart()
            nebmixer.init()
            nebmixer.enable()
            self.c_handle.updateAll() # Update all values to ensure their at their initial state.
            if reset_settings_flag == True:
                self.classlog.info("Changing Instr File -- Resetting Secondary Settings")
                self.c_handle.restoreAltToDefault()
        except Exception as e:
            self.classlog.error("Error in start(): %s", e)

    def run(self):
        try:
            new_instr = None
            request = False
            if self.first_run == False:
                self.c_handle.restoreAltToDefault()
            profile = loopprofile.LoopProfile(self.classlog)
            while (self.pt.status() == 0): # Run a loop to poll for messages, and handle the UI.
                self.ui.update()
                self.c_handle.updateAll()
                profile.tick()
                if debug_controls == True:
                    if time.time() - self.last_debug_print > 0.25:
                        self.last_debug_print = time.time()
                        self.c_handle.printAllControls()
                request = self.ui.getReloadRequest()
                if request == True:
                    self.cleanup()
            nebmixer.disable()
            if request == True:
                self.first_run = False
                self.classlog.info("Received Reload Request from UI")
                self.classlog.info("index of new instr is: %s", str(self.c_handle.instr_sel_idx))
                self.new_instr = self.ui.getNewInstr()
                self.classlog.info("new instr: %s", self.new_instr)
                self.new_bank = self.c_handle.getInstrSelBank() 
                self.classlog.info("new bank: %s", self.new_bank)
                self.c.cleanup()
                self.ui.reload_flag = False
                self.classlog.info("Reloading %s from %s", self.new_instr, self.new_bank)
                # Store bank/instr to config
                self.writeBootInstr()
                # Get bank/instr from factory
                if self.new_bank == "puredata":
                    self.start_puredata(self.new_instr)
                    self.run_puredata()
                elif self.new_bank == "supercollider":
                    self.start_supercollider(self.new_instr)
                    self.run_supercollider()
                elif self.new_bank == "programs":
                    self.start_programs(self.new_instr)
                    self.run_programs()
                else:
                    self.c.reset()
                    self.start(self.new_instr, self.new_bank)
                    self.run()
            else:
                self.classlog.info("Run Loop Ending.")
                self.cleanup()
                self.classlog.info("Goodbye!")
                sys.exit()
        except Exception as e:
            self.classlog.error("Error in run(): %s", e)

    def cleanup(self):
        try:
            self.classlog.info("Cleaning Up")
            self.pt.stop()
            self.pt.join()
        except Exception as e:
            self.classlog.error("Error in cleanup(): %s", e)

    # The jack line lets startup.sh start jackd (and sclang scsynth) early.
    def writeBootInstr(self, jack=None):
        try:
            text = 'bank,' + self.new_bank + '\n' + 'instr,' + self.new_instr + '\n'
            if jack is not None:
                text += 'jack,%d-%d-%d\n' % jack
            try:
                if textfile.read(self.instr_cfg) == text:
                    return
            except OSError:
                pass
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
            with open(self.instr_cfg, 'w', encoding="utf-8") as f:
                self.classlog.debug("bootinstr: %s", text.replace('\n', ' '))
                f.write(text)
                #TODO: uncomment, maybe dead code. Do testing and see what happens. If working, remove. If now uncomment.
                #for line in f:
                #    templist = line.strip().split(',')
                #    if templist[0] == 'bank':
                #        self.new_bank = templist[1]
                #    elif templist[0] == 'instr':
                #        self.new_instr = templist[1] 
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")
        except Exception as e:
            self.classlog.error("Could not write config file: %s", e)

    def wait_on_jack(self):
        pass #maybe take this and fill in of a old commit.

    # The stock rpi-proto driver plays only 48000 at the right speed; the
    # patched one (Resources/kernel/0002-*) runs all four.
    PROTO_VERSION_FILE = "/sys/module/snd_soc_rpi_proto/version"
    PROTO_RATES = (8000, 32000, 48000, 96000)

    def jackRates(self):
        try:
            with open(self.PROTO_VERSION_FILE) as f:
                if f.read().strip() == "nebulae-rates-1":
                    return self.PROTO_RATES
        except OSError:
            pass
        return (nebconfig.DEFAULT_SAMPLE_RATE,)

    # (period, periods, rate); the rate snapped to one the card runs.
    def jackSettings(self, instr, config):
        settings = []
        for read, default in ((config.blockSize, nebconfig.DEFAULT_BLOCK_SIZE),
                              (config.nPeriods, nebconfig.DEFAULT_NPERIODS),
                              (config.sampleRate, nebconfig.DEFAULT_SAMPLE_RATE)):
            try:
                settings.append(read())
            except ValueError as e:
                self.classlog.warning("%s: %s, using %d", instr, e, default)
                settings.append(default)
        rates = self.jackRates()
        wished = settings[2]
        settings[2] = min(rates, key=lambda r: (abs(r - wished), -r))
        if settings[2] != wished:
            self.classlog.warning("%s: -r %d is not possible on this card (%s): using %d",
                                  instr, wished, ", ".join(str(r) for r in rates), settings[2])
        return tuple(settings)

    @staticmethod
    def jackUnit(settings):
        return "jack@%d-%d-%d.service" % settings

    def runningJack(self):
        try:
            out = subprocess.run(["systemctl", "list-units", "--plain", "--no-legend",
                                  "--state=active", "jack@*.service"],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 universal_newlines=True).stdout
            for line in out.splitlines():
                unit = line.split()[0] if line.split() else ""
                if unit.startswith("jack@") and unit.endswith(".service"):
                    values = [int(v) for v in unit[len("jack@"):-len(".service")].split("-")]
                    defaults = [None, nebconfig.DEFAULT_NPERIODS, nebconfig.DEFAULT_SAMPLE_RATE]
                    return tuple(values[:3] + defaults[len(values):])
        except Exception as e:
            self.classlog.error("Error in runningJack(): %s", e)
        return None

    def start_jack(self, settings):
        try:
            running = self.runningJack()
            if running == settings:
                return
            if running is not None or os.system("pgrep jackd > /dev/null 2>&1") == 0:
                self.classlog.info("jackd %s -> %s: restarting jackd",
                                   self.jackUnit(running) if running else "running", self.jackUnit(settings))
                self.quit_scsynth()
                self.stop_jack()
                self.wait_for_jack_to_die()
            self.classlog.debug("starting %s", self.jackUnit(settings))
            os.system("systemctl start %s" % self.jackUnit(settings))
        except Exception as e:
            self.classlog.error("Error in start_jack(): %s", e)

    # A scsynth killed by jackd is never rebooted by sclang: the next SC
    # instrument would stay silent.
    def quit_scsynth(self):
        try:
            if subprocess.call(["pgrep", "-x", "scsynth"], stdout=subprocess.DEVNULL) != 0:
                return
            self.classlog.info("scsynth still runs on jackd: asking sclang to quit it")
            address = b"/neb/quit\0\0\0"
            message = address + b",i\0\0" + struct.pack(">i", 0)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(message, ("127.0.0.1", 3010))
            sock.close()
            for _ in range(50):
                if subprocess.call(["pgrep", "-x", "scsynth"], stdout=subprocess.DEVNULL) != 0:
                    return
                time.sleep(0.1)
            self.classlog.warning("scsynth did not quit within 5 s")
        except Exception as e:
            self.classlog.error("Error in quit_scsynth(): %s", e)

    def stop_jack(self):
        os.system("systemctl stop 'jack@*.service'")

    def leave_jack(self):
        self.quit_scsynth()
        self.stop_jack()
        self.wait_for_jack_to_die()

    def wait_for_jack_to_start(self):
        try:
            count = 0
            while subprocess.call(
                "pgrep jackd", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ) != 0:
                count += 1
                if count > 25:
                    raise TimeoutError("jackd did not start within 5 seconds")
                time.sleep(0.2)
                self.classlog.debug("waiting for jackd to start...")
            self.classlog.debug("jackd is now running!!!!")
        except Exception as e:
            self.classlog.error("Error in wait_for_jack_to_start(): %s", e)


    def wait_for_jack_to_die(self):
        try:
            count = 0
            while subprocess.call(
                "pgrep jackd", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ) == 0:
                count += 1
                if count > 10:
                    self.stop_jack()
                    raise TimeoutError("jackd did not die within 2 seconds")
                time.sleep(0.2)
                self.classlog.debug("jackd has not died yet...")
        except Exception as e:
            self.classlog.error("Error in wait_for_jack_to_die(): %s", e)

    def start_supercollider(self, patch, fromSC=False):
        try:
            self.classlog.info("start_supercollider!!!!!")
            self.launch_bootled()
            
            ##if csound is still alive
            if self.c is not None:
                self.c.cleanup()
                self.c = None

            self.currentInstr = patch
            self.newInstr = patch

            fullPathTmp = nebconfig.instrumentPath("supercollider", patch)
            floader = fileloader.FileLoader()
            fullPath = floader.copyFileInternaly(fullPathTmp,"/tmp/") #this remove bug if patch will be removed with floader.reload()
            self.kill_bootled()
            floader.reload()
            self.launch_bootled()
            if not os.path.exists(fullPathTmp):
                fullPath = floader.copyFileInternaly(fullPath, nebconfig.instrumentDir("supercollider")) #if no new file, copy it back
            else:
                fullPath = fullPathTmp

            self.orc_handle.refreshFileHandler() #also the audio files

            reuseResources = fromSC and isinstance(self.c_handle, chSC.SCControlHandler)
            scConfig = nebconfig.NebConfig.read("supercollider", patch)
            self.kernelSwitch(patch, scConfig)
            jack = self.jackSettings(patch, scConfig)
            if reuseResources and self.runningJack() not in (None, jack):
                self.classlog.info("%s wants %s: restarting scsynth", patch, self.jackUnit(jack))
                self.close_sc()
                reuseResources = False
            self.writeBootInstr(jack)
            self.start_jack(jack)
            self.wait_for_jack_to_start()
            scConfigData = scConfig.asDict()
            scConfigData['output_period'] = [scConfig.outputPeriod()]
            scConfigData['holdwithtrigg_combos'] = scConfig.holdWithTriggCombos()
            if not reuseResources:
                self.classlog.info("init SuperCollider handle")
                self.c_handle = chSC.SCControlHandler(None, self.orc_handle.numFiles(), scConfigData, self.new_instr, bank="supercollider")
                self.c_handle.startScOscServer()
                self.c_handle.setCsoundPerformanceThread(None)
                self.st = None #just to be sertain.
            self.c_handle.setConfig(scConfig, self.pagesPath("supercollider", patch))

            self.c_handle.enterSuperColliderMode()
            self.classlog.info("Load patch!")
            #self.kill_bootled() #maybe warning is because scsynth starts??? Moved here
            self.c_handle.loadScSynth(fullPath)
            self.c_handle.startRawEncoders()
            
            self.kill_bootled()

            
            self.loadUI()
            self.c_handle.sendScOscMessages()
            self.c_handle.updateAll() # Update all values to ensure their at their initial state.
            nebmixer.init()
            nebmixer.enable()

        except Exception as e:
            self.classlog.error("Error in start_supercollider(): %s", e)

    def start_puredata(self, patch):
        try:
            self.log.spill_basic_info()
            self.c_handle = None
            self.currentInstr = patch
            self.newInstr = patch
            floader = fileloader.FileLoader()
            floader.reload()
            try:
                config = nebconfig.NebConfig.read("puredata", patch)
            except (OSError, ValueError) as e:
                self.classlog.warning("No nebconfig from %s: %s", patch, e)
                config = nebconfig.NebConfig([])
            self.kernelSwitch(patch, config)
            jack = self.jackSettings(patch, config)
            self.writeBootInstr(jack)
            self.quit_scsynth()
            self.start_jack(jack)
            self.orc_handle.refreshFileHandler()
            fullPath = nebconfig.instrumentPath("puredata", patch)
            cmd = "pd -jack -rt -callback -nogui -verbose".split() if debug else "pd -jack -rt -callback -nogui".split()
            for lib in ("else", "cyclone"):
                libDir = "/usr/lib/pd/extra/" + lib
                if os.path.isdir(libDir):
                    cmd += ["-path", libDir, "-lib", lib]
            cmd.append(fullPath)
            
            self.wait_for_jack_to_start()
            
            self.pt = subprocess.Popen(cmd)

            self.wait_for_puredata()
            self.c_handle = chPD.PDControlHandler(None, self.orc_handle.numFiles(), None, self.new_instr, bank="puredata")
            self.c_handle.setCsoundPerformanceThread(None)
            self.c_handle.enterPureDataMode()
            self.loadUI()
            nebmixer.init()
            nebmixer.enable()
        except Exception as e:
            self.classlog.error("Error in start_puredata(): %s", e)

    # Until Pd listens on its netreceive port 3000 (the patch is loaded).
    def wait_for_puredata(self, timeout=2.0):
        start = time.time()
        while time.time() - start < timeout:
            if self.pt.poll() is not None:
                self.classlog.error("PureData exited during startup")
                return
            for path in ("/proc/net/tcp", "/proc/net/tcp6"):
                try:
                    with open(path) as f:
                        for line in f.readlines()[1:]:
                            fields = line.split()
                            # local address ends in :0BB8 (port 3000), state 0A = LISTEN
                            if fields[1].endswith(":0BB8") and fields[3] == "0A":
                                self.classlog.info("PureData ready after %.2f s", time.time() - start)
                                return
                except OSError:
                    pass
            time.sleep(0.05)
        self.classlog.info("PureData not listening on port 3000 after %.1f s", timeout)

    def run_puredata(self):
        try:
            new_instr = None
            request = False
            self.c_handle.enterPureDataMode()
            profile = loopprofile.LoopProfile(self.classlog)
            while(request != True):
                self.c_handle.updateAll()
                if debug_controls == True:
                    self.c_handle.printAllControls()
                self.ui.update()
                profile.tick()
                request = self.ui.getReloadRequest()
            nebmixer.disable()
            if request == True:
                self.classlog.info("Received Reload Request from UI")
                self.classlog.info("index of new instr is: %s", str(self.c_handle.instr_sel_idx))
                self.new_instr = self.ui.getNewInstr()
                self.new_bank = self.c_handle.getInstrSelBank()
                self.ui.reload_flag = False
                self.classlog.info("Reloading %s from %s", self.new_instr, self.new_bank)
                self.writeBootInstr()
                if self.new_bank == "puredata":
                    self.close_puredata()
                    self.start_puredata(self.new_instr)
                    self.run_puredata()
                elif self.new_bank == "supercollider":
                    self.close_puredata()
                    self.start_supercollider(self.new_instr)
                    self.run_supercollider()
                elif self.new_bank == "programs":
                    self.close_puredata()
                    self.start_programs(self.new_instr)
                    self.run_programs()
                else:
                    self.close_puredata()
                    self.start(self.new_instr, self.new_bank)
                    self.run()
            else:
                self.classlog.info("Run Loop Ending.")
                self.close_puredata()
                self.classlog.info("Goodbye!")
                sys.exit()
        except Exception as e:
            self.classlog.error("Error in run_puredata(): %s", e)

    def run_supercollider(self):
        try:
            request = False
            profile = loopprofile.LoopProfile(self.classlog)
            while(request != True):
                self.c_handle.updateAll()
                self.ui.update()
                profile.tick()
                request = self.ui.getReloadRequest()
            nebmixer.disable()
            if isinstance(self.c_handle, chSC.SCControlHandler):
                self.c_handle.setRawActive(False)
            if request == True:
                self.first_run = False
                self.classlog.info("Received Reload Request from UI")
                self.classlog.info("index of new instr is: %s", str(self.c_handle.instr_sel_idx))
                self.new_instr = self.ui.getNewInstr()
                self.classlog.info("new instr: %s", self.new_instr)
                self.new_bank = self.c_handle.getInstrSelBank()
                self.classlog.info("new bank: %s", self.new_bank)
                self.ui.reload_flag = False
                self.classlog.info("Reloading %s from %s", self.new_instr, self.new_bank)
                self.writeBootInstr()
                if self.new_bank == "puredata":
                    self.close_sc()
                    self.start_puredata(self.new_instr)
                    self.run_puredata()
                elif self.new_bank == "supercollider":
                    self.start_supercollider(self.new_instr,True)
                    self.run_supercollider()
                elif self.new_bank == "programs":
                    self.close_sc()
                    self.start_programs(self.new_instr)
                    self.run_programs()
                else:
                    time.sleep(0.5)
                    self.close_sc()
                    self.start(self.new_instr, self.new_bank)
                    self.run()
            else:
                self.classlog.info("Run Loop Ending.")
                self.close_sc()
                self.classlog.info("Goodbye!")
                sys.exit()
        except Exception as e:
            self.classlog.error("Error in run_supercollider(): %s", e)

    def close_sc(self):
        #os.system("sudo killall sclang")
        #os.system("sudo killall jackd") #chould not be needed but just to be sure
        if isinstance(self.c_handle, chSC.SCControlHandler):
            self.c_handle.closeScSynthProcess()
        self.c_handle.closeSockets()
        self.st = None

    def close_puredata(self):
        try:
            if self.pt is not None:
                self.classlog.info("Terminating PureData process")
                self.pt.terminate()
                self.classlog.info("wait on terminating PureData...")
                timeout = 4.0
                start = time.time()
                while self.pt.poll() is None:
                    if time.time() - start > timeout:
                        self.classlog.error(
                            "PureData did not terminate in time, killing"
                        )
                        self.pt.kill()
                        break
                    time.sleep(0.1)
        except Exception as e:
            self.classlog.error("Error in cleanup_puredata(): %s", e)
        os.system("killall pt")
        # nebio has one Pd connection; left open, the next Pd gets no knobs.
        if isinstance(self.c_handle, chPD.PDControlHandler):
            self.c_handle.closeSockets()
        self.pt = None

    def pagesPath(self, bank, name):
        return nebconfig.instrumentDir(bank) + name + encoderpages.PAGES_EXT

    def start_programs(self, name):
        try:
            self.log.spill_basic_info()
            if self.c is not None:
                self.c.cleanup()
                self.c = None
            self.c_handle = None
            self.currentInstr = name
            self.newInstr = name
            floader = fileloader.FileLoader()
            floader.reload()
            config = nebconfig.NebConfig.read("programs", name)
            self.kernelSwitch(name, config)
            jack = self.jackSettings(name, config)
            self.writeBootInstr(jack)
            self.quit_scsynth()
            self.start_jack(jack)
            self.orc_handle.refreshFileHandler()
            bindings, errors = config.oscBindings()
            for error in errors:
                self.classlog.error("%s.prog: %s", name, error)
            try:
                port = config.oscPort()
            except ValueError as e:
                self.classlog.error("%s.prog: %s", name, e)
                port = nebconfig.DEFAULT_OSC_PORT
            self.wait_for_jack_to_start()
            program = config.run()
            if program is None:
                self.classlog.error("%s.prog has no run entry: nothing started", name)
            else:
                cmd = [program, "--port", str(port), nebconfig.instrumentPath("programs", name)]
                if program.endswith(".sh"):
                    cmd.insert(0, "sh")
                elif program.endswith(".py"):
                    cmd.insert(0, "python3")
                elif os.path.isfile(program) and not os.access(program, os.X_OK):
                    os.chmod(program, 0o755)
                self.classlog.info("Starting %s", " ".join(cmd))
                self.prog = subprocess.Popen(cmd)
            self.c_handle = chProg.ProgControlHandler(None, self.orc_handle.numFiles(), None, self.new_instr,
                                                      bank="programs", oscPort=port, bindings=bindings)
            self.c_handle.setConfig(config, self.pagesPath("programs", name))
            self.c_handle.setCsoundPerformanceThread(None)
            self.c_handle.enterProgramsMode()
            self.loadUI()
            nebmixer.init()
            nebmixer.enable()
        except Exception as e:
            self.classlog.error("Error in start_programs(): %s", e)

    def run_programs(self):
        try:
            request = False
            self.c_handle.enterProgramsMode()
            profile = loopprofile.LoopProfile(self.classlog)
            while(request != True):
                self.c_handle.updateAll()
                self.ui.update()
                profile.tick()
                request = self.ui.getReloadRequest()
            nebmixer.disable()
            if request == True:
                self.classlog.info("Received Reload Request from UI")
                self.new_instr = self.ui.getNewInstr()
                self.new_bank = self.c_handle.getInstrSelBank()
                self.ui.reload_flag = False
                self.classlog.info("Reloading %s from %s", self.new_instr, self.new_bank)
                self.writeBootInstr()
                self.close_programs()
                if self.new_bank == "puredata":
                    self.start_puredata(self.new_instr)
                    self.run_puredata()
                elif self.new_bank == "supercollider":
                    self.start_supercollider(self.new_instr)
                    self.run_supercollider()
                elif self.new_bank == "programs":
                    self.start_programs(self.new_instr)
                    self.run_programs()
                else:
                    self.start(self.new_instr, self.new_bank)
                    self.run()
            else:
                self.classlog.info("Run Loop Ending.")
                self.close_programs()
                self.classlog.info("Goodbye!")
                sys.exit()
        except Exception as e:
            self.classlog.error("Error in run_programs(): %s", e)

    def close_programs(self):
        try:
            if self.prog is not None:
                self.classlog.info("Stopping the program")
                self.prog.terminate()
                try:
                    self.prog.wait(timeout=4.0)
                except subprocess.TimeoutExpired:
                    self.classlog.error("The program did not stop in time, killing it")
                    self.prog.kill()
                    self.prog.wait()
        except Exception as e:
            self.classlog.error("Error in close_programs(): %s", e)
        if isinstance(self.c_handle, chProg.ProgControlHandler):
            self.c_handle.closeSockets()
        self.prog = None

    def loadUI(self):
        try:
            self.classlog.info("Killing LED program")
            cmd = "pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
            os.system(cmd)
            if self.ui is None:
                configSettings.applyAtStart()
                self.ui = ui.UserInterface(self.c_handle)
            else:
                self.ui.controlhandler = self.c_handle
                self.ui.clearAllLEDs()
            self.c_handle.setInstrSelBank(self.new_bank)
            self.ui.setCurrentInstr(self.new_instr)
        except Exception as e:
            self.classlog.error("Error in loadUI(): %s", e)

    def launch_bootled(self):
        try:
            self.classlog.info("Starting loading LED animation")
            nebio.led_animation("loading", "rainbow")
        except Exception as e:
            self.classlog.error("Error in launch_bootled(): %s", e)

    def kill_bootled(self):
        try:
            self.classlog.info("Stopping loading LED animation")
            nebio.led_animation_stop()
        except Exception as e:
            self.classlog.error("Error in kill_bootled(): %s", e)

### NEBULAE ###
try:
    app = Nebulae()
    if app.new_bank == "puredata":
        app.start_puredata(app.new_instr)
        app.run_puredata()
    elif app.new_bank == "supercollider":
        app.start_supercollider(app.new_instr)
        app.run_supercollider()
    elif app.new_bank == "programs":
        app.start_programs(app.new_instr)
        app.run_programs()
    else:
        app.start(app.new_instr, app.new_bank)
        app.run()
except Exception:
    ClassLogger.logCrash("Unhandled error in main execution")