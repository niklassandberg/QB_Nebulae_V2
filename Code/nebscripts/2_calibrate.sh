#!/bin/bash
# Calibrate the CV inputs, from the scripts page of the instr selector.
# Unplug all CV cables first: the 8 CV inputs are measured as their zero.
# Settings and the current instrument are kept (check_calibration.py only).
#
# nebio (knobs, GPIO, LEDs) belongs to the running Nebulae, so it is stopped,
# the calibration runs (calibration LED animation, ~10 s) and Nebulae starts
# again. This runs as its own systemd unit: stopping nebulae.service would
# otherwise also stop this script. Log: journalctl -u nebulae-calibrate

systemd-run --unit=nebulae-calibrate --collect --no-block --quiet /bin/bash -c '
systemctl stop nebulae.service
python3 /home/alarm/QB_Nebulae_V2/Code/nebulae/check_calibration.py only
systemctl start nebulae.service
'
