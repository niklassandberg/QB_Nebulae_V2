#!/bin/bash
# The Nebulae's audio engines and their plugins, as packages in
# /home/alarm/engines/ (recipes in Resources/engines/, same layout):
#   <engine>/*.pkg.tar.*            level 1: the engines
#   <engine>/<plugins>/*.pkg.tar.*  level 2: plugins, externals
# /home/alarm/engines/ is outside the firmware folder, so a firmware update
# keeps what was built on this Nebulae. At each run (firmware update) first:
#  - the firmware's Code/engines/ is merged in: its recipes and scripts
#    replace the old ones, its packages are added, nothing is deleted
#  - the USB stick's engines/ folder too (same layout: your own recipes, or
#    ready packages), only its engine folders (not the scripts)
#  - the first time: the packages of the previous firmware (the update's
#    backup in /home/alarm/backup/old) are taken over
# Nothing is built here: a recipe with no package of its version is only
# reported (on the stick: neb_engines_report.txt); build it on the Nebulae
# with Code/scripts/engines_build.sh. After the install the package files of
# other versions are deleted.
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
#   engines_check.sh           merge, report what has no package, install
#   engines_check.sh install   only install (engines_build.sh after a build)
#   engines_check.sh status    list them; exit 0 = all installed

# Needs root. The services start it as root; started by hand it runs
# itself again with sudo (sudo as root only adds lines to the journal).
[ "$(id -u)" = 0 ] || exec sudo bash "$0" "$@"
DIR=/home/alarm/engines
FIRMWARE=/home/alarm/QB_Nebulae_V2/Code/engines
STICK=/mnt/memory/engines
OLD=/home/alarm/backup/old/QB_Nebulae_V2/Code/engines   # update.sh's backup
ARCH=$(pacman-conf Architecture | head -1)

