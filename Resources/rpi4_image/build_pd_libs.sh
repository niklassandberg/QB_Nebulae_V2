#!/bin/bash
# Builds the Pure Data libraries ELSE and cyclone and installs them in
# /usr/lib/pd/extra/else and /usr/lib/pd/extra/cyclone (Pd's own search path).
# nebulae.py starts pd with "-path ... -lib else -lib cyclone" when they exist.
# Run as root on the Pi (compiling runs as alarm); safe to run again.
#   systemd-run --unit=nebulae-pdbuild bash /home/alarm/rpi4_image/build_pd_libs.sh
# Log: /home/alarm/pd_build/build.log. ELSE builds its own ffmpeg: ~1 hour.
ELSE_TAG=v.1.0-rc14       # needs Pd 0.56-1 or newer
CYCLONE_TAG=cyclone_0.9.4 # needs Pd 0.56-2 or newer
DIR=/home/alarm/pd_build
EXTRA=/usr/lib/pd/extra
JOBS=3  # one core free (thermal), as for SuperCollider

mkdir -p $DIR && chown alarm:alarm $DIR
exec > >(tee -a $DIR/build.log) 2>&1
echo "==== $(date) build_pd_libs.sh"
set -e

pacman -S --noconfirm --needed git base-devel cmake openssl zlib bzip2
# ELSE links OpenSSL statically (sfload, play.file~, sfinfo).
if [ ! -e /usr/lib/libssl.a ] || [ ! -e /usr/lib/libcrypto.a ]; then
    echo "WARNING: no static OpenSSL (/usr/lib/libssl.a); the ELSE link may fail"
fi

as_alarm() { runuser -u alarm -- bash -c "$1"; }

fetch() {  # repo tag dir
    if [ -d $DIR/$3/.git ]; then
        as_alarm "cd $DIR/$3 && git fetch -q --depth 1 origin tag $2 && git checkout -q $2"
    else
        as_alarm "git clone -q --depth 1 -b $2 https://github.com/$1 $DIR/$3"
    fi
}

echo "== cyclone $CYCLONE_TAG"
fetch porres/pd-cyclone $CYCLONE_TAG pd-cyclone
as_alarm "cd $DIR/pd-cyclone && make -j$JOBS pdincludepath=/usr/include/pd \
    && rm -rf $DIR/out-cyclone && make install pdincludepath=/usr/include/pd objectsdir=$DIR/out-cyclone"
rm -rf $EXTRA/cyclone && cp -r $DIR/out-cyclone/cyclone $EXTRA/

echo "== ELSE $ELSE_TAG"
fetch porres/pd-else $ELSE_TAG pd-else
# pd.cmake takes the headers from $PD_PATH/src.
as_alarm "mkdir -p $DIR/pdhdr && ln -sfn /usr/include/pd $DIR/pdhdr/src"
as_alarm "cd $DIR/pd-else && cmake -BBuild -DPD_PATH=$DIR/pdhdr && cmake --build Build -j$JOBS"
rm -rf $EXTRA/else && cp -r $DIR/pd-else/Build/else $EXTRA/

echo "== test: load both in pd"
timeout 10 pd -nogui -nosound -nomidi -stderr -noprefs \
    -path $EXTRA/else -path $EXTRA/cyclone -lib else -lib cyclone \
    -send "pd quit" 2>&1 | grep -iE "else|cyclone|error|fail" || true
echo "==== $(date) build_pd_libs.sh done"
