#!/bin/bash
# Builds, on the Nebulae itself, the engine packages that have a recipe but
# no package of its version in /home/alarm/engine_packages/ (the firmware's
# Code/engine_packages/ and the stick's engine_build/, merged in by a firmware update;
# see Resources/engine_build/README.md), natively for this Pi's CPU
# (build_engines.sh), then installs them (engines_check.sh install).
# A firmware update builds nothing; it reports what has no package. Run by
# hand, it takes long:
#   sudo bash /home/alarm/QB_Nebulae_V2/Code/scripts/engines_build.sh
# Nothing missing: it does nothing.
# Internet for the sources and build tools:
#  1. the LAN (Ethernet), when it has internet
#  2. else Wi-Fi as a client, when the file wlan0-wifi (no extension) is on
#     the USB stick: the netctl profile start_wifi.sh uses for the home
#     network too, e.g.
#       Description='wifi for netctl'
#       Interface=wlan0
#       Connection=wireless
#       Security=wpa                (or none: an open network, no Key)
#       ESSID=YourWifiNetworkName
#       IP=dhcp
#       Key=YourWifiPassword
#     Only ESSID, Key, Security and Hidden are used here, with any quotes
#     (wifi_profile.sh); the file is read as text (not run) and only into
#     RAM (/tmp), never written to the SD card.
#  3. else nothing is built and the installed engines stay.
# Report: neb_engines_report.txt on the stick (what was missing, the
# network, what was built or why not); one line in neb_log.txt.
# A build takes minutes (a UGen) to hours (Csound, sc3-plugins, ELSE) on a
# Pi 3. The Wi-Fi it set up is taken down again at the end.

# Needs root. Started by hand it runs itself again with sudo.
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"
E=/home/alarm/engine_packages
STICK=/mnt/memory
# The USB stick (report, wlan0-wifi): mounted for the build if it is in and
# not mounted yet, and unmounted again at the end.
USB=/home/alarm/QB_Nebulae_V2/Code/scripts/usb_power.sh
stick_mounted=""; usb_was_off=""
if ! grep -qs " $STICK " /proc/mounts; then
    bash $USB status || { usb_was_off=1; bash $USB on; }  # Quiet mode: USB may be off
    if [ -b /dev/sda1 ]; then
        mkdir -p $STICK && mount /dev/sda1 $STICK && stick_mounted=1
    fi
fi
REPORT=/tmp/neb_engines_report.txt
WPA=/tmp/neb_build_wifi.conf
NETF=/run/systemd/network/40-neb-build-wifi.network
: > $REPORT
say() { echo "engines build: $*"; echo "$*" >> $REPORT; last_say="$*"; }
finish() {  # exit code
    if [ -n "${wpa_pid:-}" ]; then
        kill "$wpa_pid" 2>/dev/null
        rm -f "$NETF"; networkctl reload 2>/dev/null
        rfkill block wifi 2>/dev/null
    fi
    rm -f "$WPA"
    if grep -qs " $STICK " /proc/mounts; then
        cp $REPORT $STICK/neb_engines_report.txt
        echo "$(date +"%a %D - %T") - engines: ${summary:-$last_say}" >> $STICK/neb_log.txt
        sync
    fi
    release_stick
    exit "$1"
}
release_stick() {  # as it was before: unmounted, USB off (Quiet mode)
    [ -n "$stick_mounted" ] && umount $STICK
    [ -n "$usb_was_off" ] && bash $USB off
    stick_mounted=""; usb_was_off=""
}
# The new packages installed, the older files deleted (no merge: the
# stick's engine_build/ is only taken in by a firmware update).
install_built() { bash "$(dirname "$0")/engines_check.sh" install; }

