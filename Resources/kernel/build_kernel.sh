#!/bin/bash
# The Nebulae kernel: Arch Linux ARM's linux-rpi (Raspberry Pi kernel fork,
# same commit and config, files in alarm/) with nebulae.config on top,
# cross-compiled for aarch64 (Pi 3 and Pi 4) in WSL or on any x86 Linux.
#   build_kernel.sh [OUTDIR]       default OUTDIR=/root/kernel/out
# Run as root (installs the cross compiler with pacman on Arch). Result:
#   OUTDIR/linux-nebulae-<version>.tar.xz   boot/kernel8-nebulae.img
#                                           usr/lib/modules/<version>/
#   OUTDIR/config-<version>                 the full .config
#   OUTDIR/report.txt                       what nebulae.config changed
# The kernel has its own name (-nebulae): it is installed next to the stock
# kernel and started with "kernel=kernel8-nebulae.img" (see README.md).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-/root/kernel/out}
W=/root/kernel/work
# Pinned to Arch Linux ARM core/linux-rpi 6.18.57-1 (alarm/PKGBUILD), the
# version on the Nebulae images, so the two kernels differ only in the config.
KVER=6.18.57
KREL=1
COMMIT=234188315037848e5b07d65b85d38edc64095caa
JOBS=${JOBS:-$(( $(nproc) > 2 ? $(nproc) - 1 : 1 ))}
MAKE=(make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j"$JOBS")

echo "==== $(date) Nebulae kernel $KVER-$KREL (raspberrypi/linux ${COMMIT:0:10})"
pacman -S --noconfirm --needed aarch64-linux-gnu-gcc bc flex bison openssl \
    libelf pahole cpio kmod xz >/dev/null
mkdir -p "$W" "$OUT"
cd "$W"
T=linux-$KVER-${COMMIT:0:10}.tar.gz
[ -f "$T" ] || curl -fL --retry 3 -o "$T.part" \
    "https://github.com/raspberrypi/linux/archive/$COMMIT.tar.gz" && { [ -f "$T" ] || mv "$T.part" "$T"; }
S=$W/linux-$COMMIT
rm -rf "$S"
echo "== unpacking"
tar -xzf "$T"
cd "$S"
patch -p1 -i "$HERE/alarm/0001-Make-proc-cpuinfo-consistent-on-arm64-and-arm.patch"
echo "-$KREL" > localversion.10-pkgrel
echo "-nebulae" > localversion.20-pkgname
sed -i '/^CONFIG_LOCALVERSION=/d' arch/arm64/configs/bcm2711_defconfig

echo "== config: bcm2711_defconfig + archarm.diffconfig (= stock linux-rpi)"
"${MAKE[@]}" -s bcm2711_defconfig
cat "$HERE/alarm/archarm.diffconfig" >> .config
"${MAKE[@]}" -s olddefconfig
cp .config "$W/config.stock"
echo "== + nebulae.config"
tr -d '\r' < "$HERE/nebulae.config" >> .config
"${MAKE[@]}" -s olddefconfig
VER=$("${MAKE[@]}" -s kernelrelease)

# What changed, and whether every line of nebulae.config took effect.
{
    echo "Nebulae kernel $VER, $(date)"
    echo "changed against the stock linux-rpi config:"
    scripts/diffconfig "$W/config.stock" .config | sed 's/^/  /'
    echo "nebulae.config lines that did not take effect (dependencies):"
    tr -d '\r' < "$HERE/nebulae.config" | grep -E '^(CONFIG_|# CONFIG_)' | while read -r l; do
        if [[ $l == "# CONFIG_"* ]]; then
            o=${l#\# }; o=${o%% *}
            grep -qE "^$o=" .config && echo "  $o is still set"
        else
            grep -qxF "$l" .config || echo "  $l is not set"
        fi
    done || true
    echo "(end)"
} > "$OUT/report.txt"
cat "$OUT/report.txt" | tail -25

echo "== building Image, modules, dtbs ($JOBS jobs) $(date +%T)"
"${MAKE[@]}" Image modules dtbs
echo "== installing into the staging tree $(date +%T)"
P=$W/pkg; rm -rf "$P"; mkdir -p "$P/boot"
cp arch/arm64/boot/Image "$P/boot/kernel8-nebulae.img"
"${MAKE[@]}" INSTALL_MOD_PATH="$P/usr" INSTALL_MOD_STRIP=1 modules_install >/dev/null
rm -f "$P/usr/lib/modules/$VER/build"
cp .config "$OUT/config-$VER"
tar -C "$P" -cJf "$OUT/linux-nebulae-$VER.tar.xz" boot usr
{
    echo "sizes:"
    echo "  kernel8-nebulae.img: $(du -h "$P/boot/kernel8-nebulae.img" | cut -f1)"
    echo "  modules: $(find "$P/usr/lib/modules/$VER" -name '*.ko*' | wc -l) files, $(du -sh "$P/usr/lib/modules/$VER" | cut -f1)"
} | tee -a "$OUT/report.txt"
echo "==== $(date) done: $OUT/linux-nebulae-$VER.tar.xz"
