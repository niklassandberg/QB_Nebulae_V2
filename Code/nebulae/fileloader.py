import glob
import os
from classlogger import ClassLogger
from configsettings import configSettings
import neb_globals
import shutil
#import shutil

import endtimer
import nebconfig
import nebio

USB_POWER = "bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh"

# Saved values next to an instrument. A USB load never erases them; the
# stick's copy replaces them only when it is new or changed (STATE_RECORD).
STATE_EXTS = (".pages", ".state")
STATE_TYPES = {"sc": ".scd", "prog": ".prog"}
STATE_RECORD = ".stick_states"

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
        self.scripttypes = [".sh", ".neb"]
        self.progtypes = [".prog"]
        self.othertypes = [".c", ".cpp", ".cc"]
        self.dirs = [ "audio", "instr", "pd", "sc", "scripts", "prog", "csound", "other"]
        self.dirtypes = {}
        self.dirtypes["audio"] = self.audiotypes
        self.dirtypes["instr"] = self.instrtypes
        self.dirtypes["pd"] = self.pdtypes
        self.dirtypes["csd"] = self.csdtypes
        self.dirtypes["sc"] = self.scdtypes
        self.dirtypes["scripts"] = self.scripttypes
        self.dirtypes["prog"] = self.progtypes
        self.dirtypes["other"] = self.othertypes
        self.usb_mounted = self.isUSBMounted()
        self.led_process = None

    def update(self):
        if self.currentState < self.numStates: 
          # do state step 
          if self.currentState != "idling":
              self.stateFunctions[self.currentState]
              self.currentState += 1
    
    # Same names, sizes and mtimes as on the stick.
    def typeIsCurrent(self, fileType):
        fullDir = "/home/alarm/" + fileType
        try:
            local = set(f for f in os.listdir(fullDir) if not self.keepLocal(fileType, f))
            usb = self.typeFiles(fileType)
            if local != set(os.path.basename(f) for f in usb):
                return False
            for f in usb:
                s = os.stat(f)
                d = os.stat(os.path.join(fullDir, os.path.basename(f)))
                if s.st_size != d.st_size or int(s.st_mtime) != int(d.st_mtime):
                    return False
            return not self.changedStates(fileType, usb)
        except OSError:
            return False

    def keepLocal(self, fileType, name):
        return name.startswith('.') or (fileType in STATE_TYPES and name.endswith(STATE_EXTS))

    def changedStates(self, fileType, usb):
        ext = STATE_TYPES.get(fileType)
        if ext is None:
            return []
        record = self.readStateRecord(fileType)
        changed = []
        for f in usb:
            if not f.endswith(ext):
                continue
            for state_ext in STATE_EXTS:
                state = f[:-len(ext)] + state_ext
                if os.path.isfile(state):
                    st = os.stat(state)
                    if record.get(os.path.basename(state)) != (st.st_size, int(st.st_mtime)):
                        changed.append(state)
        return changed

    def readStateRecord(self, fileType):
        record = {}
        try:
            with open(os.path.join("/home/alarm", fileType, STATE_RECORD)) as f:
                for line in f:
                    parts = line.split()
                    if len(parts) == 3:
                        record[parts[0]] = (int(parts[1]), int(parts[2]))
        except (OSError, ValueError):
            pass
        return record

    def copyStates(self, fileType, usb, fullDir):
        changed = self.changedStates(fileType, usb)
        if not changed:
            return
        record = self.readStateRecord(fileType)
        for f in changed:
            try:
                self.copyFile(f, fullDir)
                st = os.stat(f)
                record[os.path.basename(f)] = (st.st_size, int(st.st_mtime))
                self.classlog.info("Saved values from the stick: %s", os.path.basename(f))
            except OSError as e:
                self.classlog.error("Could not copy %s: %s", f, e)
        try:
            with open(os.path.join(fullDir, STATE_RECORD), "w") as out:
                for name, (size, mtime) in sorted(record.items()):
                    out.write("%s %d %d\n" % (name, size, mtime))
        except OSError as e:
            self.classlog.error("Could not write %s: %s", STATE_RECORD, e)

    def copyFile(self, f, fullDir):
        dest = shutil.copy2(f, fullDir)
        fd = os.open(dest, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return dest

    def typeFiles(self, fileType):
        files = []
        for ext in self.dirtypes[fileType]:
            files.extend(glob.glob('/mnt/memory/*' + ext))
        if fileType == "prog":
            files.extend(self.progRunFiles(files))
        return files

    # A binary has no extension: it comes along with the .prog that runs it.
    def progRunFiles(self, progs):
        runs = []
        for prog in progs:
            try:
                run = nebconfig.NebConfig.readFile(prog).value("run")
            except (OSError, ValueError) as e:
                self.classlog.error("Could not read %s: %s", prog, e)
                continue
            run = run.strip() if run else ""
            path = os.path.join('/mnt/memory', run)
            if run and "/" not in run and os.path.isfile(path) and path not in runs:
                runs.append(path)
        return runs
    
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
            changed = [ft for ft in ("audio", "instr", "pd", "sc", "scripts", "prog")
                       if self.typeFiles(ft) and not self.typeIsCurrent(ft)]
            if changed:
                self.launch_bootled(1)
                for ft in changed:
                    self.copyType(ft)
                self.classlog.info("Modified content: %s", ", ".join(changed))
            else:
                self.classlog.info("No modified content.")
            self.umount(sync=False)
            self.classlog.info("Time it took: %s", t.end())
        #why self.launch_bootled when right after kill it?
        #else: 
        #    self.launch_bootled(0)
        if self.led_process is not None:
            nebio.led_animation_stop()
            self.led_process = None
        if neb_globals.remount_fs is True:
            os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")

    def mount(self):
        self.classlog.info("Mounting USB Device")
        os.system(USB_POWER + " on")
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
            os.system(USB_POWER + " off")

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
                if not self.keepLocal(fileType, f) and os.path.isfile(path):
                    os.remove(path)
            for f in files:
                try:
                    dest = self.copyFile(f, fullDir)
                    if fileType == "prog" and not dest.endswith(".prog"):
                        os.chmod(dest, 0o755)
                except OSError as e:
                    self.classlog.error("Could not copy %s: %s", f, e)
            self.copyStates(fileType, files, fullDir)
            fd = os.open(fullDir, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


    def getState(self):
        return self.currentState

    def launch_bootled(self, mode):
        self.classlog.info("Starting loading LED animation")
        if mode == 0:
            nebio.led_animation("loading")
        else:
            nebio.led_animation("loadingusb")
        self.led_process = True
