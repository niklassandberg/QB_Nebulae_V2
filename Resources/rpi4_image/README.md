# Nebulae RPi4 image: Arch Linux ARM aarch64 (64-bit)

The 64-bit system for the Nebulae (first made 2026-10-22), replacing the old
32-bit (armv7h, kernel 5.15) image.

| File | What |
|---|---|
| `setup_system.sh` | packages + all system configuration (run as root on the Pi; safe to run again) |
| `build_sc.sh` | builds SuperCollider 3.14.1 headless, sc3-plugins and the own UGens (hours) |
| `checkfirmware.sh` | `/home/alarm/checkfirmware.sh`, started by nebulae.service (checks the firmware, runs startup.sh) |
| `mandatory_files.txt` | `/home/alarm/mandatory_files.txt`, the files checkfirmware.sh requires |

## Making a card
1. **Write the base image** (done here from Windows, nothing needed on the Pi):
   - WSL Arch: download `http://os.archlinuxarm.org/os/ArchLinuxARM-rpi-aarch64-latest.tar.gz`
     (+ `.sig`, check with key `68B3537F39A313B3E574D06777193F152BDBE6A6`)
   - make a 6 GB image file: `sfdisk` p1 512 MiB type c, p2 rest; `mkfs.vfat -F 32`,
     `mkfs.ext4`; `bsdtar -xpf` into it; in `etc/fstab` mmcblk0 -> mmcblk1
     (the tarball's mainline kernel calls the SD card mmcblk1)
   - write it raw to the card (elevated PowerShell, `\\.\PhysicalDriveN`), verify.
2. **First boot** (Ethernet, ssh `alarm@<ip>`, password alarm; root password root):
   ```
   pacman-key --init && pacman-key --populate archlinuxarm
   echo ', +' | sfdisk --no-reread -N 2 /dev/mmcblk1 && partx -u /dev/mmcblk1 && resize2fs /dev/mmcblk1p2
   pacman -Syu
   pacman -Sw linux-rpi && pacman -Rdd linux-aarch64 uboot-raspberrypi && pacman -S linux-rpi
   sed -i s/mmcblk1/mmcblk0/ /etc/fstab
   ```
   The Raspberry Pi kernel (`linux-rpi`) is needed for the codec overlay.
   Then `/boot/config.txt` = `Code/localfiles/config.txt` and `/boot/cmdline.txt`:
   `root=/dev/mmcblk0p2 rw rootwait console=serial0,115200 console=tty1 fsck.repair=yes initcall_blacklist=raid6_select_algo`
   (no initramfs needed: ext4 and the SD driver are built in). Reboot.
3. **Firmware + system**: copy the firmware to `/home/alarm/QB_Nebulae_V2` (as
   `create_fw_update.sh` lays it out, Unix line endings, without `Code/packages`)
   and this folder to `/home/alarm/rpi4_image`, then `bash /home/alarm/rpi4_image/setup_system.sh`.
4. **SuperCollider**: copy `Resources/sc_pkg/rpi4/PKGBUILD` next to `build_sc.sh`, then
   `systemd-run --unit=nebulae-scbuild bash /home/alarm/rpi4_image/build_sc.sh`
   (log: `/home/alarm/sc_build/build.log`). It enables sclang.service at the end.
5. **Pure Data libraries** ELSE and cyclone (optional, about an hour: ELSE builds its own ffmpeg):
   `systemd-run --unit=nebulae-pdbuild bash /home/alarm/rpi4_image/build_pd_libs.sh`
   (log: `/home/alarm/pd_build/build.log`). They go to `/usr/lib/pd/extra/else` and `cyclone`;
   nebulae.py loads both (`-path ... -lib ...`) when they are there.

## Differences from the old 32-bit image
- Kernel `linux-rpi` 6.18 (aarch64) instead of 5.15 (armv7h): pacman -Syu is
  allowed again on this image.
- A newer Pi 4 bootloader (EEPROM, ~0.9 s faster start) works with it. The
  image does not carry the EEPROM: on a new Pi, put an empty file
  `update_bootloader` on the USB stick once (see `Resources/bootloader/README.md`).
- The `rpi-proto` overlay is now called `proto-codec`; the firmware loads it
  for `dtoverlay=rpi-proto` (warning in `/proc/device-tree/chosen/user-warnings`).
  `i2s-mmap` no longer exists and is not needed. The card is still `sndrpiproto`, card 0.
- The Pi LEDs are `/sys/class/leds/ACT` and `PWR` (were `led0`, `led1`);
  quiet.sh and noise_test.sh handle both.
- Ethernet is `end0` as before. `alarmpi.local` works through systemd-resolved's
  mDNS (`MulticastDNS=yes`).
- Adafruit_GPIO cannot detect the I2C bus on this platform: leddriver.py passes `busnum=1`.
- checkfirmware.sh: a revert goes back to the previous firmware in
  `/home/alarm/backup/old` (the old script unpacked `neb_factory_fw.zip`, a Python 2
  firmware that cannot run here).
- update.sh installs from `Code/packages` only the packages for this architecture
  (that folder holds old armv7h packages and Python 2 wheels).
- Not carried over: python2, csound 6.11 debug build, openmpi, asp, Pd externals
  (were not installed on the old card either).
