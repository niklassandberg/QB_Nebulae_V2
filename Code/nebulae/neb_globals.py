remount_fs = False
wifi_always_on = False

#To not write to known logs so we get even more noice
#sudo systemctl stop systemd-journald.socket systemd-journald-dev-log.socket systemd-journald
#sudo systemctl stop rsyslog 2>/dev/null
#sudo systemctl stop syslog 2>/dev/null
#
#
#What more can I do to remove noise?
#
#To disable all logging permanently, add to /etc/systemd/journald.conf:
#
#  [Journal]
#  Storage=none
#
#  Other things to reduce noise:
#
#  - Mount filesystem read-only — you already do this with mountfs.sh ro, good
#  - Disable swap — swap writes to SD card: sudo swapoff -a
#  - Disable cron — periodic jobs: sudo systemctl stop cronie
#  - Disable timesyncd — NTP syncs periodically: sudo systemctl stop systemd-timesyncd
#
# what is NTP syncs?
# 
# NTP (Network Time Protocol) — it periodically contacts a time server over the network to keep the system clock accurate. Since you're an audio device with   no need for accurate time, you can safely disable it.
# 
# Öhhh, dont supercollider use time?
# 
# SC uses its own internal clock (TempoClock, SystemClock) which runs from the CPU — it doesn't need NTP or system time to be accurate. NTP is only for wall   clock time (date/time of day).
#
# Yes, check sys_opt_lite.sh:
# 
# NTP is already stopped (sudo service ntp stop line 8), and CPU scaling is already set to performance (lines 52-55).
# 
# Things not yet in this script that could help:
# 
# - sudo systemctl stop systemd-timesyncd — replaces NTP on Arch
# - sudo systemctl stop systemd-journald — stop logging
# - sudo swapoff -a — disable swap
# 
# Want me to add these to sys_opt_lite.sh?
