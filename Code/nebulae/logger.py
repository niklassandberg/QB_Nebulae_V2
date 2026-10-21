import os
import subprocess
from time import gmtime, strftime
import neb_globals

class NebLogger(object):

    def __init__(self):
        self.usb_status = False
        self.write_local = True #requires remount
        self.write_remote = True
        self.system_data = {}
        self.acquireSystemData()
        self.localpath = "/home/alarm/QB_Nebulae_V2/Code/log/neb_log.txt"
        self.remotepath = "/mnt/memory/neb_log.txt"

    def spill_basic_info(self):
        self.check_usb_status()
        if self.write_remote == True:
            self.mount_usb()
            if self.usb_status == True:
                self.write_info(self.remotepath)
                self.unmount_usb()
        if self.write_local == True:
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
            print("Adding to Local Log")
            self.write_info(self.localpath)
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")

    # Written from Python instead of one shell per line (was ~0.5 s per
    # instrument start, mostly gettemp.sh calling the RPi3-only vcgencmd).
    def write_info(self, path):
        ts = self.getTimeStamp() + " --- "
        lines = [ts + key + ", " + value.rstrip() + "\n" for key, value in self.system_data.items()]
        try:
            with open(path, "a") as f:
                f.writelines(lines)
                f.write(self.cpu_data())
        except OSError as e:
            print("Could not write log " + path + ": " + str(e))

    def cpu_data(self):
        # We'll log the cpu temp, and the amount of available memory
        out = ""
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                out += "CPU temp=%.1f'C\n" % (int(f.read()) / 1000.0)
        except (OSError, ValueError):
            pass
        try:
            out += subprocess.run(["free", "-h"], capture_output=True, text=True).stdout
        except OSError:
            pass
        return out

    def check_usb_status(self):
        self.usb_status = False
        with open("/etc/mtab", "r") as f:
            for line in f:
                if "/mnt/memory" in line:
                    self.usb_status = True

    def mount_usb(self):
        self.check_usb_status() 
        if self.usb_status == True:
            print("USB drive is already mounted")
        else:
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
            print("Mounting USB Device")
            # Quiet mode switches USB off between uses. Not switched off after
            # unmount_usb(): the file loader mounts right after, and switches it off.
            os.system("bash /home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh on")
            os.system("mount /dev/sda1 /mnt/memory")
            self.check_usb_status()
            if self.usb_status == True:
                print("USB drive is now mounted.")
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")

    def unmount_usb(self):
        self.check_usb_status() 
        if self.usb_status == False:
            print("USB drive is not mounted")
        else:
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
            print("Unmounting USB Device")
            os.system("umount /dev/sda1")
            self.check_usb_status()
            if self.usb_status == False:
                print("USB drive is now safe to eject.")
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")

    def acquireSystemData(self):
        with open("/home/alarm/QB_Nebulae_V2/Code/config.txt", "r") as f:
            for line in f:
                items = line.split("=")
                if len(items) > 1:
                    self.system_data[items[0]] = items[1]
                else:
                    print("Invalid entry in config.txt:")
                    print(line)

    def getTimeStamp(self):
        return strftime("%a, %d %b %Y %H: %M:%S +0000", gmtime())
        
