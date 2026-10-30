# Main Nebulae Source File
import sys
import os
import ctcsound
import controlhandler as ch
import controlhandlerSC as chSC
import controlhandlerPD as chPD
import conductor
import nebconfig
import ui
import fileloader
import time
import logger
import neb_globals
import multiprocessing
import subprocess

import nebmixer
import nebio
import loopprofile
import kernelswitch
from classlogger import ClassLogger
from configsettings import configSettings

# Before the first Csound(): Csound's own signal handlers caught SIGTERM
# without exiting, so "systemctl stop nebulae" (and every reboot) waited
# 90 s for systemd's SIGKILL. With the default action it stops at once.
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
            # Check the config file for last instr
            if os.path.isfile(self.instr_cfg) and os.path.getsize(self.instr_cfg) > 0:
                # Get bank/instr from factory
                with open(self.instr_cfg, 'r') as f:
                    self.classlog.info("Reading bootinstr.txt")
                    for line in f:
                        templist = line.strip().split(',')
                        if templist[0] == 'bank':
                            self.new_bank = templist[1]
                        elif templist[0] == 'instr':
                            self.new_instr = templist[1] 
            else:
                self.new_bank = 'instr'
                instr_path = nebconfig.instrumentDir("instr")
                factory_path = "/home/alarm/QB_Nebulae_V2/Code/instr/"
                if not os.path.isdir(instr_path) or not os.listdir(instr_path):
                    os.makedirs(instr_path, exist_ok=True)
                    os.system("cp " + factory_path + "a_granularlooper.instr " + instr_path)
                instr_files = sorted([f[:-6] for f in os.listdir(instr_path) if f.endswith(".instr")])
                self.new_instr = instr_files[0] if instr_files else 'a_granularlooper'
            self.currentInstr = self.new_instr
            # Check if file exists, else reset to default instr
            if self.new_bank in nebconfig.INSTR_DIRS:
                path = nebconfig.instrumentPath(self.new_bank, self.new_instr)
            else:
                self.classlog.info("bank not recocgnized.")
                self.classlog.info(self.new_bank)
                path = nebconfig.instrumentPath('instr', 'a_granularlooper')
            if os.path.isfile(path) == False:
                # set to default instr
                self.new_bank = 'instr'
                self.new_instr = 'a_granularlooper'
            self.first_run = True
            nebmixer.disable()
            self.last_debug_print = time.time()
        except Exception as e:
            self.classlog.error("Error in __init__: %s", e)

    # Csound's performance thread (it computes and plays every audio block)
    # in real-time priority (SCHED_FIFO, csound_rt_priority in
    # configsettings.py, below jackd's 75): nothing else may interrupt it.
    # At normal priority even the Quiet mode spin loops (SCHED_IDLE) got
    # ~2 ms turns on its core; on a Pi 3 while recording that was constant
    # dropouts (measured 2026-10-24: ~1400 interruptions per 20 s, 1800 to
    # 2000 dropouts per 160 s; with FIFO 0 and 0).
    # new_threads: the thread ids CsoundPerformanceThread() created.
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

    # Kernel per instrument (kernelswitch.py, "kernel,rt" in the instrument's
    # nebconfig): when the running kernel is the wrong one, the Pi restarts
    # into the one this instrument wants. Called after floader.reload(), with
    # the NebConfig the engine then uses (the file is read once). The
    # instrument is not started meanwhile: the loading animation runs until
    # systemd stops Nebulae. If the restart does not come, the instrument
    # starts on this kernel after all.
    def kernelSwitch(self, instr, config):
        if not self.kernel_switch.switchFor(instr, config):
            return
        self.launch_bootled()
        time.sleep(60)
        self.classlog.error("No restart after 60 s: starting %s on this kernel", instr)
        self.kill_bootled()

    def start(self, instr, instr_bank):
        try:
            #somehow jack starts at startup sometimes, just to be sure...
            self.wait_for_jack_to_die()
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
            config = nebconfig.NebConfig.read("instr", instr)
            self.kernelSwitch(instr, config)
            self.orc_handle.generate_orc(instr, instr_bank, config)
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
            self.c.readScore(self.orc_handle.curSco)     # Read in Score generated from notes 
            self.c.start() # Start Csound
            self.c_handle = ch.ControlHandler(self.c, self.orc_handle.numFiles(), configData, self.new_instr, bank=self.new_bank) # Create handler for all csound comm.
            self.loadUI()
            threads = set(os.listdir("/proc/self/task"))
            self.pt = ctcsound.CsoundPerformanceThread(self.c.csound()) # Create CsoundPerformanceThread
            self.setRealtime(set(os.listdir("/proc/self/task")) - threads)
            self.c_handle.setCsoundPerformanceThread(self.pt)
            self.pt.play() # Begin Performing the Score in the perforamnce thread
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

    def writeBootInstr(self):
        try:
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
            with open(self.instr_cfg, 'w') as f:
                self.classlog.debug("bank: %s, instr: %s",self.new_bank,self.new_instr)
                bankstr = 'bank,'+self.new_bank
                instrstr = 'instr,'+self.new_instr
                f.write(bankstr + '\n')
                f.write(instrstr + '\n')
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

    def start_jack(self):
        try:
            if os.system("pgrep jackd > /dev/null 2>&1") != 0:
                self.classlog.debug("jackd is not running, starting service...")
                os.system("systemctl start jack")
        except Exception as e:
            self.classlog.error("Error in start_jack(): %s", e)

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
                    os.system("systemctl stop jack")
                    raise TimeoutError("jackd did not die within 1 second")
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

            self.start_jack()

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
                
            self.wait_for_jack_to_start()

            self.orc_handle.refreshFileHandler() #also the audio files

            # Only an SCControlHandler can be reused (a Csound/PD handler has no
            # SC updateAll() and no OSC listener).
            reuseResources = fromSC and isinstance(self.c_handle, chSC.SCControlHandler)
            scConfig = nebconfig.NebConfig.read("supercollider", patch)
            self.kernelSwitch(patch, scConfig)
            scConfigData = scConfig.asDict()
            scConfigData['output_period'] = [scConfig.outputPeriod()]
            scConfigData['holdwithtrigg_combos'] = scConfig.holdWithTriggCombos()
            if not reuseResources:
                self.classlog.info("init SuperCollider handle")
                self.c_handle = chSC.SCControlHandler(None, self.orc_handle.numFiles(), scConfigData, self.new_instr, bank="supercollider")
                self.c_handle.startScOscServer()
                self.c_handle.setCsoundPerformanceThread(None)
                self.st = None #just to be sertain.
            self.c_handle.setConfig(scConfig) # rawencoder or hybrid speed/pitch, as the .scd declares

            self.c_handle.enterSuperColliderMode()
            self.classlog.info("Load patch!")
            #self.kill_bootled() #maybe warning is because scsynth starts??? Moved here
            self.c_handle.loadScSynth(fullPath)
            self.c_handle.startRawEncoders() # patch is running: sclang takes its rawencoders
            
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
            self.start_jack()
            self.log.spill_basic_info()
            self.c_handle = None
            self.currentInstr = patch
            self.newInstr = patch
            floader = fileloader.FileLoader()
            floader.reload()
            # Pd itself reads the patch; here only its nebconfig (kernel). A
            # patch that is not readable as text still starts (Pd may know).
            try:
                config = nebconfig.NebConfig.read("puredata", patch)
            except (OSError, ValueError) as e:
                self.classlog.warning("No nebconfig from %s: %s", patch, e)
                config = nebconfig.NebConfig([])
            self.kernelSwitch(patch, config)
            self.orc_handle.refreshFileHandler()
            fullPath = nebconfig.instrumentPath("puredata", patch)
            cmd = "pd -jack -rt -callback -nogui -verbose".split() if debug else "pd -jack -rt -callback -nogui".split()
            # Pd libraries (Code/engine_packages/puredata/externals), when installed.
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

    # Waits until Pd listens on its netreceive port (3000, see pdsender.py),
    # i.e. the patch is loaded, instead of a fixed 2 s. At most 2 s (as
    # before, also for a patch without netreceive), or until pd exits.
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
                self.c_handle.setRawActive(False) # give the encoders back to Python
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
        # c_handle is not an SCControlHandler if start_supercollider() failed early
        if isinstance(self.c_handle, chSC.SCControlHandler):
            self.c_handle.closeScSynthProcess()
        self.c_handle.closeSockets()
        self.wait_for_jack_to_die()
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
        os.system("systemctl stop jack")
        self.wait_for_jack_to_die()
        self.pt = None

    def loadUI(self):
        try:
            self.classlog.info("Killing LED program")
            cmd = "pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
            os.system(cmd)
            if self.ui is None:
                # First instrument loaded: the saved Quiet mode and Wi-Fi to
                # the system (both off until now).
                configSettings.applyAtStart()
                self.ui = ui.UserInterface(self.c_handle)
            else:
                self.ui.controlhandler = self.c_handle
                self.ui.clearAllLEDs()
            self.c_handle.setInstrSelBank(self.new_bank)
            self.ui.setCurrentInstr(self.new_instr)
        except Exception as e:
            self.classlog.error("Error in loadUI(): %s", e)

    # The loading animation runs inside nebio (same look as bootleds.py), so
    # no second process writes to the LED driver.
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
    else:
        app.start(app.new_instr, app.new_bank)
        app.run()
except Exception:
    # With the traceback, also when Nebulae() itself failed (no app yet).
    ClassLogger.logCrash("Unhandled error in main execution")