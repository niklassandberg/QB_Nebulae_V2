#!/usr/bin/env python3
# How long the last start took, from power-on (run as root):
#   firmware/bootloader  BCM2711 system timer (1 MHz, counts from power-on /
#                        reset) minus Linux's uptime: the time before the kernel
#   sound                nebio's first "inputs running" after Csound started
#                        (journal, seconds after the kernel started)
import mmap
import os
import re
import struct
import subprocess

STC_BASE = 0xFE003000  # BCM2711 system timer (Pi 4)


def system_timer():
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=STC_BASE)
    lo = struct.unpack_from("<I", m, 4)[0]
    hi = struct.unpack_from("<I", m, 8)[0]
    return (hi << 32 | lo) / 1e6


def sound_after_kernel():
    inv = subprocess.run(["systemctl", "show", "-p", "InvocationID", "--value", "nebulae.service"],
                         capture_output=True, text=True).stdout.strip()
    log = subprocess.run(["journalctl", "_SYSTEMD_INVOCATION_ID=" + inv, "-o", "short-monotonic",
                          "--no-pager"], capture_output=True, text=True).stdout
    after_csound = log[log.find("Csound version"):] if "Csound version" in log else ""
    m = re.search(r"\[\s*([0-9.]+)\][^\n]*inputs running", after_csound)
    return float(m.group(1)) if m else None


uptime = float(open("/proc/uptime").read().split()[0])
firmware = system_timer() - uptime
sound = sound_after_kernel()
print("firmware/bootloader (before the kernel): %5.2f s" % firmware)
if sound is not None:
    print("kernel start -> sound:                  %5.2f s" % sound)
    print("power-on -> sound:                      %5.2f s" % (firmware + sound))
else:
    print("sound start not found in this nebulae.service run")
