# Raspberry Pi 4 bootloader (EEPROM) for the Nebulae

The Nebulae (64-bit image, kernel 6.18) runs bootloader **2026-09-23** with
`nebulae-eeprom.conf` (flashed 2026-10-22). Compared with the bootloader it
had before (2023-01-11), the firmware phase before the kernel is ~0.9 s
shorter (7.52 -> 6.60 s, `Code/scripts/boot_time.py`); USB works.

`nebulae-eeprom.conf` is its config: `BOOT_UART=0`, `WAKE_ON_GPIO=1`,
`POWER_OFF_ON_HALT=0` (as the Pi had), `DISABLE_HDMI=1`, `NET_INSTALL_AT_POWER_ON=0`.

## Updating a Pi 4: from the Nebulae firmware
The kit (pieeprom.upd = 2026-09-23 with nebulae-eeprom.conf, pieeprom.sig,
recovery.bin) is in the firmware: `Code/localfiles/eeprom/`. The update is
opt-in: put an empty file called `update_bootloader` on the USB stick and
start the Nebulae. update.sh removes the file, `Code/scripts/eeprom_update.sh`
checks (64-bit image only, Pi's bootloader older than the kit, kit checksum),
copies the kit to /boot and reboots: the Pi flashes itself (a few seconds,
green LED; do not switch off) and starts normally; the next boot removes
the files from /boot. What happened is written to `neb_log.txt` on the stick
("already 2026-09-23, nothing done", "not on this image", ...).

## A new kit
From https://github.com/raspberrypi/rpi-eeprom (`firmware-2711/default/`):
`pieeprom-<date>.bin`, `recovery.bin` and the tool `rpi-eeprom-config`.
- `rpi-eeprom-config --config nebulae-eeprom.conf --out pieeprom.upd pieeprom-<date>.bin`
- `pieeprom.sig`: line 1 the sha256 of pieeprom.upd, line 2 `ts: <build
  timestamp>` (seconds; eeprom_update.sh compares it with
  /proc/device-tree/chosen/bootloader/build-timestamp, which the Pi shows
  after flashing).
- Put the three files in `Code/localfiles/eeprom/`.

## Repair
A Pi whose EEPROM is broken (e.g. power lost during an update): Raspberry Pi
Imager, "Misc utility images" > "Bootloader" (SD card boot) writes a recovery
SD card. Put it in the Pi, power on, wait until the green LED blinks steadily,
power off, put the Nebulae card back, then update with `update_bootloader`.

## Note
This bootloader needs the 64-bit image: the old 32-bit image (kernel 5.15)
gets no USB with it (no `vl805.bin` for the USB controller; the kernel gives
up with `xhci_hcd ... can't setup: -110`). eeprom_update.sh never flashes on
the 32-bit image. To use the 32-bit image again on a Pi that has this
bootloader, flash an older bootloader first (Imager as above, or a 2023
release from rpi-eeprom).
