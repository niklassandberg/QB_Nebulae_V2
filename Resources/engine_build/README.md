# Audio engines and their plugins

The Nebulae's audio engines and everything built for them are packages in the
firmware (`Code/engine_packages/`), built from the recipes here. Both have the same
layout, in two levels:

```
Code/engine_packages/                       Resources/engine_build/
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
The engines live in **`/home/alarm/engine_packages/`** (same layout), outside the
firmware folder: a firmware update replaces `QB_Nebulae_V2/`, but keeps what
was built on the Nebulae. `Code/scripts/engines_check.sh` (run by `update.sh`
during a firmware update, and by `setup_system.sh`):
1. merges the firmware's `Code/engine_packages/` into `/home/alarm/engine_packages/`: its
   recipes and scripts replace the old ones, its packages are added, nothing
   is deleted (the first time also the packages of the previous firmware)
2. merges the USB stick's **`engine_build/`** folder the same way (only the engine
   folders): **your own recipes or ready packages**, e.g.
   `engine_build/supercollider/plugins/sc-myugen/PKGBUILD` on the stick. Only
   during a firmware update (`neb_update.zip` on the stick too).
3. builds nothing: a recipe without a package of its version is only
   reported, on the stick in `neb_engines_report.txt` (build it by hand, below)
4. installs level 1 and then level 2, each package only when the installed
   version differs, and puts them in `IgnorePkg` so `pacman -Syu` cannot
   replace them
5. deletes the other package files of each package: the one with its
   recipe's version is kept (a version like `0+gfb481d4`, a commit, cannot be
   compared as newer), without a recipe the highest version

`engines_check.sh status` lists them.

Plugins that were copied in by hand before they were packages (the old
`build_sc.sh`, `build_pd_libs.sh`) block a package install ("exists in
filesystem"). The folders the packages may overwrite for that are in
**`legacy_overwrite.sh`**, the only place (read by `build_engines.sh` and
`engines_check.sh`): once no Nebulae has such leftovers, comment its lines out.

### Building a missing package on the Nebulae (by hand)
The firmware also carries the recipes (`create_fw_update.sh` copies this
folder into `Code/engine_packages/`). When a recipe has no package of its version in
`/home/alarm/engine_packages/` (for example a new UGen added to the repository
without building it, or a recipe from the stick), build it on the Nebulae:
```
sudo bash /home/alarm/QB_Nebulae_V2/Code/scripts/engines_build.sh
```
It builds every recipe without its package, **natively** for that Pi's CPU
(`-mcpu=native`: `cortex-a53+crc` on a Pi 3, `cortex-a72+crc` on a Pi 4, for
every recipe that uses makepkg's `$CFLAGS`; both models have the same
instructions, so a package also runs on the other one, only less finely
tuned), installs the result and deletes the old package files. Log:
`/home/alarm/engine_packages/build.log`. It needs internet:

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
   only read into RAM, and the Wi-Fi connection is taken down at the end.
3. else nothing is built: the installed engines stay.

Either way `neb_engines_report.txt` on the stick (mounted for the build if it
is in) says what was missing, which network was used, and what was built or
why not; when something failed also its last lines and the whole log
(`neb_engines_build.log.gz`). A build takes minutes for a UGen and hours for
Csound, sc3-plugins or ELSE on a Pi 3; the build tools it installs are
removed again afterwards.

## Building the packages
On a Pi with the 64-bit image, as root (hours on a Pi 3, mostly sc3-plugins
and ELSE, which builds its own ffmpeg):
```
systemd-run --unit=nebulae-engines bash Resources/engine_build/build_engines.sh /home/alarm/engine_packages
```
It builds and installs level 1, then level 2, and writes the packages to
`/home/alarm/engine_packages` in the `Code/engine_packages/` layout; copy that into the
repository. Packages already in the output folder are not built again (put the
current `Code/engine_packages/` there first to only build what is new).

A new version: change `pkgver`/tag/commit (and the checksums) in the recipe,
raise `pkgrel` for a rebuild of the same version.
