#!/bin/bash
# Code/kernel_modules/<version>/*.ko.xz into /lib/modules/<version>/updates/
# of each kernel with the same vermagic, then depmod.
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
