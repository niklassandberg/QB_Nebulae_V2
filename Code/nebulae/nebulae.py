# Main Nebulae Source File
import sys
import os
import ctcsound
import controlhandler as ch
import controlhandlerSC as chSC
import conductor
import ui
import fileloader
import time
import logger
import neb_globals
import multiprocessing
import subprocess

import nebmixer
from classlogger import ClassLogger

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
                with open(self.instr_cfg, 'rb') as f:
                    self.classlog.info("Reading bootinstr.txt")
                    for line in f:
                        templist = line.strip().split(',')
                        if templist[0] == 'bank':
                            self.new_bank = templist[1]
                        elif templist[0] == 'instr':
                            self.new_instr = templist[1] 
            else:
                self.new_bank = 'factory'
                self.new_instr = 'a_granularlooper'
            self.currentInstr = self.new_instr
            # Check if file exists, else reset to default instr
            factory_path = "/home/alarm/QB_Nebulae_V2/Code/instr/"
            user_path = "/home/alarm/instr/"
            pd_path = "/home/alarm/pd/"
            sc_path = "/home/alarm/sc/"
            if self.new_bank == 'factory': 
                path = factory_path + self.new_instr + '.instr'
            elif self.new_bank == 'user':
                path = user_path + self.new_instr + '.instr'
            elif self.new_bank == 'puredata':
                path = pd_path + self.new_instr + '.pd'
            elif self.new_bank == 'supercollider':
                path = sc_path + self.new_instr + '.sc'
            else:
                self.classlog.info("bank not recocgnized.")
                self.classlog.info(self.new_bank)
                path = 'factory'
            if os.path.isfile(path) == False:
                # set to default instr
                self.new_bank = 'factory'
                self.new_instr = 'a_granularlooper'
            self.first_run = True
            self.last_debug_print = time.time()
        except Exception as e:
            self.classlog.error("Error in __init__: %s", e)

    def getSysCores(self):
        try:
            return multiprocessing.cpu_count()
        except Exception as e:
            self.classlog.error("Error in getSysCores(): %s", e)
            return 1

    def start(self, instr, instr_bank):
        try:
            #self.start_jack()
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
            self.orc_handle.generate_orc(instr, instr_bank)
            configData = self.orc_handle.getConfigDict()
            
            self.c.setOption("-iadc:hw:0,0")
            self.c.setOption("-odac:hw:0,0") 
            
            #self.c.setOption("-iadc") # FOR JACK!!!
            #self.c.setOption("-odac") # FOR JACK!!!
            
            if configData.has_key("-B"):
                self.c.setOption("-B"+str(configData.get("-B")[0]))
            else: 
                self.c.setOption("-B512") # Liberal Buffer

            #self.c.setOption("-j "+str(self.getSysCores())) # EXPERMENTAL, see if it works!!
            
            if configData.has_key("-b"):
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
            self.pt = ctcsound.CsoundPerformanceThread(self.c.csound()) # Create CsoundPerformanceThread 
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
        self.quit_jack()
        try:
            new_instr = None
            request = False
            if self.first_run == False:
                self.c_handle.restoreAltToDefault()
            while (self.pt.status() == 0): # Run a loop to poll for messages, and handle the UI.
                self.ui.update()
                self.c_handle.updateAll()
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
                bankstr = 'bank,'+self.new_bank
                instrstr = 'instr,'+self.new_instr 
                f.write(bankstr + '\n')
                f.write(instrstr + '\n')
                for line in f:
                    templist = line.strip().split(',')
                    if templist[0] == 'bank':
                        self.new_bank = templist[1]
                    elif templist[0] == 'instr':
                        self.new_instr = templist[1] 
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")
        except Exception as e:
            self.classlog.error("Could not write config file: %s", e)

    def jack_is_running(self):
        try:
            subprocess.check_call(
                ["systemctl", "is-active", "--quiet", "jackd.service"]
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def quit_jack(self):
        try:

            os.system("sudo systemctl stop jackd.service") 

            retries = 0

            while self.jack_is_running():
                self.classlog.info("jack is dying, waiting...")
                retries += 1
                if retries > 50:
                    self.classlog.info("Timeout waiting for jack to die!")
                    break
                time.sleep(0.5)
            if retries >= 50:
                self.classlog.info("jack has not died!")
        except Exception as e:
            self.classlog.error("Error in start_jack(): %s", e)


    def wait_on_jack(self):
        try:
            os.system("sudo systemctl start jackd.service") 
            retries = 0
            while not self.jack_is_running():
                self.classlog.info("jack is not up yet, waiting...")
                retries += 1
                if retries > 50:
                    self.classlog.info("Timeout waiting for jack to be up!")
                    break
                time.sleep(0.2)
            if retries >= 50:
                self.classlog.info("jack is not up after 50 retries!")
            os.system("jack_wait -w")
            self.classlog.debug("jackd is running!!!!")
        except Exception as e:
            self.classlog.error("Error in start_jack(): %s", e)

    def waitForSCisUp(self):
        try:
            retries = 0
            while not self.c_handle.synthIsUpStatus():
                self.classlog.info("synth is not up yet, waiting...")
                retries += 1
                if retries > 50:
                    self.classlog.info("Timeout waiting for synth to be up!")
                    break
                time.sleep(0.5)
            if retries >= 50:
                self.classlog.info("synth is not up after 50 retries!")
                #sys.exit(50)
        except Exception as e:
            self.classlog.error("Error in waitForSynthOrDie(): %s", e)

    def start_supercollider(self, patch, fromSC=False):
        try:
            self.classlog.info("start_supercollider!!!!!")
            nebmixer.disable()

            #start sc with the selected synth
            self.cleanup()
            self.wait_on_jack()
            
            
            if self.c is not None: ##if csound is still alive
                self.c.cleanup() ##kill it
                self.c = None ##set its life to None

            reuseResources = fromSC and self.c_handle is not None and self.st is not None and self.st.poll() is None
            
            if not reuseResources:

                #TODO: EVERY TIME ANYTHING GETS LOADED EVERY FILES GETS MOVED THIS IS STUPID!!!
                # THIS IS A TEST TO SEE HOW LONG EVERYTHING TAKES!!!
                #self.c_handle = None
                self.currentInstr = patch
                self.newInstr = patch
                floader = fileloader.FileLoader()
                floader.reload() #reloads all the files to be sure
                self.orc_handle.refreshFileHandler() #also the audio files

            fullPath = "/home/alarm/sc/" + patch +  ".scd"
            
            if reuseResources:
            #if fromSC and self.c_handle is not None:
                self.classlog.info("SuperCollider and is running in the process, reuse!")
                self.c_handle.loadScSynth(fullPath)
                self.waitForSCisUp()
            else:
                self.classlog.info("Starting SuperCollider process")
                
                my_env = os.environ.copy()
                my_env["C_JACK_DEFAULT_OUTPUTS"] = "system"
                my_env["SC_JACK_DEFAULT_INPUTS"] = "system"
                my_env["JACK_NO_START_SERVER"] = "1"
                command_list = ["sclang", fullPath]
                self.st = subprocess.Popen(command_list, env=my_env)

                #cmd = "sclang".split()
                #cmd.append(fullPath)
                #self.st = subprocess.Popen(cmd)
                
                self.c_handle = chSC.SCControlHandler(None, self.orc_handle.numFiles(), None, self.new_instr, bank="supercollider")
                self.c_handle.setCsoundPerformanceThread(None)
                self.c_handle.lisenOnSCisUpMessage()
                self.waitForSCisUp()
                self.classlog.info("SuperCollider is started.")

            self.c_handle.enterSuperColliderMode()
            self.loadUI()
            self.c_handle.sendScOscMessages()
            self.c_handle.updateAll() # Update all values to ensure their at their initial state.
            nebmixer.init()
            nebmixer.enable()

        except Exception as e:
            self.classlog.error("Error in start_supercollider(): %s", e)

    def start_puredata(self, patch):
        try:
            #self.start_jack()
            self.log.spill_basic_info()
            self.c_handle = None
            self.currentInstr = patch
            self.newInstr = patch
            floader = fileloader.FileLoader()
            floader.reload()
            self.orc_handle.refreshFileHandler()
            fullPath = "/home/alarm/pd/" + patch + ".pd"
            cmd = "pd -rt -callback -nogui -verbose -audiobuf 5".split() if debug else "pd -rt -callback -nogui -audiobuf 5".split()
            cmd.append(fullPath)
            self.pt = subprocess.Popen(cmd)
            self.classlog.info('sleeping')
            time.sleep(2)
            self.c_handle = ch.ControlHandler(None, self.orc_handle.numFiles(), None, self.new_instr, bank="puredata")
            self.c_handle.setCsoundPerformanceThread(None)
            self.c_handle.enterPureDataMode()
            self.loadUI()
            nebmixer.init()
            nebmixer.enable()
        except Exception as e:
            self.classlog.error("Error in start_puredata(): %s", e)

    def run_puredata(self):
        try:
            new_instr = None
            request = False
            self.c_handle.enterPureDataMode()
            while(request != True):
                self.c_handle.updateAll()
                if debug_controls == True:
                    self.c_handle.printAllControls()
                self.ui.update()
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
            while(request != True):
                self.c_handle.updateAll()
                self.ui.update()
                request = self.ui.getReloadRequest()
            nebmixer.disable()
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
                #self.writeBootInstr()
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
        try:
            if self.st is not None:
                self.classlog.info("Terminating SuperCollider process")
                self.st.terminate()
                self.classlog.info("Waiting for SuperCollider to terminate...")

                timeout = 4.0
                start = time.time()
                while self.st.poll() is None:
                    if time.time() - start > timeout:
                        self.classlog.error(
                            "SuperCollider did not terminate in time, killing"
                        )
                        self.st.kill()
                        break
                time.sleep(0.1)
        except Exception as e:
            self.classlog.error("Error in close_sc(): %s", e)
        #os.system("sudo killall sclang")
        #os.system("sudo killall scsynth") 
        #os.system("sudo killall jackd")

    def close_puredata(self):
        try:
            if self.st is not None:
                self.classlog.info("Terminating PureData process")
                self.st.terminate()
                self.classlog.info("wait on terminating PureData...")
                timeout = 4.0
                start = time.time()
                while self.st.poll() is None:
                    if time.time() - start > timeout:
                        self.classlog.error(
                            "PureData did not terminate in time, killing"
                        )
                        self.st.kill()
                        break
                    time.sleep(0.1)
        except Exception as e:
            self.classlog.error("Error in cleanup_puredata(): %s", e)
        #os.system("sudo killall pt")
        #os.system("sudo killall jackd")

    def loadUI(self):
        try:
            self.classlog.info("Killing LED program")
            cmd = "sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
            os.system(cmd)
            if self.ui is None:
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
            cmd = "sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
            os.system(cmd)
            self.classlog.info("Launching LED program")
            fullCmd = "python2 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py loading"
            self.led_process = subprocess.Popen(fullCmd, shell=True)
            self.classlog.info('led process created: %s', str(self.led_process))
        except Exception as e:
            self.classlog.error("Error in launch_bootled(): %s", e)


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
except Exception as e:
    app.classlog.error("Unhandled error in main execution: %s", e)
