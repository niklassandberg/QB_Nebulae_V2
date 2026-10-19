################################################
# Build a firmware update and install it on a Nebulae over the network
#
# sh deploy_fw_update.sh            normal firmware
# sh deploy_fw_update.sh --hwtest   hardware test firmware (see create_fw_update.sh)
#
# 1. create_fw_update.sh builds neb_update.zip
# 2. it is copied to the Nebulae (scp)
# 3. there it is put on the USB stick (/dev/sda1), as you would by hand
# 4. the Nebulae reboots, and update.sh installs it at boot
#    (it reboots once more by itself to install the SC extensions)
# 5. this script waits until the Nebulae is back and shows the version
#
# The USB stick must be in the Nebulae.
# Settings (environment variables):
#   NEB_HOST     default alarm@alarmpi.local
#   NEB_PW       ssh password of alarm, default alarm
#   NEB_ROOT_PW  sudo password (the root password), default root
#   NEB_WAIT     seconds to wait for the update to finish, default 900, 0 = don't wait
################################################

NEB_HOST="${NEB_HOST:-alarm@alarmpi.local}"
NEB_PW="${NEB_PW:-alarm}"
NEB_ROOT_PW="${NEB_ROOT_PW:-root}"
NEB_WAIT="${NEB_WAIT:-900}"

dir="$(pwd)"

# Without a terminal, ssh/scp get the password from this script. In a terminal
# Git Bash's ssh asks for it itself, so the first run sets up a key (below).
askpass="$(mktemp)"
trap 'rm -f "$askpass"' EXIT
printf '#!/bin/sh\necho "%s"\n' "$NEB_PW" > "$askpass"
chmod +x "$askpass"
export SSH_ASKPASS="$askpass" SSH_ASKPASS_REQUIRE=force DISPLAY="${DISPLAY:-none}"
NEB_KEY="${NEB_KEY:-$HOME/.ssh/nebulae_ed25519}"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -i $NEB_KEY"

neb() {
    ssh $SSH_OPTS "$NEB_HOST" "$@" < /dev/null
}

# Log in with a key, so no password is asked again. The first time, the key is
# made and put on the Nebulae (asks for the password of alarm once).
if ! ssh $SSH_OPTS -o BatchMode=yes "$NEB_HOST" true < /dev/null 2>/dev/null; then
    if [ ! -f "$NEB_KEY" ]; then
        mkdir -p "$(dirname "$NEB_KEY")"
        ssh-keygen -q -t ed25519 -N "" -C "nebulae deploy" -f "$NEB_KEY" || exit 1
    fi
    echo "Putting the ssh key on $NEB_HOST (password of alarm: $NEB_PW)"
    ssh $SSH_OPTS "$NEB_HOST" 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys' < "$NEB_KEY.pub" \
        || { echo "can't log in to $NEB_HOST"; exit 1; }
fi

echo "=== 1/4 Building firmware"
rm -f neb_update.zip
sh create_fw_update.sh "$@" || { echo "create_fw_update.sh failed"; exit 1; }
[ -f neb_update.zip ] || { echo "no neb_update.zip was made"; exit 1; }
size=$(wc -c < neb_update.zip | tr -d ' ')
echo "neb_update.zip: $size bytes"

echo "=== 2/4 Copying to $NEB_HOST"
neb true || { echo "can't log in to $NEB_HOST"; exit 1; }
scp $SSH_OPTS neb_update.zip "$NEB_HOST:/tmp/neb_update.zip" < /dev/null || { echo "copy failed"; exit 1; }

echo "=== 3/4 Putting it on the USB stick"
neb "echo '$NEB_ROOT_PW' | sudo -S -p '' bash -c '
    set -e
    [ -b /dev/sda1 ] || { echo \"no USB stick (/dev/sda1) in the Nebulae\"; exit 1; }
    mkdir -p /mnt/memory
    mounted=0
    if ! mountpoint -q /mnt/memory; then mount /dev/sda1 /mnt/memory; mounted=1; fi
    cp /tmp/neb_update.zip /mnt/memory/neb_update.zip
    sync
    got=\$(wc -c < /mnt/memory/neb_update.zip)
    [ \"\$got\" = \"$size\" ] || { echo \"size on the stick is \$got, expected $size\"; exit 1; }
    [ \$mounted = 1 ] && umount /mnt/memory
    rm -f /tmp/neb_update.zip
    echo \"on the stick, rebooting\"
    (sleep 1; reboot) > /dev/null 2>&1 &
'" || { echo "could not put the update on the stick, nothing was changed"; exit 1; }

if [ "$NEB_WAIT" = "0" ]; then
    echo "=== 4/4 Not waiting. The Nebulae installs the update while it boots."
    exit 0
fi

echo "=== 4/4 Waiting for the update (up to $NEB_WAIT s)"
md5=$(md5sum neb_update.zip | cut -d' ' -f1)
sleep 20
start=$(date +%s)
while :; do
    # Done when update.sh has taken this zip (its copy in backup/new), the
    # second stage has run (Code/packages is gone: SC extensions installed)
    # and nebulae.py (or hwtest.py) runs, i.e. startup.sh is through.
    state=$(neb "
        [ \"\$(md5sum /home/alarm/backup/new/neb_update.zip 2>/dev/null | cut -d' ' -f1)\" = $md5 ] || { echo copying; exit; }
        [ -d /home/alarm/QB_Nebulae_V2/Code/packages ] && { echo stage2; exit; }
        pgrep -f 'nebulae/nebulae.py|nebio/tools/hwtest.py' > /dev/null && echo done || echo booting
    " 2>/dev/null)
    if [ "$state" = "done" ]; then
        break
    fi
    if [ $(( $(date +%s) - start )) -gt "$NEB_WAIT" ]; then
        echo; echo "timed out; the Nebulae may still be updating"
        exit 1
    fi
    [ "$state" != "$last" ] && printf ' %s' "${state:-offline}"; last="$state"
    sleep 10
done
echo
neb "grep VERSION /home/alarm/QB_Nebulae_V2/Code/config.txt; uptime"
echo "Done."
cd "$dir"
