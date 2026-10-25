# Audio engines and their plugins

The Nebulae's audio engines and everything built for them are packages in the
firmware (`Code/engines/`), built from the recipes here. Both have the same
layout, in two levels:

```
Code/engines/                       Resources/engines/
  csound/                             csound/PKGBUILD
  supercollider/                      supercollider/PKGBUILD
    plugins/                            plugins/sc3-plugins/ sc-guttersynth/
                                                sc-xplaybuf/ sc-superbufrd/
  puredata/                           puredata/ (no recipe: the Arch package)
    externals/                          externals/pd-cyclone/ pd-else/
```

1. **Engines** (`<engine>/`): Csound, SuperCollider, Pure Data.
2. **Plugins / externals** (`<engine>/<dir>/<name>/`): built against the
   installed engine, so always after level 1.

| Package | Source | Why our own |
|---|---|---|
| csound 6.18.1-10.1 | Arch Linux ARM recipe, 2 fixes | ALARM builds it without optimisation (3x slower) and 6.18 ignores `-B`; see `csound/README.md` |
| supercollider-headless 3.14.1-1 | own recipe | headless, JACK, libscsynth (not in the repositories) |
| pd 0.57.0-1 | Arch Linux ARM package | none: it is built with optimisation (checked: plain configure/make with makepkg's `-O2`; ALARM uses Arch's recipe unchanged). Kept here so every Nebulae gets this version |
| sc3-plugins, sc-guttersynth, sc-xplaybuf, sc-superbufrd | upstream, pinned tag/commit | not packaged for aarch64; were built by hand (old `build_sc.sh`) |
| pd-cyclone 0.9.4, pd-else 1.0-rc14 | upstream, pinned tag | not packaged; were built by hand (old `build_pd_libs.sh`) |

All of them are optimised builds (`-O2`/`-O3`, CMake `Release`) for
`-march=armv8-a`, so the same packages run on a Pi 3 and a Pi 4.

## On the Nebulae
`Code/scripts/engines_check.sh` (run by `update.sh` after a firmware update,
and by `setup_system.sh`) installs level 1 and then level 2, each package only
when the installed version differs, and puts them all in `IgnorePkg` so
`pacman -Syu` cannot replace them. `engines_check.sh status` lists them.

### Fallback: the Nebulae builds a missing package itself
The firmware also carries the recipes (`create_fw_update.sh` copies this
folder into `Code/engines/`). When a recipe has no package next to it (for
example a new UGen added to the repository without building it), the firmware
update builds it on the Nebulae (`Code/scripts/engines_build.sh`):

1. internet through the **LAN** cable, if it has internet
2. else **Wi-Fi** as a normal client, with a file called `wlan0-wifi` (no
   filename extension!) on the USB stick next to `neb_update.zip`, with your
   Wi-Fi name and password:
   ```
   Description='wifi for netctl'
   Interface=wlan0
   Connection=wireless
   Security=wpa
   ESSID=YourWifiNetworkName
   IP=dhcp
   Key=YourWifiPassword
   ```
   It is the same file the Nebulae uses for the home network when Wi-Fi is
   switched on (`start_wifi.sh`). Quotes around a value do not matter (`"…"`,
   `'…'`, `’…’` from old instructions, or none): the Nebulae takes every value
   as written, also a `$` in the password (`Code/scripts/wifi_profile.sh`).
   A WPA password has 8-63 characters. `Security=none` (and no `Key`) for an
   open network, `Hidden=yes` for a network that does not show its name. Here it is
   only read into RAM, the Wi-Fi setting is gone after the reboot that ends the
   update.
3. else nothing is built: the installed engines stay.

Either way `neb_engines_report.txt` on the stick says what was missing, which
network was used, and what was built or why not. A build takes minutes for a
UGen and hours for Csound, sc3-plugins or ELSE on a Pi 3 (the update LEDs stay
on meanwhile); the build tools it installs are removed again afterwards.

## Building the packages
On a Pi with the 64-bit image, as root (hours on a Pi 3, mostly sc3-plugins
and ELSE, which builds its own ffmpeg):
```
systemd-run --unit=nebulae-engines bash Resources/engines/build_engines.sh /home/alarm/engines_out
```
It builds and installs level 1, then level 2, and writes the packages to
`/home/alarm/engines_out` in the `Code/engines/` layout; copy that into the
repository. Packages already in the output folder are not built again (put the
current `Code/engines/` there first to only build what is new).

A new version: change `pkgver`/tag/commit (and the checksums) in the recipe,
raise `pkgrel` for a rebuild of the same version.
