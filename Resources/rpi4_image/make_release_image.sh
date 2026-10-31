#!/bin/bash
# Release image of the Nebulae for other users, from an image of a working
# card (e.g. read with Win32 Disk Imager, or a .img.zst from pi_image_backup.sh).
# The source is only read.
#
#   make_release_image.sh [--firmware neb_update.zip] [--spare MiB] [--keep-img]
#                         SOURCE.img|SOURCE.img.zst OUT.img.xz
#   make_release_image.sh --pi3 [--keep-img] RELEASE.img|RELEASE.img.xz OUT.img.xz
#
# --pi3: a copy of an existing release image (made without Pi 3 support) that
# also starts on a Pi 3: only the Pi 3 support below is added, nothing else is
# rebuilt. Images made without --pi3 have it already.
#
# The release image:
#  - small: the root file system is made new from the files (mke2fs -d) with
#    --spare MiB free (default 1536), so it fits on an 8 GB card; it grows to
#    the whole card at its first start (firstboot/nebulae-firstboot)
#  - no personal state: a new machine ID and SSH host keys at the first start;
#    no logins (authorized_keys), histories, logs, package cache, build
#    leftovers, backups, files from the USB stick, Nebulae settings
#    (Code/config back to the factory defaults, no calibration)
#  - with --firmware: the Nebulae firmware from that neb_update.zip
#    (create_fw_update.sh) instead of the source card's
#  - starts on a Pi 4 and a Pi 3: /boot/nebulae-image.txt (arm_64bit=1; the Pi 3
#    otherwise looks for a 32-bit kernel), included from config.txt, also in
#    the firmware's Code/localfiles/config.txt (startup.sh copies that to /boot)
#  - checked: e2fsck, and every file (content, owner, permissions, size, link
#    targets) compared with what was meant to go in
#  - OUT.img.xz (Raspberry Pi Imager and balenaEtcher write it as it is) and
#    OUT.img.xz.sha256 (of the .img inside)
#
# Run as root in WSL or Linux; needs util-linux, e2fsprogs (1.47: mke2fs -d),
# xz, zstd for a .zst source, unzip/tar for --firmware. Space next to OUT: the
# release .img (~7 GB) while it is made, and a whole decompressed source for
# a .zst one.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
FIRMWARE=""; SPARE=1536; KEEP=0; PI3=0; ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --firmware) FIRMWARE=$2; shift ;;
        --spare) SPARE=$2; shift ;;
        --keep-img) KEEP=1 ;;
        --pi3) PI3=1 ;;
        -h|--help) sed -n '2,38p' "$0"; exit 0 ;;
        *) ARGS+=("$1") ;;
    esac
    shift
done
[ ${#ARGS[@]} = 2 ] || { sed -n '2,38p' "$0"; exit 2; }
SRC=${ARGS[0]}; OUT=${ARGS[1]}
case "$OUT" in *.img.xz) ;; *) echo "OUT must end in .img.xz"; exit 2 ;; esac
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 2; }
for t in sfdisk losetup mke2fs e2fsck xz sha256sum; do
    command -v $t >/dev/null || { echo "missing tool: $t"; exit 2; }
done
[ -f "$SRC" ] || { echo "no source: $SRC"; exit 2; }
[ -z "$FIRMWARE" ] || [ -f "$FIRMWARE" ] || { echo "no firmware: $FIRMWARE"; exit 2; }
for f in nebulae-firstboot.sh nebulae-firstboot.service; do
    [ -f "$HERE/firstboot/$f" ] || { echo "missing $HERE/firstboot/$f"; exit 2; }
done

IMG=${OUT%.xz}
T=$(mktemp -d /tmp/nebrelease.XXXXXX)
TMPSRC=""
mkdir -p "$T/lower" "$T/up" "$T/work" "$T/root" "$T/new"
cleanup() {
    umount "$T/boot" "$T/new" "$T/root" "$T/lower" 2>/dev/null
    for f in "$SRC" "$IMG"; do
        for l in $(losetup -n -O NAME -j "$f" 2>/dev/null); do losetup -d "$l"; done
    done
    [ -n "$TMPSRC" ] && rm -f "$TMPSRC"
    rm -rf "$T"
}
trap cleanup EXIT
die() { echo "ERROR: $*"; exit 1; }
step() { echo "==== $(date +%T) $*"; }