merge() {
    local first=""
    [ -d $DIR ] || first=1
    mkdir -p $DIR
    # The first time: what the previous firmware had built (Code/engines/ in
    # it), so it is not built again.
    if [ -n "$first" ] && [ -d $OLD ]; then
        (cd $OLD && find . -name "*.pkg.tar.*" -exec cp --parents -n {} $DIR/ \;)
        echo "engines: packages of the previous firmware taken over"
    fi
    [ -d $FIRMWARE ] && cp -r $FIRMWARE/. $DIR/
    if grep -qs " /mnt/memory " /proc/mounts && [ -d $STICK ]; then
        for d in $STICK/*/; do
            [ -d "$d" ] && cp -r "$d" $DIR/ && echo "engines: $(basename "$d")/ from the stick"
        done
    fi
    chown -R alarm:alarm $DIR
}

# After the install: the older package files (older() below) go.
remove_old() {
    for p in $(older 1) $(older 2); do
        rm -f "$p" "$p.sig"
        echo "engines: old package removed: $(basename "$p")"
    done
}
all_pkgs() {  # level: 1 = $DIR/*/, 2 = $DIR/*/*/
    local glob=$DIR/*; [ "$1" = 2 ] && glob=$DIR/*/*
    ls $glob/*-$ARCH.pkg.tar.* $glob/*-any.pkg.tar.* 2>/dev/null | grep -v '\.sig$'
}
# Per package only one file counts (others can lie next to it until
# remove_old, e.g. a new version just built): the one with the version of its
# recipe (PKGBUILD) - versions like 0+gfb481d4 (a commit) cannot be compared
# as newer/older; without a recipe (Pd, the Arch package) the highest version
# (vercmp). Name and version are read from each package (pacman -Qp), as file
# names have dashes of their own (sc-guttersynth-0+gfb481d4-1-...).
# Prints "current|older <file>" lines.
sort_pkgs() {
    declare -A recipe best ver
    local f p nv name v
    for f in $DIR/*/PKGBUILD $DIR/*/*/*/PKGBUILD; do
        [ -f "$f" ] || continue
        # A recipe without name or version (broken, e.g. from a stick) is skipped.
        nv=$( eval "$(tr -d '\r' < "$f")" 2>/dev/null
              [ -n "${pkgname:-}" ] && [ -n "${pkgver:-}" ] && echo "$pkgname $pkgver-${pkgrel:-1}" )
        [ -n "$nv" ] && recipe[${nv%% *}]=${nv#* }
    done
    for p in $(all_pkgs $1); do
        nv=$(pacman -Qp "$p" 2>/dev/null) || continue
        name=${nv%% *}; v=${nv#* }
        if [ -z "${best[$name]:-}" ]; then
            best[$name]=$p; ver[$name]=$v; continue
        fi
        if [ -n "${recipe[$name]:-}" ]; then
            [ "$v" = "${recipe[$name]}" ] && better=1 || better=""
        else
            [ "$(vercmp "$v" "${ver[$name]}")" -gt 0 ] && better=1 || better=""
        fi
        if [ -n "$better" ]; then
            echo "older ${best[$name]}"; best[$name]=$p; ver[$name]=$v
        else
            echo "older $p"
        fi
    done
    for name in "${!best[@]}"; do echo "current ${best[$name]}"; done
}
pkgs() { sort_pkgs $1 | sed -n 's/^current //p'; }
older() { sort_pkgs $1 | sed -n 's/^older //p'; }
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
# Recipes without a package of their version (level 1: package next to the
# recipe, level 2: in the folder above it): not built here, only reported.
unbuilt() {
    local f d rel nv dst
    for f in $DIR/*/PKGBUILD $DIR/*/*/*/PKGBUILD; do
        [ -f "$f" ] || continue
        d=$(dirname "$f"); rel=${d#$DIR/}
        nv=$( eval "$(tr -d '\r' < "$f")" 2>/dev/null
              [ -n "${pkgname:-}" ] && [ -n "${pkgver:-}" ] && echo "$pkgname $pkgver-${pkgrel:-1}" )
        [ -n "$nv" ] || continue
        case "$rel" in */*/*) dst=$(dirname "$d") ;; *) dst=$d ;; esac
        ls "$dst/${nv% *}-${nv#* }"-*.pkg.tar.* >/dev/null 2>&1 || echo "$rel (${nv/ / })"
    done
}
report_unbuilt() {
    local list; list=$(unbuilt)
    [ -n "$list" ] || return
    echo "$list" | sed 's/^/engines: no package for /'
    echo "engines: build them on the Nebulae: sudo bash $(dirname "$0")/engines_build.sh"
    if grep -qs " /mnt/memory " /proc/mounts; then
        { echo "$(date) - not built (no package in the firmware or on the stick):"
          echo "$list"
          echo "Build them on the Nebulae: sudo bash /home/alarm/QB_Nebulae_V2/Code/scripts/engines_build.sh"
        } > /mnt/memory/neb_engines_report.txt
    fi
}
case "$1" in
    status|install) ;;              # status: only list; install: after engines_build.sh
    *) merge; report_unbuilt ;;     # firmware update (update.sh), setup_system.sh
esac
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
    # Plugins installed by hand before they were packages: their files may be
    # replaced. The rules are in legacy_overwrite.sh (one place, to comment out).
    LEGACY_OVERWRITE=()
    . $DIR/legacy_overwrite.sh 2>/dev/null
    pacman --noconfirm -U "${LEGACY_OVERWRITE[@]}" $need ||
        { echo "engines: level $level install failed"; exit 1; }
done
remove_old
# pacman -Syu must not bring the Arch packages back.
for name in $names; do
    grep -qE "^IgnorePkg.*[ =]$name( |\$)" /etc/pacman.conf && continue
    if grep -q '^IgnorePkg' /etc/pacman.conf; then
        sed -i "0,/^IgnorePkg.*/s//& $name/" /etc/pacman.conf
    else
        sed -i "/^\[options\]/a IgnorePkg = $name" /etc/pacman.conf
    fi
    echo "engines: $name added to IgnorePkg in /etc/pacman.conf"
done
exit 0
