# Csound package for the Nebulae (aarch64)

Nebulae uses its own build of Csound 6.18.1 instead of the Arch Linux ARM
package. The package is in `Code/engines/`; a firmware update installs it
(`Code/scripts/engines_check.sh`, run by `update.sh`) when another Csound is
installed, and adds `csound` to `IgnorePkg` so `pacman -Syu` keeps it.

## Why
Found 2026-10-23: granular_looper glitched on a Pi 3 with the 64-bit image at
moderate settings, while Qu-Bit's original Pi 3 system (Csound 6.11) played
it clean with every knob at maximum.

1. **The Arch Linux ARM package is built without optimisation.** ALARM's
   PKGBUILD sets `CMAKE_C_FLAGS` / `CMAKE_CXX_FLAGS` to its own flags only,
   which replaces makepkg's `CFLAGS` (`-O2 -march=armv8-a ...`); with
   `CMAKE_BUILD_TYPE=None` nothing adds `-O2` back. The library has 65 % more
   instructions and 5x the stack loads/stores of an optimised build.
   Offline benchmark on the Pi 3 (granular_looper, the glitching setting,
   60 s of audio):

   | Csound | time for 60 s audio | speed |
   |---|---|---|
   | Arch Linux ARM 6.18.1-10 | 66.3 s | 0.91x real time (dropouts) |
   | 6.18.1 built with the CFLAGS | 21.4 s | 2.80x |
   | 6.11.0 built with the CFLAGS | 20.5 s | 2.92x |

   The Csound version is not the difference; the build is. The 32-bit
   (armv7h) image used the same build system and glitched too.
2. **Csound 6.18 ignores `-B`.** `InOut/rtalsa.c` `open_device()` lost the
   line `dev->buffer_smps = parm->bufSamp_HW;` (6.11 has it), so the ALSA
   buffer is always 1024 frames (2 x 512). Instruments ask for `-B 2048`, as
   on the original system. `rtalsa-buffer-size.patch` puts the line back.
   Latency is the same as on the original Pi 3 (Csound still works in `-b`
   blocks; the buffer holds 4 of them instead of 2).

Not the cause (measured): nebio's input rates and interrupts (~5 % of a core
with nebio almost off), scheduling priority, the kernel, 32 vs 64 bit, the
buffer alone.

## Files
- `PKGBUILD`: ALARM's extra/csound 6.18.1-10 with the two fixes, pkgrel 10.1
- `rtalsa-buffer-size.patch`: fix 2
- `csound.sh`: unchanged from Arch (profile.d variables)

## Building a new package
On a Pi with the 64-bit image (about 30 min on a Pi 3):
```
makepkg -s          # in a copy of this folder, as alarm
cp csound-6.18.1-10.1-aarch64.pkg.tar.zst <repo>/Code/engines/
```
For a new Csound version: start from the current ALARM PKGBUILD again and
check both fixes are still needed (look at its CMAKE_C_FLAGS line and at
`open_device()` in `InOut/rtalsa.c`).
