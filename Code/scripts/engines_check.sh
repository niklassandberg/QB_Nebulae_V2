#!/bin/bash
# The Nebulae's audio engines and their plugins, as packages in Code/engines/
# (recipes in Resources/engines/, same layout):
#   Code/engines/<engine>/*.pkg.tar.*            level 1: the engines
#   Code/engines/<engine>/<plugins>/*.pkg.tar.*  level 2: plugins, externals
#  - csound: optimised and -B working. The Arch Linux ARM package is built
#    without optimisation (3x slower: constant dropouts on a Pi 3), ignores -B.
#  - supercollider: supercollider-headless (headless, JACK, libscsynth);
#    plugins: sc3-plugins, GutterSynth, XPlayBuf, SuperBufRd.
#  - puredata: the Arch package (built with optimisation, checked), kept at
#    this version; externals: cyclone, ELSE.
# Run by update.sh after a firmware update (root file system read-write) and
# by setup_system.sh. Installs every package whose version is not the one
# installed: the engines first, then the plugins (they are built against the
# engines). All of them go in IgnorePkg so pacman -Syu keeps them.
#   engines_check.sh           install what is needed
#   engines_check.sh status    list them; exit 0 = all installed
DIR=/home/alarm/QB_Nebulae_V2/Code/engines
ARCH=$(pacman-conf Architecture | head -1)
pkgs() {  # level: 1 = $DIR/*/, 2 = $DIR/*/*/
    local glob=$DIR/*; [ "$1" = 2 ] && glob=$DIR/*/*
    ls $glob/*-$ARCH.pkg.tar.* $glob/*-any.pkg.tar.* 2>/dev/null | grep -v '\.sig$'
}
names=""; missing=0
check() {  # level -> $need: the package files to install
    need=""
    for p in $(pkgs $1); do
        want=$(pacman -Qp "$p" 2>/dev/null)    # e.g. "csound 6.18.1-10.1"
        name=${want%% *}
        [ -n "$name" ] || { echo "engines: cannot read $p"; continue; }
        names="$names $name"
        have=$(pacman -Q "$name" 2>/dev/null)
        if [ "$have" = "$want" ]; then
            echo "engines: $have (Nebulae) is installed"
        else
            echo "engines: $want needed (installed: ${have:-none})"
            need="$need $p"; missing=1
        fi
    done
}
# Fallback: a recipe without its package is built on the Nebulae first (needs
# internet: LAN, else Wi-Fi from wifi_credentials.txt on the stick; report on
# the stick). Normally the firmware has every package and nothing happens.
[ "$1" = status ] || sudo bash "$(dirname "$0")/engines_build.sh"
if [ -z "$(pkgs 1)$(pkgs 2)" ]; then
    echo "engines: no packages for $ARCH in $DIR, keeping the installed ones"
    [ "$1" = status ] && exit 1
    exit 0
fi
if [ "$1" = status ]; then
    check 1; check 2
    exit $missing
fi
for level in 1 2; do
    check $level
    [ -n "$need" ] || continue
    # Plugins installed by hand before they were packages (old build_sc.sh,
    # build_pd_libs.sh): their files may be replaced.
    sudo pacman --noconfirm -U \
        --overwrite '/usr/share/SuperCollider/Extensions/*' \
        --overwrite '/usr/lib/pd/extra/*' $need ||
        { echo "engines: level $level install failed"; exit 1; }
done
# pacman -Syu must not bring the Arch packages back.
for name in $names; do
    grep -qE "^IgnorePkg.*[ =]$name( |\$)" /etc/pacman.conf && continue
    if grep -q '^IgnorePkg' /etc/pacman.conf; then
        sudo sed -i "0,/^IgnorePkg.*/s//& $name/" /etc/pacman.conf
    else
        sudo sed -i "/^\[options\]/a IgnorePkg = $name" /etc/pacman.conf
    fi
    echo "engines: $name added to IgnorePkg in /etc/pacman.conf"
done
exit 0
