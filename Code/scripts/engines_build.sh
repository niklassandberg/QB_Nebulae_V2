#!/bin/bash
# Fallback after a firmware update: builds, on the Nebulae itself, the engine
# packages the firmware has a recipe for but no package (Code/engines/, see
# Resources/engines/README.md). Normally the firmware has them all and this
# does nothing. Run by engines_check.sh, with the root file system read-write
# and the USB stick mounted (update.sh).
# Internet for the sources and build tools:
#  1. the LAN (Ethernet), when it has internet
#  2. else Wi-Fi as a client, when wifi_credentials.txt is on the USB stick:
#       SSID=My network
#       PASSWORD=my password        (no PASSWORD line: an open network)
#     It is only read into RAM (/tmp), never written to the SD card.
#  3. else nothing is built and the installed engines stay.
# Report: neb_engines_report.txt on the stick (what was missing, the
# network, what was built or why not); one line in neb_log.txt.
# A build takes minutes (a UGen) to hours (Csound, sc3-plugins, ELSE) on a
# Pi 3; the update LEDs stay on meanwhile. A reboot follows the update, so
# the Wi-Fi and time settings made here are temporary.
E=/home/alarm/QB_Nebulae_V2/Code/engines
STICK=/mnt/memory
REPORT=/tmp/neb_engines_report.txt
WPA=/tmp/neb_build_wifi.conf
NETF=/run/systemd/network/40-neb-build-wifi.network
: > $REPORT
say() { echo "engines build: $*"; echo "$*" >> $REPORT; }
finish() {  # exit code
    if [ -n "${wpa_pid:-}" ]; then
        kill "$wpa_pid" 2>/dev/null
        rm -f "$NETF"; networkctl reload 2>/dev/null
        rfkill block wifi 2>/dev/null
    fi
    rm -f "$WPA"
    if grep -qs " $STICK " /proc/mounts; then
        cp $REPORT $STICK/neb_engines_report.txt
        echo "$(date +"%a %D - %T") - engines: $(tail -1 $REPORT)" >> $STICK/neb_log.txt
        sync
    fi
    exit "$1"
}

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
[ -n "$missing" ] || exit 0    # every recipe has its package: nothing to build
say "$(date) - $(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"
say "no package in the firmware for:$missing"

# Network: the LAN first (faster, nothing to set up), else Wi-Fi with the
# credentials from the stick.
have_internet() { curl -sfI --max-time 10 https://github.com >/dev/null 2>&1; }
net=""
say "LAN: trying"
for i in /sys/class/net/e*; do ip link set "$(basename $i)" up 2>/dev/null; done  # quiet level 1 puts it down
systemctl start systemd-networkd systemd-resolved
/usr/lib/systemd/systemd-networkd-wait-online --any --timeout=20 >/dev/null 2>&1
if have_internet; then net="LAN"; else say "LAN: no internet"; fi
CRED=$STICK/wifi_credentials.txt
if [ -z "$net" ] && [ -f "$CRED" ]; then
    ssid=$(tr -d '\r' < "$CRED" | sed -n 's/^SSID=//p' | head -1)
    pass=$(tr -d '\r' < "$CRED" | sed -n 's/^PASSWORD=//p' | head -1)
    if [ -z "$ssid" ]; then
        say "wifi_credentials.txt has no SSID= line"
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
    say "Wi-Fi: no wifi_credentials.txt on the stick"
fi
if [ -z "$net" ]; then
    say "NOT BUILT: no internet (connect a LAN cable or put wifi_credentials.txt on the stick, then update again)"
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
rm -rf /home/alarm/engines_build
sed -n '/^==== .*build_engines.sh$/,$p' $E/build.log | grep -E '^==' >> $REPORT
if grep -q 'FAILED' <(tail -1 $E/build.log); then
    say "BUILT WITH ERRORS after $(( ($(date +%s) - start) / 60 )) min: $(tail -1 $E/build.log | sed 's/.*FAILED://') (log: Code/engines/build.log)"
    finish 1
fi
say "built after $(( ($(date +%s) - start) / 60 )) min"
finish 0
