#!/usr/bin/env python3
import os
import subprocess
import switch
import sys
import time
import RPi.GPIO as GPIO
import neb_globals

def launch_bootled():
    cmd = "sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
    os.system(cmd)
    print('Launching LED program')
    fullCmd = "python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py wifi pulse"
    led_process = subprocess.Popen(fullCmd, shell=True)
    print('led process created: ' + str(led_process))
 
def kill_bootled():
    cmd = "sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py"
    os.system(cmd)


led_process = None

if len(sys.argv) > 1:
    arg = sys.argv[1]
else:
    arg = None
GPIO.setmode(GPIO.BCM)
speed_click = switch.Switch(26) # Speed Encoder Click GPIO
speed_click.update() 
if speed_click.state() == True or arg == 'force' or neb_globals.wifi_always_on:
    launch_bootled()
    print('starting wifi')
    os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")

    nebwifi_active = subprocess.run(['systemctl', 'is-active', 'nebwifi.service'],
                                    capture_output=True, text=True).stdout.strip() == 'active'
    if not nebwifi_active:
        os.system("systemctl start nebwifi.service")
    if neb_globals.remount_fs is True:
        os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")
    else:
        os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/sys_opt.sh")
        print('Skipping wifi')
kill_bootled()


