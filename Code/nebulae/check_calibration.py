#!/usr/bin/env python3
import os
from subprocess import Popen
import switch
import sys
import neb_globals
import time

def launch_bootled():
    cmd = "pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
    os.system(cmd)
    print("Launching LED program")
    fullCmd = "python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py calibration"
    led_process = Popen(fullCmd, shell=True)
    print('led process created: ' + str(led_process))
 
def kill_bootled():
    cmd = "pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
    os.system(cmd)


led_process = None

if len(sys.argv) > 1:
    arg = sys.argv[1]
else:
    arg = None
pitch_click = switch.Switch(22) # Pitch Encoder Click GPIO
pitch_click.update()
# 'force': calibrate + factory reset (firmware update). 'only': calibrate and
# keep settings and instrument (configsettings page, Code/nebscripts/2_calibrate.sh).
if pitch_click.state() == True or arg == 'force' or arg == 'only':
    launch_bootled()
    #time.sleep(2)
    print('Calibration commencing')
    # Imported and built only when calibrating: a full ControlHandler took
    # ~1 s at every boot. nebio starts from the real pin levels, so the
    # click above is valid without it.
    import calibration_collector
    collector = calibration_collector.CalibrationCollector()
    collector.collect()
if arg == 'only':
    print('Calibration done, settings kept')
elif pitch_click.state() == True or arg == 'force':
    # Clear out settings and factory reset
    if neb_globals.remount_fs is True:
        os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
    cmd = "rm /home/alarm/QB_Nebulae_V2/Code/config/bootinstr.txt"
    os.system(cmd) 
    cmd = "rm /home/alarm/QB_Nebulae_V2/Code/config/nebsettings.txt"
    os.system(cmd) 
    cmd = "rm /home/alarm/QB_Nebulae_V2/Code/config/buffer_cnt.txt"
    os.system(cmd) 
    if neb_globals.remount_fs is True:
        os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")
else:
    print('Skipping Calibration')
kill_bootled()


