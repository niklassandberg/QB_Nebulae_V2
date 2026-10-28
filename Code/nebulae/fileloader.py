import glob
import os
from classlogger import ClassLogger
from configsettings import configSettings
import neb_globals
import shutil
#import shutil

import endtimer
import nebio

USB_POWER = "bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh"

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
        self.scripttypes = [".sh", ".neb"]  # configsettings page (scripts.py); .neb = executable
        self.othertypes = [".c", ".cpp", ".cc"]
        self.dirs = [ "audio", "instr", "pd", "sc", "scripts", "csound", "other"]
        self.dirtypes = {}
        self.dirtypes["audio"] = self.audiotypes
        self.dirtypes["instr"] = self.instrtypes
        self.dirtypes["pd"] = self.pdtypes
        self.dirtypes["csd"] = self.csdtypes
        self.dirtypes["sc"] = self.scdtypes
        self.dirtypes["scripts"] = self.scripttypes
        self.dirtypes["other"] = self.othertypes
        self.usb_mounted = self.isUSBMounted()
        self.led_process = None

    def update(self):
        if self.currentState < self.numStates: 
          # do state step 
          if self.currentState != "idling":
              self.stateFunctions[self.currentState]
              self.currentState += 1
    
    # A type is up to date when /home/alarm/<type> holds exactly the stick's
    # files with the same size and mtime (copy2 keeps the mtime). Unlike the
    # old in-memory hash of the whole stick this survives a reboot, and
    # neb_log.txt (appended at every start) no longer counts as a change.
    def typeIsCurrent(self, fileType):
        fullDir = "/home/alarm/" + fileType
        try:
            local = set(f for f in os.listdir(fullDir) if not f.startswith('.'))
            usb = self.typeFiles(fileType)
            if local != set(os.path.basename(f) for f in usb):
                return False
            for f in usb:
                s = os.stat(f)
                d = os.stat(os.path.join(fullDir, os.path.basename(f)))
                if s.st_size != d.st_size or int(s.st_mtime) != int(d.st_mtime):
                    return False
            return True
        except OSError:
            return False

    def typeFiles(self, fileType):
        files = []
        for ext in self.dirtypes[fileType]:
            files.extend(glob.glob('/mnt/memory/*' + ext))
        return files
    
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
            changed = [ft for ft in ("audio", "instr", "pd", "sc", "scripts")
                       if self.typeFiles(ft) and not self.typeIsCurrent(ft)]
            if changed:
                self.launch_bootled(1)
                for ft in changed:
                    self.copyType(ft)
                self.classlog.info("Modified content: %s", ", ".join(changed))
            else:
                self.classlog.info("No modified content.")
            # copyType() flushes what it copied; a global sync waited for
            # all other boot-time writes too (5 s seen).
            self.umount(sync=False)
            self.classlog.info("Time it took: %s", t.end())
        #why self.launch_bootled when right after kill it?
        #else: 
        #    self.launch_bootled(0)
        if self.led_process is not None:
            # Stop the USB loading animation
            nebio.led_animation_stop()
            self.led_process = None
        if neb_globals.remount_fs is True:
            os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")

    def mount(self):
        self.classlog.info("Mounting USB Device")
        os.system(USB_POWER + " on")  # quiet mode switches USB off between uses
        os.system("mount /dev/sda1 /mnt/memory")
        self.usb_mounted = self.isUSBMounted()

    def umount(self, sync=True):
        self.classlog.info("Unmounting USB Device")
        os.system("umount /dev/sda1" )
        if sync:
            self.classlog.info("Sync filebuffers to disk.")
            os.system("sync")
        self.usb_mounted = self.isUSBMounted()
        if configSettings.servicesQuiet:
            os.system(USB_POWER + " off")  # quiet mode: USB only on while in use

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
        files = self.typeFiles(fileType)
        if len(files) > 0:
            fullDir = "/home/alarm/" + fileType
            os.makedirs(fullDir, exist_ok=True)
            self.classlog.info("Erasing " + fullDir)
            for f in os.listdir(fullDir):
                path = os.path.join(fullDir, f)
                if not f.startswith('.') and os.path.isfile(path):
                    os.remove(path)
            for f in files:
                try:
                    dest = shutil.copy2(f, fullDir)  # keeps the mtime for typeIsCurrent()
                    fd = os.open(dest, os.O_RDONLY)
                    try:
                        os.fsync(fd)  # on the SD card even if the power is cut
                    finally:
                        os.close(fd)
                except OSError as e:
                    self.classlog.error("Could not copy %s: %s", f, e)
            fd = os.open(fullDir, os.O_RDONLY)
            try:
                os.fsync(fd)  # the new directory entries
            finally:
                os.close(fd)


    def getState(self):
        return self.currentState

    # Runs inside nebio (same look as bootleds.py), no second LED process.
    def launch_bootled(self, mode):
        self.classlog.info("Starting loading LED animation")
        if mode == 0:
            nebio.led_animation("loading")
        else:
            nebio.led_animation("loadingusb")
        self.led_process = True # animation running, stopped at the end of reload()
