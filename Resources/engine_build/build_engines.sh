#!/bin/bash
# Builds the Nebulae's engine packages on a Pi with the 64-bit image, in two
# levels (see README.md next to this script):
#   1. the engines: <engine>/PKGBUILD (Csound, SuperCollider) and Pure Data
#      (the Arch package, no recipe); each is installed when built
#   2. their plugins and externals: <engine>/<dir>/<name>/PKGBUILD, built
#      against the installed engines
# Output: OUT in the layout of Code/engine_packages/ (copy it there).
#   build_engines.sh [OUT]        default OUT=/home/alarm/engine_packages
# Run as root (it installs the build dependencies); makepkg runs as alarm.
# Takes hours on a Pi 3 (Csound ~30 min, sc3-plugins and ELSE longer), so
# start it detached:
#   systemd-run --unit=nebulae-engines bash /path/to/build_engines.sh
# Log: OUT/build.log. Packages already in OUT are not built again: run it
# again after a failure to go on.
set -uo pipefail
SRC=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-/home/alarm/engine_packages}
WORK=/home/alarm/engine_build_work
mkdir -p "$OUT" "$WORK/sources"
chown alarm:alarm "$OUT" "$WORK" "$WORK/sources"
exec >> "$OUT/build.log" 2>&1
echo "==== $(date) build_engines.sh"
# Parallel jobs and memory: a Pi 3 (1 GB, no swap) froze building ELSE's
# ffmpeg with 3 jobs. Under 2 GB: 2 jobs and, for the time of the build, 1 GB
# of compressed swap in RAM (zram), removed again at the end.
mem=$(awk '/^MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
if [ "$mem" -lt 2000 ]; then JOBS=2; else JOBS=3; fi
ZRAM=""
if [ "$mem" -lt 2000 ] && [ -z "$(swapon --show --noheadings)" ] && modprobe zram 2>/dev/null; then
    ZRAM=$(zramctl --find --size 1G --algorithm zstd 2>/dev/null)
    if [ -n "$ZRAM" ] && mkswap "$ZRAM" >/dev/null && swapon -p 100 "$ZRAM"; then
        echo "== $mem MB RAM: $JOBS jobs, swap on $ZRAM (zram, 1 GB)"
    else
        [ -n "$ZRAM" ] && zramctl --reset "$ZRAM"; ZRAM=""
    fi
fi
[ -n "$ZRAM" ] || echo "== $mem MB RAM: $JOBS jobs"
cleanup() { [ -n "$ZRAM" ] && { swapoff "$ZRAM"; zramctl --reset "$ZRAM"; }; }
trap cleanup EXIT
# The recipes, with Unix line endings (files from Windows may have CRLF,
# which bash and makepkg read as part of the values).
HERE=$WORK/recipes
rm -rf "$HERE"; cp -r "$SRC" "$HERE"
find "$HERE" -type f \( -name PKGBUILD -o -name "*.sh" -o -name "*.install" \) -exec sed -i 's/\r$//' {} +
# Native: every package is built for this Pi's CPU, for every recipe that
# uses makepkg's $CFLAGS / $CXXFLAGS (all here do, as a new one normally
# does): -mcpu=native instead of -march=armv8-a, i.e. cortex-a53+crc on a
# Pi 3, cortex-a72+crc on a Pi 4. Both have the same instructions (ARMv8.0 +
# CRC, no crypto), so a package also runs on the other model, only tuned for
# the one it was built on.
CONF=$WORK/makepkg.conf
sed 's/-march=armv8-a/-mcpu=native/' /etc/makepkg.conf > "$CONF"
grep -q -- '-mcpu=native' "$CONF" ||
    printf '%s\n' 'CFLAGS="$CFLAGS -mcpu=native"' 'CXXFLAGS="$CXXFLAGS -mcpu=native"' >> "$CONF"
echo "== compiler: -mcpu=native = $(gcc -mcpu=native -Q --help=target 2>/dev/null | awk '$1 == "-mcpu=" {print $2}')"
# Plugins installed by hand before they were packages: their files may be
# replaced. The rules are in legacy_overwrite.sh (one place, to comment out).
LEGACY_OVERWRITE=()
. "$SRC/legacy_overwrite.sh" 2>/dev/null
OVERWRITE=("${LEGACY_OVERWRITE[@]}")

# The Nebulae's own packages: not in the repositories, built here.
OWN=$(for f in "$HERE"/*/PKGBUILD "$HERE"/*/*/*/PKGBUILD; do ( . "$f"; echo "$pkgname" ); done)
repo_deps() {  # PKGBUILD -> what it needs from the repositories
    ( . "$1"
      for d in "${makedepends[@]}" "${depends[@]}"; do
          n=${d%%[<>=]*}
          case " $(echo $OWN) " in *" $n "*) ;; *) echo "$n" ;; esac
      done )
}
failed=""
build() {  # recipe dir relative to HERE, destination dir relative to OUT
    local rel=$1 dst=$OUT/$2 name ver
    name=$( . "$HERE/$rel/PKGBUILD"; echo "$pkgname" )
    ver=$( . "$HERE/$rel/PKGBUILD"; echo "$pkgver-$pkgrel" )
    if ls "$dst/$name-$ver"-*.pkg.tar.* >/dev/null 2>&1; then
        echo "== $rel: $name $ver already built"
        # Installed, so the next level builds against it.
        [ "$(pacman -Q "$name" 2>/dev/null)" = "$name $ver" ] ||
            pacman -U --noconfirm "${OVERWRITE[@]}" $(ls "$dst/$name-$ver"-*.pkg.tar.* | grep -v '\.sig$') ||
            { echo "== $rel: install FAILED"; failed="$failed $rel"; return 1; }
        return 0
    fi
    echo "== $rel: $name $ver ($(date +%T))"
    pacman -S --noconfirm --needed --disable-sandbox $(repo_deps "$HERE/$rel/PKGBUILD") ||
        { echo "== $rel: build dependencies FAILED"; failed="$failed $rel"; return 1; }
    rm -rf "$WORK/$rel"; mkdir -p "$WORK/$rel"; cp -r "$HERE/$rel/." "$WORK/$rel/"
    chown -R alarm:alarm "$WORK"
    if ! ( cd "$WORK/$rel" && runuser -u alarm -- env MAKEFLAGS=-j$JOBS CMAKE_BUILD_PARALLEL_LEVEL=$JOBS SRCDEST="$WORK/sources" \
            makepkg --config "$CONF" -f --nodeps --noconfirm ); then
        echo "== $rel: makepkg FAILED"; failed="$failed $rel"; return 1
    fi
    mkdir -p "$dst"
    cp "$WORK/$rel/$name-$ver"-*.pkg.tar.* "$dst/"
    chown -R alarm:alarm "$OUT"
    pacman -U --noconfirm "${OVERWRITE[@]}" $(ls "$dst/$name-$ver"-*.pkg.tar.* | grep -v '\.sig$') ||
        { echo "== $rel: install FAILED"; failed="$failed $rel"; return 1; }
}

echo "=== level 1: engines"
for f in "$HERE"/*/PKGBUILD; do
    rel=${f#$HERE/}; rel=${rel%/PKGBUILD}
    build "$rel" "$rel"
done
echo "== puredata: the Arch package (optimised; kept at this version)"
if ls "$OUT"/puredata/pd-[0-9]*.pkg.tar.* >/dev/null 2>&1; then
    echo "== puredata: $(ls "$OUT"/puredata/pd-[0-9]*.pkg.tar.* | grep -v '\.sig$' | xargs -n1 basename) already there"
else
    pacman -S --noconfirm --needed --disable-sandbox pd
    pacman -Sw --noconfirm --disable-sandbox pd >/dev/null    # into the cache if it is not there
    v=$(pacman -Q pd | cut -d' ' -f2)
    mkdir -p "$OUT/puredata"
    cp /var/cache/pacman/pkg/pd-$v-*.pkg.tar.* "$OUT/puredata/" 2>/dev/null ||
        { echo "== puredata: package not found in the cache"; failed="$failed puredata"; }
fi

echo "=== level 2: plugins and externals"
for f in "$HERE"/*/*/*/PKGBUILD; do
    rel=${f#$HERE/}; rel=${rel%/PKGBUILD}
    build "$rel" "$(dirname "$rel")"
done

chown -R alarm:alarm "$OUT"
echo "==== $(date) done${failed:+, FAILED:$failed}"
find "$OUT" -name "*.pkg.tar.*" ! -name "*.sig" | sort
