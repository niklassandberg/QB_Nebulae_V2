#!/bin/bash
# Only the codec card driver (snd-soc-rpi-proto) with
# 0002-rpi-proto-bclk-ratio-per-rate.patch, for a kernel that is already on
# the card: the stock linux-rpi or a Nebulae kernel. A minute instead of a
# kernel build. Needs the source tree of build_kernel.sh (same commit as the
# stock kernel) and the kernel's config:
#   build_proto_module.sh NAME CONFIG [OUTDIR]
#   NAME    rpi (stock), nebulae, nebulae-rt: the end of the kernel version
#   CONFIG  stock: /root/kernel/work/config.stock (made by build_kernel.sh),
#           Nebulae: OUTDIR of build_kernel.sh/config-<version>
#   OUTDIR  default /root/kernel/proto-modules; the result is
#           OUTDIR/<version>/snd-soc-rpi-proto.ko.xz
# Install on the card (the package's own module stays; depmod prefers
# updates/; undo = delete it + depmod):
#   cp OUTDIR/<version>/snd-soc-rpi-proto.ko.xz /lib/modules/<version>/updates/
#   depmod <version>; then reboot (never rmmod/insmod it while running: the
#   codec then has no clock until the next boot)
# The kernels have no MODVERSIONS and no module signing: version name and
# config must match, the symbols are found by name when it loads.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NAME=$1
CONFIG=$2
OUT=${3:-/root/kernel/proto-modules}
S=$(ls -d /root/kernel/work/linux-*/ | head -1)
[ -f "$CONFIG" ] || { echo "no config $CONFIG"; exit 1; }
cd "$S"
grep -q 'MODULE_VERSION("nebulae-rates-1")' sound/soc/bcm/rpi-proto.c \
    || patch -p1 -i "$HERE/0002-rpi-proto-bclk-ratio-per-rate.patch"
cp "$CONFIG" .config
echo "-$NAME" > localversion.20-pkgname
make -s olddefconfig
make -s -j3 modules_prepare
rm -f sound/soc/bcm/rpi-proto.o sound/soc/bcm/snd-soc-rpi-proto.ko
# Module.symvers is of the last full build (maybe the other variant): the
# other modules of the folder may miss symbols there, so only warn.
make -s -j3 KBUILD_MODPOST_WARN=1 M=sound/soc/bcm modules >/dev/null 2>&1 || true
V=$(cat include/config/kernel.release)
mkdir -p "$OUT/$V"
xz -c sound/soc/bcm/snd-soc-rpi-proto.ko > "$OUT/$V/snd-soc-rpi-proto.ko.xz"
echo "$OUT/$V/snd-soc-rpi-proto.ko.xz: $(modinfo -F vermagic sound/soc/bcm/snd-soc-rpi-proto.ko), $(modinfo -F version sound/soc/bcm/snd-soc-rpi-proto.ko)"
