# QB_Nebulae_V2

-- Credentials -- 

ssh alarm@192.168.12.1
passw: alarm

sudo passw: root

--  Instruction to do life changes on RPI -- 

Python isn't compiled ahead of time; it reads the .py files when it starts:

1. Edit the file, e.g. nano /home/alarm/QB_Nebulae_V2/Code/nebulae/ui.py. You can do it as alarm, who owns the folder.
2. Restart Nebulae:
sudo systemctl restart nebulae
3. Watch the log for mistakes (a typo shows up here as an error with the line number):
journalctl -u nebulae -f

Python checks at every start whether a .py file has changed, and if so recompiles its cached copy (__pycache__/*.pyc) by itself. You never need to delete anything.

Good to know:
- nebio (C++, Code/nebio/src/) is different: it has to be compiled. The restart does that too: startup.sh runs build_nebio.sh, which rebuilds when a source file has changed. It just takes a little longer.
- SuperCollider classes (NebInterface.sc in /usr/share/SuperCollider/Extensions/): those need sudo systemctl restart sclang.
- A firmware update replaces the whole folder, so changes you made on the Pi are lost at the next update. Copy them back into the repo (or tell me, and I'll fetch them from the Pi) before you build the next firmware.

-- To see heat in rpi (I dont want to install not needed packages) -- 
cat /sys/class/thermal/thermal_zone0/temp | sed 's/\(..\)\(...\)/\1.\2°C/'

-- Alter the usb stick instr so it can be reloaded ---

sudo mkdir -p /tmp/stick && sudo mount /dev/sda1 /tmp/stick
sudo nano /tmp/stick/2_wave_tables.scd   # make your changes and save
sudo umount /tmp/stick

--See buffer under run in jack
sudo journalctl -u 'jack@*' -f -n 0 | grep --line-buffered XRun
#Count xruns in the last 10 minutes:
sudo journalctl -u 'jack@*' --since "10 min ago" | grep -c XRun
--