# Pi 3 support. The image's own settings go to nebulae-image.txt in the boot
# partition; config.txt only includes it, so the same firmware config.txt
# still works on images without that file.
PI3TXT=nebulae-image.txt
pi3_root() {   # $1 = root file system; the firmware's config.txt gets the include
    local f=$1/home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt
    [ -f "$f" ] || die "no $f"
    grep -q "^include $PI3TXT" "$f" && return 0
    [ -n "$(tail -c1 "$f")" ] && echo >> "$f"
    if grep -q $'\r$' "$f"; then
        printf '# 64-bit image settings (Pi 3: arm_64bit=1), see /boot/%s\r\ninclude %s\r\n' $PI3TXT $PI3TXT >> "$f"
    else
        printf '# 64-bit image settings (Pi 3: arm_64bit=1), see /boot/%s\ninclude %s\n' $PI3TXT $PI3TXT >> "$f"
    fi
}
pi3_boot() {   # $1 = image, $2 = root file system (pi3_root done)
    local s z LB
    read -r s z < <(sfdisk -d "$1" | grep 'start=' | head -1 |
        sed 's/.*start= *\([0-9]*\), *size= *\([0-9]*\).*/\1 \2/')
    LB=$(losetup -f --show -o $((s * 512)) --sizelimit $((z * 512)) "$1") || die "losetup boot"
    mkdir -p "$T/boot"
    mount -t vfat "$LB" "$T/boot" || die "mount boot partition"
    [ -f "$T/boot/kernel8.img" ] || die "no kernel8.img in the boot partition"
    [ -f "$T/boot/bootcode.bin" ] && ls "$T"/boot/bcm2710-rpi-3-b*.dtb >/dev/null 2>&1 ||
        die "no Pi 3 boot files (bootcode.bin, bcm2710-rpi-3-b*.dtb)"
    printf '# Settings of this 64-bit image, included from config.txt.\n# 64-bit kernel (kernel8.img) on a Pi 3 too; a Pi 4 does that by itself.\narm_64bit=1\n' > "$T/boot/$PI3TXT"
    # As startup.sh does at every start: config.txt = the firmware's.
    cat "$2/home/alarm/QB_Nebulae_V2/Code/localfiles/config.txt" > "$T/boot/config.txt"
    umount "$T/boot" || die "umount boot partition"
    if command -v fsck.vfat >/dev/null; then
        # A card read while /boot was mounted has the dirty bit set: cleared
        # here; after that the check must be clean.
        fsck.vfat -a "$LB" 2>&1 | grep -iE 'dirty|remov|fix|correct|free' | sed 's/^ */  fsck.vfat: /'
        fsck.vfat -n "$LB" >/dev/null 2>&1 || { fsck.vfat -n "$LB" | tail -5; die "fsck.vfat"; }
    fi
    losetup -d "$LB"
    echo "  boot partition: $PI3TXT (arm_64bit=1) + include in config.txt"
}

if [ $PI3 = 1 ]; then
    IMG=${OUT%.xz}
    [ "$(readlink -f "$SRC")" != "$(readlink -f "$IMG")" ] || die "OUT must differ from the source"
    rm -f "$IMG"
    case "$SRC" in
        *.xz) step "decompressing $SRC"; xz -d -c "$SRC" > "$IMG" || die "decompress" ;;
        *) step "copying $SRC"; cp "$SRC" "$IMG" || die "copy" ;;
    esac
    read -r start size < <(sfdisk -d "$IMG" | grep 'start=' | tail -1 |
        sed 's/.*start= *\([0-9]*\), *size= *\([0-9]*\).*/\1 \2/')
    [ -n "${start:-}" ] || die "no partition table in $SRC"
    LN=$(losetup -f --show -o $((start * 512)) --sizelimit $((size * 512)) "$IMG") || die "losetup root"
    e2fsck -fn "$LN" >/dev/null 2>&1 || die "e2fsck: the source root file system has errors"
    mount "$LN" "$T/new" || die "mount root"
    [ -f "$T/new/etc/nebulae-firstboot" ] || die "not a release image (no /etc/nebulae-firstboot)"
    step "Pi 3 support"
    pi3_root "$T/new"
    pi3_boot "$IMG" "$T/new"
    umount "$T/new" || die "umount root"
    e2fsck -fn "$LN" >/dev/null 2>&1 || die "e2fsck after the change"
    losetup -d "$LN"
    echo "  e2fsck ok"
    step "compressing"
    xz -T0 -6 -k -f -c "$IMG" > "$OUT.part" || die "xz"
    xz -t "$OUT.part" || die "xz test"
    mv "$OUT.part" "$OUT"
    echo "$(sha256sum < "$IMG" | cut -d' ' -f1)  $(basename "$IMG")" > "$OUT.sha256"
    [ $KEEP = 1 ] || rm -f "$IMG"
    step "done: $OUT ($(du -h "$OUT" | cut -f1)), starts on a Pi 3 and a Pi 4"
    exit 0
fi

