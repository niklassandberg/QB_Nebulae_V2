# Nebulae kernel

A kernel for the Nebulae: Arch Linux ARM's `linux-rpi` (the Raspberry Pi
kernel fork, same source commit and configuration; their files are in
`alarm/`) with `nebulae.config` on top. One kernel for the Pi 3 and the Pi 4.

What `nebulae.config` changes (6.18.58-1 config check, `report.txt`: 1390 options
removed, 37 changed, none added):
- **out**, because the Nebulae does not have it: graphics/HDMI (DRM), cameras
  and video (media), Bluetooth, joysticks/tablets/touchscreens, USB Wi-Fi
  dongle drivers, CAN/NFC/amateur radio/802.15.4, file systems it never sees
  (btrfs, xfs, f2fs, ...). Most of these were modules (only disk space), but
  btrfs, f2fs, joysticks and touchscreens were built into the kernel; with
  btrfs gone, RAID6 and the XOR checksums are no longer built in either, so
  their speed tests at every boot are gone (`raid6_select_algo` was switched
  off by `initcall_blacklist` in cmdline.txt for that reason).
- **the same as stock**, kept so a new stock config cannot change them: full
  kernel preemption (`CONFIG_PREEMPT`; not `PREEMPT_RT`, which costs
  throughput, and Csound already uses most of a core on a Pi 3), no debug info
- **kept**: the codec (I2S, WM8731, proto-codec overlay), SPI/I2C/GPIO,
  Ethernet of both Pis (genet, smsc95xx, lan78xx), the Pi's Wi-Fi (brcmfmac),
  USB audio, USB sticks (vfat, exfat, ntfs3), ext4, everything else of the
  stock kernel.

`report.txt` (next to the build) lists every option that changed against the
stock kernel, and any line of `nebulae.config` that did not take effect.

## Building (WSL or any x86 Arch Linux)
```
systemd-run --unit=nebkernel bash Resources/kernel/build_kernel.sh /root/kernel/out
```
About 30-60 min. In WSL, keep that wsl session open until it is done (WSL
stops the Linux instance, and the build with it, about a minute after the
last wsl window or command closes), e.g. run it as
`wsl -d archlinux -u root -- bash build_kernel.sh` in a terminal window that
stays open. WSL's disk grows by about 3 GB. Result: `linux-nebulae-<version>.tar.xz` with
`boot/kernel8-nebulae.img` and `usr/lib/modules/<version>/`.

## Testing on a card (next to the stock kernel)
The kernel has its own name, so it does not replace anything:
1. on the Pi, as root, with the root file system read-write:
   ```
   tar -xJf linux-nebulae-<version>.tar.xz -C /
   ```
2. in `/boot/nebulae-image.txt` (the image's own boot settings, startup.sh
   does not overwrite it) add:
   ```
   kernel=kernel8-nebulae.img
   ```
3. reboot; `uname -r` shows `...-nebulae`.

Back to the stock kernel: remove that line. If the Pi does not start with
the new kernel, put the card in a PC: the boot partition is a normal FAT
drive in Windows, and the line can be removed with Notepad.

To compare: boot time (`systemd-analyze`, `Code/scripts/boot_time.py` on a
Pi 4), audio dropouts in the Csound and SC banks, `free -m`.
