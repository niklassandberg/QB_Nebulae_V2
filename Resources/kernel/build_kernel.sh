#!/bin/bash
# The Nebulae kernel: Arch Linux ARM's linux-rpi (Raspberry Pi kernel fork,
# same commit and config, files in alarm/) with nebulae.config on top,
# cross-compiled for aarch64 (Pi 3 and Pi 4) in WSL or on any x86 Linux, or
# built natively on an aarch64 Arch Linux ARM (e.g. the Pi 4 itself, ~2 h):
# then with the same compiler as Arch Linux ARM's own linux-rpi. (The Pi 4
# hang at boot of 2026-10-30 was not the compiler: native builds hung the
# same; the card had no arm_64bit=1, see README.md.)
#   build_kernel.sh [OUTDIR] [rt]  default OUTDIR=/root/kernel/out
#   rt: the real-time variant, nebulae-rt.config on top (PREEMPT_RT)
# Run as root (installs the cross compiler with pacman on Arch). Result:
#   OUTDIR/linux-NAME-<version>.tar.xz      boot/kernel8-NAME.img
#                                           usr/lib/modules/<version>/
#   OUTDIR/config-<version>                 the full .config
#   OUTDIR/report[-rt].txt                  what the config files changed
# NAME is nebulae or nebulae-rt. The kernel has its own name: it is installed
# next to the stock kernel (and the other variant) and started with
# "kernel=kernel8-NAME.img" (see README.md).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-/root/kernel/out}
case ${2:-} in
    "") NAME=nebulae;    SUF=;    CONFIGS=("$HERE/nebulae.config") ;;
    rt) NAME=nebulae-rt; SUF=-rt; CONFIGS=("$HERE/nebulae.config" "$HERE/nebulae-rt.config") ;;
    *)  echo "unknown variant '$2' (only: rt)" >&2; exit 2 ;;
esac
W=/root/kernel/work
# Pinned to Arch Linux ARM core/linux-rpi 6.18.57-1 (alarm/PKGBUILD), the
# version on the Nebulae images, so the two kernels differ only in the config.
KVER=6.18.57
KREL=1
COMMIT=234188315037848e5b07d65b85d38edc64095caa
JOBS=${JOBS:-$(( $(nproc) > 2 ? $(nproc) - 1 : 1 ))}
if [ "$(uname -m)" = aarch64 ]; then
    MAKE=(make -j"$JOBS")
    DEPS=(gcc bc flex bison openssl libelf cpio kmod xz)
else
    MAKE=(make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j"$JOBS")
    DEPS=(aarch64-linux-gnu-gcc bc flex bison openssl libelf pahole cpio kmod xz)
fi

echo "==== $(date) Nebulae kernel $KVER-$KREL$SUF (raspberrypi/linux ${COMMIT:0:10}), $(uname -m)"
pacman -S --noconfirm --needed "${DEPS[@]}" >/dev/null
echo "compiler: $(${DEPS[0]} --version | head -1)"
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
echo "-$NAME" > localversion.20-pkgname
sed -i '/^CONFIG_LOCALVERSION=/d' arch/arm64/configs/bcm2711_defconfig

echo "== config: bcm2711_defconfig + archarm.diffconfig (= stock linux-rpi)"
"${MAKE[@]}" -s bcm2711_defconfig
cat "$HERE/alarm/archarm.diffconfig" >> .config
"${MAKE[@]}" -s olddefconfig
cp .config "$W/config.stock"
echo "== + ${CONFIGS[*]##*/}"
cat "${CONFIGS[@]}" | tr -d '\r' >> .config
"${MAKE[@]}" -s olddefconfig
VER=$("${MAKE[@]}" -s kernelrelease)

# What changed, and whether every line of the config files took effect. An
# option set in more than one file is checked only as the last file sets it.
{
    echo "Nebulae kernel $VER, $(date), $(uname -m), $(${DEPS[0]} --version | head -1)"
    echo "changed against the stock linux-rpi config:"
    scripts/diffconfig "$W/config.stock" .config | sed 's/^/  /'
    echo "${CONFIGS[*]##*/} lines that did not take effect (dependencies):"
    cat "${CONFIGS[@]}" | tr -d '\r' | grep -E '^(CONFIG_|# CONFIG_)' | tac \
        | awk '{ o = ($1 == "#") ? $2 : $1; sub(/=.*/, "", o) } !seen[o]++' \
        | tac | while read -r l; do
        if [[ $l == "# CONFIG_"* ]]; then
            o=${l#\# }; o=${o%% *}
            grep -qE "^$o=" .config && echo "  $o is still set"
        else
            grep -qxF "$l" .config || echo "  $l is not set"
        fi
    done || true
    echo "(end)"
} > "$OUT/report$SUF.txt"
tail -25 "$OUT/report$SUF.txt"

echo "== building Image, modules, dtbs ($JOBS jobs) $(date +%T)"
"${MAKE[@]}" Image modules dtbs
echo "== installing into the staging tree $(date +%T)"
P=$W/pkg; rm -rf "$P"; mkdir -p "$P/boot"
cp arch/arm64/boot/Image "$P/boot/kernel8-$NAME.img"
"${MAKE[@]}" INSTALL_MOD_PATH="$P/usr" INSTALL_MOD_STRIP=1 modules_install >/dev/null
rm -f "$P/usr/lib/modules/$VER/build"
cp .config "$OUT/config-$VER"
tar -C "$P" -cJf "$OUT/linux-$NAME-$VER.tar.xz" boot usr
{
    echo "sizes:"
    echo "  kernel8-$NAME.img: $(du -h "$P/boot/kernel8-$NAME.img" | cut -f1)"
    echo "  modules: $(find "$P/usr/lib/modules/$VER" -name '*.ko*' | wc -l) files, $(du -sh "$P/usr/lib/modules/$VER" | cut -f1)"
} | tee -a "$OUT/report$SUF.txt"
echo "==== $(date) done: $OUT/linux-$NAME-$VER.tar.xz"
