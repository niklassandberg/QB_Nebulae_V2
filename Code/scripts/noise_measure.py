#!/usr/bin/env python3
# Measures the noise at the audio input (with a cable from output to input:
# what comes out of the Nebulae), for noise_test.sh. Run as root while a
# noise test step plays digital silence:
#   noise_measure.py [seconds] [label]     default 10 s
# Prints and appends to /tmp/noise_measure.txt, per channel (L, R):
#   rms    level of everything 20 Hz - 20 kHz (dBFS)
#   floor  noise floor between the tones (median of the bins, dB per bin)
#   tones  the strongest peaks well above the floor (Hz, dBFS)
#   at     the level at the frequencies the scans make (100 Hz tick,
#          375/750 lock, 400/800/1200/2400 Nebulae's rates)
# Levels: a full-scale sine is 0 dBFS. Welch average, Hann window,
# 32768-sample segments (1.46 Hz bins), so runs are comparable.
import subprocess
import sys
import time

import numpy as np

RATE = 48000
SEG = 32768
WATCH = (100, 375, 400, 750, 800, 1200, 2400)
OUT = "/tmp/noise_measure.txt"


def record(seconds):
    raw = subprocess.run(["arecord", "-q", "-D", "hw:0,0", "-f", "S16_LE", "-r", str(RATE),
                          "-c", "2", "-t", "raw", "-d", str(seconds)],
                         stdout=subprocess.PIPE, check=True).stdout
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    return x.reshape(-1, 2).T  # [L, R]


def spectrum(x):
    w = np.hanning(SEG)
    step = SEG // 2
    acc = None
    n = 0
    for start in range(0, len(x) - SEG + 1, step):
        seg = x[start:start + SEG]
        seg = (seg - seg.mean()) * w
        p = np.abs(np.fft.rfft(seg)) ** 2
        acc = p if acc is None else acc + p
        n += 1
    mag = np.sqrt(acc / n)
    amp = 2.0 * mag / w.sum()  # peak amplitude of a sine in that bin
    freqs = np.fft.rfftfreq(SEG, 1.0 / RATE)
    return freqs, amp


def db(a):
    return 20.0 * np.log10(np.maximum(a, 1e-12))


def analyse(x):
    freqs, amp = spectrum(x)
    band = (freqs >= 20) & (freqs <= 20000)
    level = db(amp)
    floor = float(np.median(level[band]))
    # rms of the band: power of all bins (Hann: equivalent noise bandwidth 1.5)
    rms = float(np.sqrt(np.sum((amp[band] / np.sqrt(2)) ** 2) / 1.5))
    # tones: local maxima at least 12 dB above the floor
    peaks = []
    idx = np.where(band)[0]
    for i in idx[1:-1]:
        if level[i] > floor + 12 and level[i] >= level[i - 1] and level[i] >= level[i + 1]:
            peaks.append((float(level[i]), float(freqs[i])))
    peaks.sort(reverse=True)
    tones = []
    for lv, f in peaks:  # merge peaks closer than 3 bins
        if all(abs(f - g) > 3 * RATE / SEG for _, g in tones):
            tones.append((lv, f))
        if len(tones) == 8:
            break
    at = {}
    for f in WATCH:
        i = int(round(f * SEG / RATE))
        at[f] = float(level[max(0, i - 2):i + 3].max())
    return db(rms), floor, tones, at


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    label = " ".join(sys.argv[2:]) or "(no label)"
    x = record(seconds)
    lines = ["== %s  %s  (%d s)" % (time.strftime("%H:%M:%S"), label, seconds)]
    for name, ch in zip(("L", "R"), x):
        rms, floor, tones, at = analyse(ch)
        lines.append("  %s rms %6.1f dBFS  floor %6.1f dB" % (name, rms, floor))
        lines.append("    tones: " + (", ".join("%.0f Hz %.1f" % (f, lv) for lv, f in tones) or "none"))
        lines.append("    at:    " + ", ".join("%d %.1f" % (f, at[f]) for f in WATCH))
    text = "\n".join(lines)
    print(text)
    with open(OUT, "a") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
