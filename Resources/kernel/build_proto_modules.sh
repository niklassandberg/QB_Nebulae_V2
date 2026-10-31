#!/bin/bash
# The codec card driver (snd-soc-rpi-proto, patched) for every kernel a
# Nebulae image may boot, collected for the firmware: copy OUTDIR/* into the
# repo's Code/kernel_modules/ (one folder per kernel version); every firmware
# update then installs what fits (Code/scripts/kernel_modules.sh).
#   build_proto_modules.sh [OUTDIR]     default /root/kernel/proto-modules
# Run as root on an aarch64 Arch Linux ARM with the source tree and configs of
# build_kernel.sh (e.g. the Pi 4 that built the kernels):
#   stock     /root/kernel/work/config.stock (= Arch Linux ARM linux-rpi)
#   nebulae   /root/kernel/out-native/config-<version>, both variants
# A new kernel version (linux-rpi update, new Nebulae kernel): build_kernel.sh
# first, then this.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-/root/kernel/proto-modules}
K=/root/kernel/out-native
"$HERE/build_proto_module.sh" rpi /root/kernel/work/config.stock "$OUT"
for cfg in "$K"/config-*-nebulae "$K"/config-*-nebulae-rt; do
    [ -f "$cfg" ] || continue
    case $cfg in *-rt) name=nebulae-rt ;; *) name=nebulae ;; esac
    "$HERE/build_proto_module.sh" "$name" "$cfg" "$OUT"
done
echo "== for Code/kernel_modules/:"
ls -l "$OUT"/*/snd-soc-rpi-proto.ko.xz
