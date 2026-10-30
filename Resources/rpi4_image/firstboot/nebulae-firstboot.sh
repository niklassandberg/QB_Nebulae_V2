#!/bin/bash
# First start of a card written from a release image (make_release_image.sh),
# once: the flag /etc/nebulae-firstboot is removed at the end.
#  - own identity: a new machine ID (the image's is the same on every card;
#    DHCP and mDNS use it, two Nebulae on one network got the same IP) and
#    new SSH host keys
#  - the root partition and its file system grown to the whole SD card
# Not systemd's own first boot (an empty /etc/machine-id): that also applies
# unit presets and may ask questions on the console.
log() { echo "nebulae-firstboot: $*"; }

rm -f /etc/machine-id && systemd-machine-id-setup >/dev/null && log "new machine ID"
ssh-keygen -A >/dev/null && log "new SSH host keys"

# Root partition from the kernel command line (root=/dev/mmcblk0p2).
root=$(tr ' ' '\n' < /proc/cmdline | sed -n 's|^root=||p')
disk=${root%p[0-9]*}
part=${root##*p}
if [ -b "$disk" ] && [ -b "$root" ]; then
    if echo ', +' | sfdisk --no-reread -q -N "$part" "$disk"; then
        partx -u "$disk"
        resize2fs "$root" >/dev/null 2>&1 && log "root file system grown to $(df -h / | awk 'NR==2{print $2}')"
    fi
fi

rm -f /etc/nebulae-firstboot
sync
