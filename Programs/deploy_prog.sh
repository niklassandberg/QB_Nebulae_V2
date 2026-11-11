#!/bin/sh
################################################
# Put a program on the Nebulae's USB stick over the network
#
# ./deploy_prog.sh audrey
#
# Copies Programs/<name>/<name>.prog and the binary its run, line names to the
# root of the stick (where Nebulae reads programs from), and the same files to
# /home/alarm/prog, so reselecting the program plays the new version at once.
# The saved values (<name>.pages) are left alone.
#
# Settings (environment variables), as deploy_fw_update.sh:
#   NEB_HOST     default alarm@alarmpi.local
#   NEB_PW       ssh password of alarm, default alarm
#   NEB_ROOT_PW  sudo password (the root password), default root
################################################

NEB_HOST="${NEB_HOST:-alarm@alarmpi.local}"
NEB_PW="${NEB_PW:-alarm}"
NEB_ROOT_PW="${NEB_ROOT_PW:-root}"

here="$(cd "$(dirname "$0")" && pwd)"

usage() {
    echo "usage: $0 <program>"
    echo "programs:"
    for p in "$here"/*/*.prog; do
        [ -f "$p" ] && echo "  $(basename "$p" .prog)"
    done
    exit 1
}

[ $# = 1 ] || usage

# The folder of the program, any case: "Proxy" for proxy.
dir=""
for d in "$here"/*/; do
    d="${d%/}"
    if [ "$(basename "$d" | tr 'A-Z' 'a-z')" = "$(echo "$1" | tr 'A-Z' 'a-z')" ]; then
        dir="$d"
    fi
done
[ -n "$dir" ] || { echo "no program \"$1\" in $here"; usage; }
set -- "$dir"/*.prog
[ -f "$1" ] || { echo "no .prog in $dir"; exit 1; }
prog="$1"

run=$(sed -n '/^nebconfigbegin/,/^nebconfigend/s/^run,\([^[:space:]]*\).*/\1/p' "$prog" | tr -d '\r' | tail -n 1)
files="$prog"
if [ -n "$run" ] && [ -f "$dir/$run" ]; then
    files="$files $dir/$run"
elif [ -n "$run" ]; then
    echo "note: run,$run is not in $dir (an installed command?), only the .prog is copied"
fi

# ssh with the key deploy_fw_update.sh sets up; without it, the password.
askpass="$(mktemp)"
trap 'rm -f "$askpass"' EXIT
printf '#!/bin/sh\necho "%s"\n' "$NEB_PW" > "$askpass"
chmod +x "$askpass"
export SSH_ASKPASS="$askpass" SSH_ASKPASS_REQUIRE=force DISPLAY="${DISPLAY:-none}"
NEB_KEY="${NEB_KEY:-$HOME/.ssh/nebulae_ed25519}"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
[ -f "$NEB_KEY" ] && SSH_OPTS="$SSH_OPTS -i $NEB_KEY"

echo "=== Copying to $NEB_HOST:"
for f in $files; do echo "  $(basename "$f")"; done
ssh $SSH_OPTS "$NEB_HOST" 'rm -rf /tmp/deploy_prog && mkdir /tmp/deploy_prog' < /dev/null \
    || { echo "can't log in to $NEB_HOST"; exit 1; }
scp -p $SSH_OPTS $files "$NEB_HOST:/tmp/deploy_prog/" < /dev/null || { echo "copy failed"; exit 1; }

echo "=== Putting it on the USB stick and in /home/alarm/prog"
ssh $SSH_OPTS "$NEB_HOST" "echo '$NEB_ROOT_PW' | sudo -S -p '' sh -c '
    set -e
    cd /tmp/deploy_prog
    [ -b /dev/sda1 ] || { echo \"no USB stick (/dev/sda1) in the Nebulae\"; exit 1; }
    mkdir -p /mnt/memory
    mounted=0
    if ! mountpoint -q /mnt/memory; then mount /dev/sda1 /mnt/memory; mounted=1; fi
    ok=1
    for f in *; do
        cp --preserve=timestamps \"\$f\" /mnt/memory/\"\$f\" || ok=0
    done
    sync
    for f in *; do
        cmp -s \"\$f\" /mnt/memory/\"\$f\" || { echo \"\$f differs on the stick\"; ok=0; }
    done
    [ \$mounted = 1 ] && umount /mnt/memory
    [ \$ok = 1 ]
    ro=0
    grep -q \" / [^ ]* ro[ ,]\" /proc/mounts && { mount -o remount,rw /; ro=1; }
    mkdir -p /home/alarm/prog
    for f in *; do
        # A running binary cannot be overwritten (text file busy), but replaced.
        cp -p \"\$f\" /home/alarm/prog/.\"\$f\".new
        case \"\$f\" in *.prog) ;; *) chmod 755 /home/alarm/prog/.\"\$f\".new ;; esac
        mv -f /home/alarm/prog/.\"\$f\".new /home/alarm/prog/\"\$f\"
    done
    sync
    [ \$ro = 1 ] && mount -o remount,ro /
    rm -rf /tmp/deploy_prog
    echo \"done: reselect the program on the Nebulae to play the new version\"
'" < /dev/null || { echo "could not put it on the stick, check the Nebulae"; exit 1; }
