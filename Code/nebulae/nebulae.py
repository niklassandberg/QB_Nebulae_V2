# Main Nebulae Source File
import sys
import os
from subprocess import Popen
import ctcsound
import controlhandler as ch
import conductor
import ui
import fileloader
import time
import logger
import neb_globals

import nebmixer

cfg_path = "/home/alarm/QB_Nebulae_V2/Code/config/"

debug = True 
debug_controls = False

class Nebulae(object):

    def __init__(self):
        if neb_globals.remount_fs is False:
            print("Nebulae is operating in \"Read/Write\" mode.")
            print("Filesystem will not be remounted during operation.")
            os.system("/home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
        print "Nebulae Initializing"
        self.instr_cfg = cfg_path + "bootinstr.txt"
        self.orc_handle = conductor.Conductor() # Initialize Audio File Tables and Csound Score/Orchestra
        #self.currentInstr = "a_granularlooper"
        self.c = None
        self.pt = None 
        self.st = None
        self.ui = None
        self.c_handle = None
        self.led_process = None
        self.log = logger.NebLogger()
        # Check the config file for last instr
        if os.path.isfile(self.instr_cfg) and os.path.getsize(self.instr_cfg) > 0:
            # Get bank/instr from factory
            with open(self.instr_cfg, 'rb') as f:
                print "Reading bootinstr.txt"
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
            print "bank not recocgnized."
            print self.new_bank
            path = 'factory'
        if os.path.isfile(path) == False:
            # set to default instr
            self.new_bank = 'factory'
            self.new_instr = 'a_granularlooper'
        self.first_run = True
        self.last_debug_print = time.time()

    def start(self, instr, instr_bank):
        print "Nebulae Starting"
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
        self.c.setOption("-odac:hw:0,0")  # Set option for Csound
        if configData.has_key("-B"):
            self.c.setOption("-B"+str(configData.get("-B")[0]))
        else: 
            self.c.setOption("-B512") # Liberal Buffer

        if configData.has_key("-b"):
            self.c.setOption("-b"+str(configData.get("-b")[0]))
        self.c.setOption("--realtime")
        self.c.setOption("-+rtaudio=alsa") # Set option for Csound
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
            print("Changing Instr File -- Resetting Secondary Settings")
            self.c_handle.restoreAltToDefault()

    def run(self):
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
                nebmixer.disable()
                self.cleanup()
        if request == True:
            self.first_run = False
            print "Received Reload Request from UI"
            print "index of new instr is: " + str(self.c_handle.instr_sel_idx)
            self.new_instr = self.ui.getNewInstr()
            print "new instr: " + self.new_instr
            self.new_bank = self.c_handle.getInstrSelBank() 
            print "new bank: " + self.new_bank
            self.c.cleanup()
            self.ui.reload_flag = False # Clear Reload Flag
            print "Reloading " + self.new_instr + " from " + self.new_bank
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
            print "Run Loop Ending."
            self.cleanup()
            print "Goodbye!"
            sys.exit()

    def cleanup(self):
        print "Cleaning Up"
        self.pt.stop()
        self.pt.join()

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
        except:
            "Could not write config file."
            
    def start_jack(self):
        if os.system("jack_lsp > /dev/null 2>&1") != 0:
            os.system("killall jackd") #just to be on the safe side.
            time.sleep(1) #short sleep to ensure that jackd is killed
            cmd = "jackd -T -ndefault -R -P75 -dalsa -dhw:0 -p512 -n3 -s -r48000 &"
            #cmd = "jackd &" #TODO: does not pick up jackdrc, dont know why need to fix! 
            os.system(cmd)
            time.sleep(4) #give jack some time to start

    def waitForSynthOrDie(self):
        retries = 0
        while not self.c_handle.synthIsUpStatus():
            print "synth is not up yet, waiting..."
            retries += 1
            if retries > 50:
                print "Timeout waiting for synth to be up!"
                break
            time.sleep(0.1) 

        if retries >= 50 :
            print "synth is not up after 50 retries! Exiting"
            sys.exit(50)
            
    def start_supercollider(self, patch): #start sc with the selected synth
        #self.cleanup_puredata() ##kills pure data
        #self.cleanup()
        self.start_jack()
        
        #testing if it works, find out why this is stupid!!
        #TODO: why do I need todo this, this is stupid. But I dont find in the code why idx is not set properly
        idx = self.c_handle.instr_sel_idx;
        
        if self.c is not None: ##if csound is still alive
            self.c.cleanup() ##kill it
            self.c = None ##set its life to None
        self.c_handle.close()
        self.c_handle = None
        self.currentIntr = patch
        self.newInstr = patch
        floader = fileloader.FileLoader() 
        floader.reload() #reloads all the files to be sure
        self.orc_handle.refreshFileHandler() #also the audio files
        fullPath = "/home/alarm/sc/" + patch +  ".sc"
        if debug == False:
            cmd = "sclang".split()
        else:
            cmd = "sclang".split()

        fullPath = "/home/alarm/sc/" + patch +  ".sc"
        
        cmd.append(fullPath)        
        
        self.st = Popen(cmd)
        #print 'sleeping'
        #time.sleep(2) #todo: what happens if we remove this?
        self.c_handle = ch.ControlHandler(None, self.orc_handle.numFiles(), None, self.new_instr, bank="supercollider") #supercollider controlhandler
        self.c_handle.setCsoundPerformanceThread(None)
        self.c_handle.enterSuperColliderMode() ##enters supercollider mode and boots scsynth
        nebmixer.init()
        nebmixer.enable()
        
        self.c_handle.setInstrSelIdx(idx) #sets the idx properly again
        self.loadUI()

        #self.waitForSynthOrDie()

        #for some reason first init does not send osc messages
        # defore sending osc messages, update all controls
        #self.c_handle.updateAll()
        #self.ui.update()
        #self.c_handle.updateAll()
        #self.ui.update()
        #self.c_handle.sendScOscMessages()

    def start_puredata(self, patch):
        self.log.spill_basic_info()
        #testing if it works, find out why this is stupid!!
        #TODO: why do I need todo this, this is stupid. But I dont find in the code why idx is not set properly
        idx = self.c_handle.instr_sel_idx;
        if self.c is not None:
            self.c.cleanup() 
            self.c = None
        self.c_handle.close()
        self.c_handle = None
        self.currentInstr = patch
        self.newInstr = patch
        floader = fileloader.FileLoader()
        floader.reload()
        self.orc_handle.refreshFileHandler()
        fullPath = "/home/alarm/pd/" + patch + ".pd"
        #cmd = "pd -rt -nogui -verbose -audiobuf 5".split()
        if debug == False:
            cmd = "pd -rt -callback -nogui -audiobuf 5".split()
        else:
            cmd = "pd -rt -callback -nogui -verbose -audiobuf 5".split()
        cmd.append(fullPath)
        self.pt = Popen(cmd)
        print 'sleeping'
        time.sleep(2)
        self.c_handle = ch.ControlHandler(None, self.orc_handle.numFiles(), None, self.new_instr, bank="puredata")
        self.c_handle.setCsoundPerformanceThread(None)
        self.c_handle.enterPureDataMode()
        nebmixer.init()
        nebmixer.enable()

        self.c_handle.setInstrSelIdx(idx) #sets the idx properly again
        self.loadUI()
        

    def run_puredata(self):
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
            print "Received Reload Request from UI"
            print "index of new instr is: " + str(self.c_handle.instr_sel_idx)
            self.new_instr = self.ui.getNewInstr()
            self.new_bank = self.c_handle.getInstrSelBank() 
            self.ui.reload_flag = False # Clear Reload Flag
            print "Reloading " + self.new_instr + " from " + self.new_bank
            self.cleanup_puredata()
            # Store bank/instr to config
            self.writeBootInstr()
            if self.new_bank == "puredata":
                self.start_puredata(self.new_instr)
                self.run_puredata()
            elif self.new_bank == "supercollider":
                self.start_supercollider(self.new_instr)
                self.run_supercollider()
            else:
                self.start(self.new_instr, self.new_bank)
                self.run()
        else:
            print "Run Loop Ending."
            self.cleanup_puredata()
            print "Goodbye!"
            sys.exit()
            
            
    def run_supercollider(self): ##supercollider
        if self.c is not None:
            self.c.cleanup()
            self.c = None
        request = False
        while(request != True):  ##while I have no requests from UI
            self.c_handle.updateAll() ## keep on updating the control values (and sending them to scsynth)
            self.ui.update() #update the UI
            request = self.ui.getReloadRequest() ##check whether I got a UI request to change patch
        if request == True:
            self.first_run = False
            print "Received Reload Request from UI"
            print "index of new instr is: " + str(self.c_handle.instr_sel_idx)
            self.new_instr = self.ui.getNewInstr()
            print "new instr: " + self.new_instr
            self.new_bank = self.c_handle.getInstrSelBank()
            print "new bank: " + self.new_bank
            self.ui.reload_flag = False # Clear Reload Flag
            print "Reloading " + self.new_instr + " from " + self.new_bank
            # Store bank/instr to config
            self.writeBootInstr()
            # Get bank/instr from factory
            if self.new_bank == "puredata":
                self.cleanup_sc()
                self.start_puredata(self.new_instr)
                self.run_puredata()
            elif self.new_bank == "supercollider": #added
                self.cleanup_sc()
                self.start_supercollider(self.new_instr)
                self.run_supercollider()
            else:
                time.sleep(0.5)
                self.cleanup_sc()
                self.start(self.new_instr, self.new_bank)
                self.run()
        else:
            print "Run Loop Ending."
            self.cleanup_sc()
            print "Goodbye!"
            sys.exit()     
            
    def cleanup_sc(self):
        self.st.terminate()
        self.st.kill()
        
        cmd = "sudo killall sclang scsynth" 
        os.system(cmd)
        cmd = "sudo killall jackd"
        os.system(cmd)

       
    def cleanup_puredata(self): 
        self.pt.terminate()
        self.pt.kill()

    def loadUI(self):
        print "Killing LED program"
        cmd = "sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
        os.system(cmd)
        if self.ui is None:
            self.ui = ui.UserInterface(self.c_handle) # Create User Interface
        else:
            self.ui.controlhandler = self.c_handle
            self.ui.clearAllLEDs()
        self.c_handle.setInstrSelBank(self.new_bank)
        self.ui.setCurrentInstr(self.new_instr)

    def launch_bootled(self):
        cmd = "sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
        os.system(cmd)
        print "Launching LED program"
        fullCmd = "python2 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py loading"
        self.led_process = Popen(fullCmd, shell=True)
        print 'led process created: ' + str(self.led_process)


### NEBULAE ###
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
