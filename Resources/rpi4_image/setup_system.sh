#!/bin/bash
# System setup for a new Nebulae card: Arch Linux ARM aarch64 (RPi4) with the
# linux-rpi kernel, see README.md next to this script.
# Run as root on the Pi, after the firmware is in /home/alarm/QB_Nebulae_V2
# and this folder is in /home/alarm/rpi4_image. Safe to run again.
#
# Not done here (see README.md): the kernel swap, building SuperCollider and
# its UGens, the home Wi-Fi profile (needs the key), user data.
set -e
NEB=/home/alarm/QB_Nebulae_V2
HERE=$(cd "$(dirname "$0")" && pwd)
LF=$NEB/Code/localfiles

echo "== packages"
pacman -S --noconfirm --needed sudo alsa-utils csound dnsmasq hostapd i2c-tools \
    libgpiod liblo netctl dhcpcd pd python python-pip python-cherrypy python-numpy \
    raspberrypi-utils unzip usbutils which wireless_tools iw net-tools dialog \
    dosfstools jack2 git base-devel cmake pkgconf >/dev/null 2>&1
# The Arch csound above pulls in the dependencies; the Nebulae builds
# (Code/engines/: Csound optimised + -B working, SuperCollider) replace
# them, IgnorePkg keeps them.
bash $NEB/Code/scripts/engines_check.sh
# The Nebulae's own SuperCollider classes (NebInterface, MultiWtOsc), as
# update.sh installs them.
if [ -d $NEB/SuperColliderExtensions ]; then
    mkdir -p /usr/share/SuperCollider/Extensions
    for item in $NEB/SuperColliderExtensions/*; do
        rm -rf "/usr/share/SuperCollider/Extensions/$(basename "$item")"
        cp -r "$item" /usr/share/SuperCollider/Extensions/
    done
fi

echo "== host, keymap, time"
echo alarmpi > /etc/hostname
hostnamectl hostname alarmpi 2>/dev/null || true
echo KEYMAP=sv-latin1 > /etc/vconsole.conf
ln -sf /usr/share/zoneinfo/UTC /etc/localtime

echo "== sudo (asks for the root password, as on the old image)"
cat > /etc/sudoers.d/10-nebulae <<'EOF'
Defaults targetpw
%wheel ALL=(ALL:ALL) ALL
EOF
chmod 440 /etc/sudoers.d/10-nebulae
visudo -cq
usermod -aG audio,wheel alarm

echo "== network: Ethernet DHCP + alarmpi.local (mDNS)"
rm -f /etc/systemd/network/en.network /etc/systemd/network/eth.network
cat > /etc/systemd/network/end0.network <<'EOF'
[Match]
Name=end0 eth* en*

[Network]
DHCP=yes
DNSSEC=no
MulticastDNS=yes
EOF
mkdir -p /etc/systemd/resolved.conf.d
printf '[Resolve]\nMulticastDNS=yes\n' > /etc/systemd/resolved.conf.d/nebulae.conf
systemctl enable systemd-networkd systemd-resolved >/dev/null 2>&1
mkdir -p /etc/systemd/system/sshd.service.d
printf '[Unit]\n  After=network-online.target\n  Wants=network-online.target\n' \
    > /etc/systemd/system/sshd.service.d/wait-network.conf

echo "== /boot on first access"
# nebulae.service waits for local-fs.target; /boot's udev device comes late
# (~4.3 s after kernel start), and Nebulae reads /boot only later (startup.sh).
sed -i 's|^\(/dev/mmcblk0p1[[:space:]]\+/boot[[:space:]]\+vfat[[:space:]]\+\)defaults\([[:space:]]\)|\1defaults,x-systemd.automount\2|' /etc/fstab

echo "== journal, modules, udev"
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/nebulae.conf <<'EOF'
# Nebulae: keep the persistent journal small (it had grown to ~1 GB).
[Journal]
SystemMaxUse=50M
EOF
echo i2c-dev > /etc/modules-load.d/raspberrypi.conf
echo "options brcmfmac roamoff=1" > /etc/modprobe.d/brcmfmac.conf
echo 'ACTION=="add", SUBSYSTEM=="net", KERNEL=="wlan0", RUN+="/usr/bin/iw dev wlan0 set power_save off"' \
    > /etc/udev/rules.d/70-wifi-powersave.rules
printf 'SUBSYSTEM=="vchiq|input", MODE="0777"\nKERNEL=="mouse*|mice|event*",  MODE="0777"\n' \
    > /etc/udev/rules.d/raspberrypi.rules

echo "== Nebulae boot files"
install -m 755 -o alarm -g alarm "$HERE/checkfirmware.sh" /home/alarm/checkfirmware.sh
install -m 644 -o alarm -g alarm "$HERE/mandatory_files.txt" /home/alarm/mandatory_files.txt
cat $LF/config.txt > /boot/config.txt
cat $LF/environment > /etc/environment
cat $LF/jackdrc > /etc/jackdrc
mkdir -p /root/.config/SuperCollider
cat $LF/startup.scd > /root/.config/SuperCollider/startup.scd
mkdir -p /mnt/memory /home/alarm/instr /home/alarm/pd /home/alarm/sc /home/alarm/audio \
    /home/alarm/backup/old /home/alarm/backup/new
chown alarm:alarm /home/alarm/instr /home/alarm/pd /home/alarm/sc /home/alarm/audio

echo "== services"
for s in nebulae sclang jack nebwifi; do
    cat $LF/$s.service > /etc/systemd/system/$s.service
done
cat $NEB/Code/web/NebFile/NebFile.service > /etc/systemd/system/NebFile.service
systemctl daemon-reload
systemctl enable nebulae.service >/dev/null 2>&1
# sclang is enabled once SuperCollider is installed (setup builds it later).
if command -v sclang >/dev/null; then systemctl enable sclang.service >/dev/null 2>&1; fi
# Never at boot: jack is started by nebulae.py for the SC/PD banks, the access
# point by the scripts page (1_wifi.ui -> Code/scripts/wifi.sh), NebFile by start_wifi.sh.
systemctl disable jack.service nebwifi.service NebFile.service >/dev/null 2>&1 || true

echo "== Python packages for bootleds.py (leddriver.py)"
pip install --break-system-packages --root-user-action=ignore -q \
    Adafruit-PCA9685 Adafruit-GPIO Adafruit-PureIO RPi.GPIO

chown -R alarm:alarm $NEB
echo "== done"