if [ "${SRC##*.}" = zst ]; then
    step "decompressing $SRC"
    TMPSRC="$(dirname "$OUT")/.release-src.$$.img"
    zstd -d -q -f "$SRC" -o "$TMPSRC" || die "decompress"
    SRC=$TMPSRC
fi

# Source layout: boot partition first, root (ext4) last.
read -r start size < <(sfdisk -d "$SRC" | grep 'start=' | tail -1 |
    sed 's/.*start= *\([0-9]*\), *size= *\([0-9]*\).*/\1 \2/')
[ -n "${start:-}" ] || die "no partition table in $SRC"
off=$((start * 512))
LO=$(losetup -r -f --show -o $off --sizelimit $((size * 512)) "$SRC") || die "losetup"
[ "$(blkid -o value -s TYPE "$LO")" = ext4 ] || die "last partition is not ext4"
e2fsck -fn "$LO" >/dev/null 2>&1 || die "e2fsck: the source root file system has errors"
mount -o ro,noload "$LO" "$T/lower" || die "mount source"
mount -t overlay overlay -o "lowerdir=$T/lower,upperdir=$T/up,workdir=$T/work" "$T/root" || die "overlay"
R=$T/root
[ -d "$R/home/alarm/QB_Nebulae_V2/Code" ] || die "no Nebulae firmware on the source"
UIDG=$(awk -F: '$1=="alarm"{print $3":"$4}' "$R/etc/passwd")

