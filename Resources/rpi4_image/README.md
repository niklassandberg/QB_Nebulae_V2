# Nebulae RPi4 image: Arch Linux ARM aarch64 (64-bit)

The 64-bit system for the Nebulae (first made 2026-10-22), replacing the old
32-bit (armv7h, kernel 5.15) image.

| File | What |
|---|---|
| `setup_system.sh` | packages + all system configuration (run as root on the Pi; safe to run again) |
| `checkfirmware.sh` | `/home/alarm/checkfirmware.sh`, started by nebulae.service (checks the firmware, runs startup.sh) |
| `make_release_image.sh`, `firstboot/` | an image to hand out, from an image of a working card (see below) |
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
   It also installs the audio engines and their plugins from the firmware's
   `Code/engines/` (Csound, SuperCollider + sc3-plugins and UGens, Pure Data +
   cyclone and ELSE; `Code/scripts/engines_check.sh`, see
   `Resources/engines/README.md`) and enables sclang.service. Nothing to build.

## Release image for other users
`make_release_image.sh` makes an image to hand out from an image of a working
card (read the card with Win32 Disk Imager, or a `.img.zst` backup); the card
and the source image are only read. Run as root in WSL:
```
make_release_image.sh --firmware neb_update.zip card.img NebulaeV2-RPI3-<date>.img.xz
```
- small (~7 GB written, fits an 8 GB card); at its first start it grows to
  the whole card (`firstboot/nebulae-firstboot.service`, runs once)
- each card gets its own machine ID and SSH host keys at the first start
  (otherwise every card would be the same Pi: two Nebulae on one network got
  the same IP)
- nothing personal: no authorized_keys, histories, logs, package cache, SC
  build sources, backups, files from the USB stick; Nebulae settings back to
  the factory defaults (no calibration: calibrate on scripts page 2)
- `--firmware`: the firmware from that `neb_update.zip` (`create_fw_update.sh`)
  instead of the card's
- every file is checked against what was meant to go in; `.img.xz` +
  `.sha256`. Write it with Raspberry Pi Imager ("Use custom") or balenaEtcher.
- starts on a Pi 4 and a Pi 3: `/boot/nebulae-image.txt` holds `arm_64bit=1`
  (a Pi 3 otherwise looks for a 32-bit kernel), and `Code/localfiles/config.txt`
  includes it. The old 32-bit image has no such file, so the same firmware
  works there. A release image made before this gets it with
  `make_release_image.sh --pi3 OLD.img[.xz] NEW.img.xz` (copy + this change only).

Login on a release card: `alarm`/`alarm`, root `root` (Arch Linux ARM
defaults; change them with `passwd` if the Nebulae is on a shared network).

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