# What is missing: a recipe without its package (level 1: <engine>/PKGBUILD,
# package next to it; level 2: <engine>/<dir>/<name>/PKGBUILD, package in <dir>).
missing=""
for f in $E/*/PKGBUILD $E/*/*/*/PKGBUILD; do
    [ -f "$f" ] || continue
    d=$(dirname "$f"); rel=${d#$E/}
    nv=$( eval "$(tr -d '\r' < "$f")"; echo "$pkgname $pkgver-$pkgrel" )
    case "$rel" in */*/*) dst=$(dirname "$d") ;; *) dst=$d ;; esac
    ls "$dst/${nv% *}-${nv#* }"-*.pkg.tar.* >/dev/null 2>&1 || missing="$missing $rel(${nv/ / })"
done
if [ -z "$missing" ]; then
    echo "engines build: every recipe has its package, nothing to build"
    release_stick; exit 0
fi
say "$(date) - $(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"
say "no package for:$missing"

# Network: the LAN first (faster, nothing to set up), else Wi-Fi with the
# wlan0-wifi profile from the stick.
have_internet() { curl -sfI --max-time 10 https://github.com >/dev/null 2>&1; }
net=""
say "LAN: trying"
for i in /sys/class/net/e*; do ip link set "$(basename $i)" up 2>/dev/null; done  # quiet level 1 puts it down
systemctl start systemd-networkd systemd-resolved
/usr/lib/systemd/systemd-networkd-wait-online --any --timeout=20 >/dev/null 2>&1
if have_internet; then net="LAN"; else say "LAN: no internet"; fi
PROFILE=$STICK/wlan0-wifi
# A value of the netctl profile, without whatever quotes it was written with.
profile() { bash /home/alarm/QB_Nebulae_V2/Code/scripts/wifi_profile.sh get "$PROFILE" "$1"; }
if [ -z "$net" ] && [ -f "$PROFILE" ]; then
    ssid=$(profile ESSID)
    pass=$(profile Key)
    security=$(profile Security | tr A-Z a-z)
    hidden=$(profile Hidden | tr A-Z a-z)
    [ "$security" = none ] && pass=""
    if [ -z "$ssid" ]; then
        say "wlan0-wifi has no ESSID= line"
    elif [ -n "$security" ] && [ "$security" != wpa ] && [ "$security" != none ]; then
        say "wlan0-wifi: Security=$security is not supported here (wpa or none)"
    else
        say "Wi-Fi: joining \"$ssid\""
        bash /home/alarm/QB_Nebulae_V2/Code/scripts/wifi.sh driver
        rfkill unblock wifi
        netctl stop-all 2>/dev/null
        pkill -f "wpa_supplicant.*wlan0"
        umask 077
        if [ -n "$pass" ]; then
            wpa_passphrase "$ssid" "$pass" | grep -v '^\s*#psk=' > $WPA
        else
            printf 'network={\n\tssid="%s"\n\tkey_mgmt=NONE\n}\n' "$ssid" > $WPA
        fi
        # Hidden=yes: the network does not announce itself, ask for it by name.
        [ "$hidden" = yes ] && sed -i 's/^}$/\tscan_ssid=1\n}/' $WPA
        umask 022
        wpa_supplicant -B -i wlan0 -c $WPA -P /tmp/neb_build_wpa.pid >/dev/null 2>&1
        wpa_pid=$(cat /tmp/neb_build_wpa.pid 2>/dev/null)
        mkdir -p /run/systemd/network
        printf '[Match]\nName=wlan0\n[Network]\nDHCP=yes\n' > $NETF
        networkctl reload
        /usr/lib/systemd/systemd-networkd-wait-online -i wlan0 --timeout=60 >/dev/null 2>&1
        if have_internet; then net="Wi-Fi \"$ssid\""; else say "Wi-Fi: no internet through \"$ssid\""; fi
    fi
elif [ -z "$net" ]; then
    say "Wi-Fi: no wlan0-wifi on the stick"
fi
if [ -z "$net" ]; then
    say "NOT BUILT: no internet (connect a LAN cable or put wlan0-wifi on the stick, then update again)"
    finish 1
fi
say "internet through $net"
# The clock: the Pi has none, and HTTPS and the package signatures need it.
systemctl unmask --runtime systemd-timesyncd >/dev/null 2>&1
systemctl start systemd-timesyncd
for i in $(seq 60); do
    [ "$(timedatectl show -p NTPSynchronized --value)" = yes ] && break
    sleep 1
done
say "time: $(date) (synchronised: $(timedatectl show -p NTPSynchronized --value))"

# Build (only what is missing; build_engines.sh skips what has a package) and
# take the build tools off again afterwards.
before=$(pacman -Qq | sort)
pacman -Sy --noconfirm --disable-sandbox >/dev/null 2>&1
start=$(date +%s)
bash $E/build_engines.sh $E
rc=$?
own=$(for f in $E/*/PKGBUILD $E/*/*/*/PKGBUILD; do ( eval "$(tr -d '\r' < "$f")"; echo "$pkgname" ); done; echo pd)
new=$(comm -13 <(echo "$before") <(pacman -Qq | sort) | grep -vxF "$own")
if [ -n "$new" ]; then
    pacman -D --asdeps $new >/dev/null 2>&1
    orphans=$(comm -12 <(echo "$new" | sort) <(pacman -Qdtq 2>/dev/null | sort))
    [ -n "$orphans" ] && pacman -Rns --noconfirm $orphans >/dev/null 2>&1
fi
rm -rf /home/alarm/engine_build_work
# This run only: build.log is appended to, from its last start line on.
first=$(grep -n '^==== .*build_engines.sh$' $E/build.log | tail -1 | cut -d: -f1)
this_run() { tail -n +"${first:-1}" $E/build.log; }
this_run | grep -E '^(==|====) ' >> $REPORT   # its own step lines, not makepkg's "==>"
# The result is this run's "==== <date> done[, FAILED: ...]" line (the log
# goes on after it with the list of package files). No such line: the build
# stopped before the end.
result=$(this_run | grep '^==== .* done' | tail -1)
# Not everything built: why, on the stick. In the report the last lines
# before each FAILED (usually the compiler's error), and this run's whole log
# as neb_engines_build.log.gz (a few hundred KB; the log itself is MBs).
failed_log() {
    this_run | grep -n 'FAILED$' | cut -d: -f1 | while read -r n; do
        echo; echo "---- $(this_run | sed -n "${n}p")"
        this_run | sed -n "$(( n > 30 ? n - 30 : 1 )),$(( n - 1 ))p"
    done >> $REPORT
    if grep -qs " $STICK " /proc/mounts; then
        this_run | gzip > $STICK/neb_engines_build.log.gz
        say "log: neb_engines_build.log.gz on the stick"
    fi
}
if [ -z "$result" ] || [ "$rc" != 0 ]; then
    summary="BUILD STOPPED after $(( ($(date +%s) - start) / 60 )) min (exit $rc; log: /home/alarm/engine_packages/build.log)"
    say "$summary"
    failed_log
    install_built   # what did build: installed, old files deleted
    finish 1
elif [[ $result == *FAILED* ]]; then
    summary="BUILT WITH ERRORS after $(( ($(date +%s) - start) / 60 )) min:${result#*FAILED:} (log: /home/alarm/engine_packages/build.log)"
    say "$summary"
    failed_log
    install_built   # what did build: installed, old files deleted
    finish 1
fi
rm -f $STICK/neb_engines_build.log.gz  # an old one from a failed build before
say "built after $(( ($(date +%s) - start) / 60 )) min"
install_built
finish 0