step "removing personal state"
# Identity: replaced at the first start (nebulae-firstboot).
rm -f "$R"/etc/ssh/ssh_host_*
rm -f "$R/var/lib/systemd/random-seed" "$R/var/lib/systemd/credential.secret"
# Logins, histories, caches.
rm -rf "$R/root/.ssh" "$R/home/alarm/.ssh" "$R/root/.cache" "$R/home/alarm/.cache"
for h in .bash_history .python_history .lesshst .viminfo; do rm -f "$R/root/$h" "$R/home/alarm/$h"; done
rm -f "$R/home/alarm/wifi.log"
rm -rf "$R"/var/log/journal/* "$R"/var/cache/pacman/pkg/*
for f in wtmp btmp lastlog; do [ -f "$R/var/log/$f" ] && : > "$R/var/log/$f"; done
# Leftovers from making and tuning the card.
rm -rf "$R/home/alarm/sc_build" "$R/home/alarm/pd_build" "$R/home/alarm/rpi4_image" \
       "$R/home/alarm/backup_boot" "$R/home/alarm/backup" "$R/home/alarm/cache" \
       "$R/home/alarm/QB_Nebulae_V2.broken" "$R/home/alarm/rpiutils-bin" \
       "$R"/home/alarm/.eeprom_update* "$R/root/boot_aarch64_backup"
rm -f "$R"/root/cmdline.txt.* "$R"/root/config.txt.* "$R"/root/fstab.*
# Files loaded from the USB stick (the file loader brings them again).
for d in audio instr pd sc; do [ -d "$R/home/alarm/$d" ] && find "$R/home/alarm/$d" -mindepth 1 -delete; done

if [ -n "$FIRMWARE" ]; then
    step "firmware from $FIRMWARE"
    fw=$T/fw; mkdir -p "$fw"
    tar -xzf "$FIRMWARE" -C "$fw" 2>/dev/null || unzip -q "$FIRMWARE" -d "$fw" || die "unpack firmware"
    [ -d "$fw/QB_Nebulae_V2/Code/nebulae" ] || die "no QB_Nebulae_V2/Code in $FIRMWARE"
    old=$R/home/alarm/QB_Nebulae_V2
    # nebio's build: kept, build_nebio.sh rebuilds it when the sources differ.
    [ -d "$old/Code/nebio/build" ] && cp -a "$old/Code/nebio/build" "$fw/QB_Nebulae_V2/Code/nebio/"
    rm -rf "$old"
    if [ -d "$fw/QB_Nebulae_V2/SuperColliderExtensions" ]; then
        for e in "$fw"/QB_Nebulae_V2/SuperColliderExtensions/*; do
            rm -rf "$R/usr/share/SuperCollider/Extensions/$(basename "$e")"
            cp -a "$e" "$R/usr/share/SuperCollider/Extensions/"
        done
        rm -rf "$fw/QB_Nebulae_V2/SuperColliderExtensions"
    fi
    mv "$fw/QB_Nebulae_V2" "$old"
    chown -R "$UIDG" "$old"
    # As update.sh does: services and SC config from Code/localfiles.
    lf=$old/Code/localfiles
    for s in nebulae.service sclang.service jack@.service nebwifi.service; do
        [ -f "$lf/$s" ] && install -m 644 "$lf/$s" "$R/etc/systemd/system/$s"
    done
    # jack.service was replaced by jack@.service (one unit per JACK period)
    [ -f "$lf/jack@.service" ] && rm -f "$R/etc/systemd/system/jack.service"
    [ -f "$lf/jackdrc" ] && install -m 644 "$lf/jackdrc" "$R/etc/jackdrc"
    [ -f "$lf/startup.scd" ] && mkdir -p "$R/root/.config/SuperCollider" &&
        install -m 644 "$lf/startup.scd" "$R/root/.config/SuperCollider/startup.scd"
fi

step "Nebulae back to factory settings"
code=$R/home/alarm/QB_Nebulae_V2/Code
find "$code/config" -mindepth 1 ! -name defaultnebsettings.txt -delete 2>/dev/null
find "$code/log" -mindepth 1 -delete 2>/dev/null
rm -f "$code/misc/calibration_data.txt" "$code/hwtest_mode"

step "first start service"
install -D -m 755 "$HERE/firstboot/nebulae-firstboot.sh" "$R/usr/local/sbin/nebulae-firstboot"
install -m 644 "$HERE/firstboot/nebulae-firstboot.service" "$R/etc/systemd/system/nebulae-firstboot.service"
mkdir -p "$R/etc/systemd/system/sysinit.target.wants"
ln -sf /etc/systemd/system/nebulae-firstboot.service "$R/etc/systemd/system/sysinit.target.wants/nebulae-firstboot.service"
touch "$R/etc/nebulae-firstboot"

step "Pi 3 support"
pi3_root "$R"

step "building the root file system"
# No -x/-xdev: overlayfs reports the lower layer's files with another device.
used=$(du -sB1 "$R" | cut -f1)
files=$(find "$R" | wc -l)
fsbytes=$(( (used * 11 / 10 + SPARE * 1048576 + 4194303) / 4194304 * 4194304 ))
inodes=$(( files * 2 > fsbytes / 16384 ? files * 2 : fsbytes / 16384 ))
echo "  $((used / 1048576)) MiB in $files files -> file system $((fsbytes / 1048576)) MiB"
rm -f "$IMG"
head -c $off "$SRC" > "$IMG" || die "copy boot area"
mke2fs -q -F -t ext4 -L ROOT -b 4096 -N $inodes -E offset=$off -d "$R" "$IMG" $((fsbytes / 4096)) ||
    die "mke2fs"
truncate -s $((off + fsbytes)) "$IMG"
echo "$start, $((fsbytes / 512))" | sfdisk -q --no-reread -N $(sfdisk -d "$SRC" | grep -c 'start=') "$IMG" ||
    die "partition table"
pi3_boot "$IMG" "$R"

step "checking"
LN=$(losetup -r -f --show -o $off --sizelimit $fsbytes "$IMG") || die "losetup new"
e2fsck -fn "$LN" >/dev/null 2>&1 || die "e2fsck of the new file system"
echo "  e2fsck ok"
mount -o ro,noload "$LN" "$T/new" || die "mount new"
# type|mode|owner|group|size|link target|path; no size for directories (it
# depends on the file system: overlay here, ext4 there).
listing() {
    ( cd "$1" && find . -path ./lost+found -prune -o -printf '%y|%m|%U|%G|%s|%l|%p\n' |
        awk -F'|' 'BEGIN { OFS = "|" } $1 == "d" { $5 = "-" } { print }' | LC_ALL=C sort )
}
listing "$R" > "$T/m_old"
listing "$T/new" > "$T/m_new"
cmp -s "$T/m_old" "$T/m_new" || { diff "$T/m_old" "$T/m_new" | head -10; die "file lists differ"; }
echo "  metadata identical ($(wc -l < "$T/m_old") entries)"
diff -r --no-dereference -x lost+found "$R" "$T/new" > "$T/diff" 2>&1
if grep -vE '^File .* is a (character special file|block special file|socket|fifo)' "$T/diff" | grep -q .; then
    head -5 "$T/diff"; die "contents differ"
fi
echo "  all file contents identical"
umount "$T/new"

step "compressing"
xz -T0 -6 -k -f -c "$IMG" > "$OUT.part" || die "xz"
xz -t "$OUT.part" || die "xz test"
mv "$OUT.part" "$OUT"
echo "$(sha256sum < "$IMG" | cut -d' ' -f1)  $(basename "$IMG")" > "$OUT.sha256"
[ $KEEP = 1 ] || rm -f "$IMG"
step "done: $OUT ($(du -h "$OUT" | cut -f1); written to a card: $((off / 1048576 + fsbytes / 1048576)) MiB, grows at the first start)"
