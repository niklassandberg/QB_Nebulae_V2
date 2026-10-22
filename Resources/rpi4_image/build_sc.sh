#!/bin/bash
# Builds and installs SuperCollider 3.14.1 headless (Resources/sc_pkg/rpi4/
# PKGBUILD), sc3-plugins 3.14.1 and the Nebulae's own UGens (GutterSynth,
# SuperBufRd, XPlayBuf) on the Pi. Run as root; the compiling runs as alarm.
# Takes hours (-j3), so start it detached:
#   systemd-run --unit=nebulae-scbuild bash /home/alarm/rpi4_image/build_sc.sh
#   journalctl -u nebulae-scbuild -f        (or tail -f /home/alarm/sc_build/build.log)
# Each part is skipped when it is already installed, so it can be run again.
set -e
B=/home/alarm/sc_build
NEB=/home/alarm/QB_Nebulae_V2
HERE=$(cd "$(dirname "$0")" && pwd)
# PKGBUILD: next to this script on the Pi, Resources/sc_pkg/rpi4 in the repo
PKG=$HERE/PKGBUILD; [ -f $PKG ] || PKG=$HERE/../sc_pkg/rpi4/PKGBUILD
SCSRC=$B/sc_pkg/src/supercollider
EXT=/usr/share/SuperCollider/Extensions
mkdir -p $B && chown alarm:alarm $B
exec >> $B/build.log 2>&1
as_alarm() { runuser -u alarm -- "$@"; }
echo "==== $(date) build_sc.sh start"

echo "== build dependencies"
pacman -S --noconfirm --needed jack2 libsndfile fftw boost boost-libs yaml-cpp libxt \
    alsa-lib python git cmake pkgconf base-devel

if ! pacman -Q supercollider-headless >/dev/null 2>&1; then
    echo "== SuperCollider (makepkg)"
    as_alarm mkdir -p $B/sc_pkg
    as_alarm cp $PKG $B/sc_pkg/PKGBUILD
    cd $B/sc_pkg
    as_alarm makepkg -f --skipchecksums --nodeps
    pacman -U --noconfirm $B/sc_pkg/supercollider-headless-*.pkg.tar.*
fi
sclang -v 2>/dev/null | head -1 || true

as_alarm mkdir -p $B/ugens
cd $B/ugens
clone() {  # dir url commit/tag
    [ -d "$1" ] || as_alarm git clone -q --recursive "$2" "$1"
    (cd "$1" && as_alarm git checkout -q "$3" && as_alarm git submodule update -q --init --recursive)
}
cmake_ugen() {  # dir extra-cmake-args...
    d=$1; shift
    as_alarm cmake -S $d -B $d/build -DSC_PATH=$SCSRC -DCMAKE_BUILD_TYPE=Release \
        -DSUPERNOVA=OFF -DCMAKE_POLICY_VERSION_MINIMUM=3.5 "$@"
    as_alarm cmake --build $d/build -- -j3
}

if [ ! -d $EXT/SC3plugins ]; then
    echo "== sc3-plugins"
    clone sc3-plugins https://github.com/supercollider/sc3-plugins.git Version-3.14.1
    cmake_ugen sc3-plugins -DCMAKE_INSTALL_PREFIX=/usr -DNATIVE=ON
    cmake --build sc3-plugins/build --target install
fi

if [ ! -d $EXT/GutterSynth ]; then
    echo "== GutterSynth"
    clone guttersynth-sc https://github.com/madskjeldgaard/guttersynth-sc.git fb481d4
    cmake_ugen guttersynth-sc -DCMAKE_INSTALL_PREFIX=$B/ugens/install
    cmake --build guttersynth-sc/build --target install
    cp -r $B/ugens/install/GutterSynth $EXT/
fi

if [ ! -d $EXT/XPlayBuf ]; then
    echo "== XPlayBuf"
    clone XPlayBuf https://github.com/elgiano/XPlayBuf.git 44b9077
    cmake_ugen XPlayBuf -DCMAKE_INSTALL_PREFIX=$B/ugens/install
    cmake --build XPlayBuf/build --target install
    cp -r $B/ugens/install/XPlayBuf $EXT/
fi

if [ ! -d $EXT/SuperBufRd ]; then
    echo "== SuperBufRd (no install target: copied by hand)"
    clone super-bufrd https://github.com/esluyter/super-bufrd.git e1e19f9
    cmake_ugen super-bufrd -DCPP11=OFF -DCMAKE_CXX_STANDARD=17
    mkdir -p $EXT/SuperBufRd
    cp super-bufrd/build/*.so $EXT/SuperBufRd/
    for d in Classes SystemOverwrites HelpSource; do
        [ -d super-bufrd/$d ] && cp -r super-bufrd/$d $EXT/SuperBufRd/
    done
fi

echo "== Nebulae extensions (MultiWtOsc, NebInterface)"
if [ -d $NEB/SuperColliderExtensions ]; then
    for item in $NEB/SuperColliderExtensions/*; do
        rm -rf "$EXT/$(basename "$item")"
        cp -r "$item" $EXT/
    done
fi

systemctl enable sclang.service
echo "==== $(date) build_sc.sh done"
ls $EXT
