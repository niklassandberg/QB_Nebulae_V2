import glob
import os
import subprocess
from classlogger import ClassLogger
import neb_globals
import shutil
#import shutil

import endtimer

class FileLoader(object):

    #find /mnt/memory -printf '%P %s %T@\n' #gets hash for the last modified, when if differ, copy result. We dont have rsync.
    #if rsync: 
    """
        import subprocess

        USB = "/mnt/usb/DIR2/"
        SD  = "/mnt/sd/DIR1/"

        # 1. Dry-run to see if anything changed
        dry_run = subprocess.call([
            "rsync", "-a", "--delete", "--dry-run", USB, SD
        ])

        if dry_run == 0:
            # dry-run finished, now actually copy
            subprocess.call(["rsync", "-a", "--delete", USB, SD])
    """ 

    contentHash = "" # hash of usb content, must be global internal.

    def __init__(self):
        
        self.classlog = ClassLogger.loggerSetup(self)
        
        self.states = ["reloading", "idling"]
        self.stateFunctions = {}
        self.stateFunctions["idling"] = None
        self.stateFunctions["reloading"] = self.reload
        self.numStates = len(self.states)
        self.currentState = self.states[self.numStates-1]
        self.audiotypes = [ ".wav", ".aif", ".aiff", ".flac"]
        self.instrtypes = [".instr"]
        self.pdtypes = [".pd",".pd_linux"]
        self.csdtypes = [".csd"]
        self.scdtypes = [".scd",".sc"]
        self.othertypes = [".c", ".sh", ".cpp", ".cc"]
        self.dirs = [ "audio", "instr", "pd", "sc", "csound", "other"]
        self.dirtypes = {}
        self.dirtypes["audio"] = self.audiotypes
        self.dirtypes["instr"] = self.instrtypes
        self.dirtypes["pd"] = self.pdtypes
        self.dirtypes["csd"] = self.csdtypes
        self.dirtypes["sc"] = self.scdtypes
        self.dirtypes["other"] = self.othertypes
        self.usb_mounted = self.isUSBMounted()
        self.led_process = None

    def update(self):
        if self.currentState < self.numStates: 
          # do state step 
          if self.currentState != "idling":
              self.stateFunctions[self.currentState]
              self.currentState += 1
    
    def usbHasModContent(self):
        prevContentHash = FileLoader.contentHash
        try:
            output = subprocess.check_output(
                "find /mnt/memory -printf '%P %s %T@\\n' | sort | sha256sum",
                shell=True
            )
            FileLoader.contentHash = output.strip().split()[0]
        except Exception as e:
            self.classlog.error("Error computing USB content hash: %s", e)
            FileLoader.contentHash = ""
        return prevContentHash != FileLoader.contentHash
    
    def copyFileInternaly(self, filepath, destPath):
        if os.path.isfile(filepath) and os.path.isdir(destPath):
            filename = os.path.basename(filepath)
            destFilePath = os.path.join(destPath, filename)
            shutil.copy2(filepath, destFilePath)
            return destFilePath
        else:
            self.classlog.error("Invalid file or destination path, returning original filepath.")
            return filepath 
    
    def reload(self):
        if neb_globals.remount_fs is True:
            os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
        t = endtimer.EndTimer()
        self.mount()
        if self.usb_mounted == True:
            if self.usbHasModContent() == True:
                self.launch_bootled(1)
                self.copyType("audio")
                self.copyType("instr")
                self.copyType("pd")
                self.copyType("sc")
                self.classlog.info("Modified content.")
            else:
                self.classlog.info("No modified content.")
            self.umount()
            self.classlog.info("Time it took: %s", t.end())
        #why self.launch_bootled when right after kill it?
        #else: 
        #    self.launch_bootled(0)
        if self.led_process is not None:
            # Kill Boot LED
            self.led_process.kill()
            self.led_process = None
        if neb_globals.remount_fs is True:
            os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")

    def mount(self):
        self.classlog.info("Mounting USB Device")
        os.system("mount /dev/sda1 /mnt/memory")
        self.usb_mounted = self.isUSBMounted()

    def umount(self):
        self.classlog.info("Unmounting USB Device")
        os.system("umount /dev/sda1" )
        self.classlog.info("Sync filebuffers to disk.")
        os.system("sync")
        self.usb_mounted = self.isUSBMounted()

    def isUSBMounted(self):
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    if "/mnt/memory" in line:
                        return True
        except:
            self.classlog.error("Could not check for mounted drives.")

        return False

    def copyFileToUSB(self, filepath):
        if os.path.isfile(filepath):
            fileDir = '/mnt/memory'
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
            self.mount()
            if self.isUSBMounted():
                cmd = "cp " + filepath + " " + fileDir
                os.system(cmd) 
                self.umount()
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")

    def copyType(self, fileType):
        fileDir = '/mnt/memory'
        files = []
        for ext in self.dirtypes[fileType]:
            files.extend(glob.glob(fileDir + '/*' + ext))
        fileCount = len(files)
        if fileCount > 0:
            fullDir = "/home/alarm/" + fileType
            cmd = "mkdir -p " + fullDir
            os.system(cmd)
            #fullFile = fullDir + "/*" + ext
            self.classlog.info("Erasing " + fullDir)
            cmd = "rm " + fullDir + "/*"
            os.system(cmd)
            self.classlog.info("Contents of " + fullDir + " after erasure:")
            cmd = "ls " + fullDir
            os.system(cmd)
            for f in files:
                #new_f = f.replace(" ", "\ ").replace("\'", "\\\'")
                new_f = '"{0}"'.format(f)
                s = " ".join(["cp", new_f,fullDir])
                os.system(s)
                # shutil implementation
                #fstr = "*"+ ext
                #sstr = "/mnt/memory/"+fstr
                #dstr = fullDir+fstr
                #shutil.copy(sstr, dstr)


    def getState(self):
        return self.currentState

    def launch_bootled(self, mode):
        cmd = "sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
        os.system(cmd)
        self.classlog.info("Launching LED program")
        if mode == 0:
            fullCmd = "python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py loading"
        else:
            fullCmd = "python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py loadingusb"
        self.led_process = subprocess.Popen(fullCmd, shell=True)
        self.classlog.info('led process created: ' + str(self.led_process))
