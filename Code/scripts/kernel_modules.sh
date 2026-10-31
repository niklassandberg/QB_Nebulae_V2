#!/bin/bash
# Nebulae's own kernel modules: Code/kernel_modules/<kernel version>/*.ko.xz
# (built with Resources/kernel/build_proto_modules.sh) go into
# /lib/modules/<kernel version>/updates/ of every kernel on the card that has
# that version, then depmod. updates/ wins over the kernel package's own
# module, which stays untouched (deleting ours + depmod goes back).
# Today: snd-soc-rpi-proto, the codec card driver that runs every sample rate
# right (Resources/kernel/0002-rpi-proto-bclk-ratio-per-rate.patch).
#
# A module is only installed when its vermagic equals that of the kernel's
# own module: same version, same kind of build. Other kernels (another
# version, the old 32-bit images) keep their driver; the instruments' -r then
# snaps to 48000 (nebulae.py jackRates()). The new module is used from the
# next boot on (update.sh reboots).
#   kernel_modules.sh          install what fits, report the rest
#   kernel_modules.sh status   only report
SRC=/home/alarm/QB_Nebulae_V2/Code/kernel_modules
[ -d "$SRC" ] || exit 0
for dir in "$SRC"/*/; do
    [ -d "$dir" ] || continue
    ver=$(basename "$dir")
    if [ ! -d "/lib/modules/$ver" ]; then
        echo "kernel modules: no kernel $ver on this card, skipped"
        continue
    fi
    changed=0
    for mod in "$dir"*.ko.xz; do
        [ -f "$mod" ] || continue
        name=$(basename "$mod")
        own=$(find "/lib/modules/$ver/kernel" -name "$name" 2>/dev/null | head -1)
        if [ -z "$own" ] || [ "$(modinfo -F vermagic "$mod")" != "$(modinfo -F vermagic "$own")" ]; then
            echo "kernel modules: $name does not fit kernel $ver, skipped"
            continue
        fi
        if cmp -s "$mod" "/lib/modules/$ver/updates/$name"; then
            echo "kernel modules: $ver/$name up to date"
        elif [ "$1" = status ]; then
            echo "kernel modules: $ver/$name would be installed"
        else
            mkdir -p "/lib/modules/$ver/updates"
            cp "$mod" "/lib/modules/$ver/updates/$name"
            echo "kernel modules: $ver/$name installed (used from the next boot)"
            changed=1
        fi
    done
    [ $changed = 1 ] && depmod "$ver"
done
exit 0
