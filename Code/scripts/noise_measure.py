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
#   pulses short events (peaks, pulses a second, how they repeat), see pulses()
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


# Pulses: short events the rms and the Welch spectrum average away (Wi-Fi
# beacons every 102.4 ms, CPU wake-ups, USB, timers). High-passed first: the
# hum below HP_HZ would hide them.
HP_HZ = 500
WIN = RATE // 1000      # 1 ms windows
OVER_DB = 10            # a window this far above the median window is a pulse


def highpass(x):
    spec = np.fft.rfft(x - x.mean())
    spec[np.fft.rfftfreq(len(x), 1.0 / RATE) < HP_HZ] = 0
    return np.fft.irfft(spec, len(x))


def fold(power, period):
    """Mean power per phase bin (0.25 ms) of a signal folded at period samples."""
    nbins = max(8, int(period / (RATE / 4000.0)))
    phase = ((np.arange(len(power)) / period) % 1.0 * nbins).astype(np.int64)
    return np.bincount(phase, power, nbins) / np.maximum(np.bincount(phase, None, nbins), 1)


def pulses(x):
    """peak/p999 (dBFS, full band), hp_peak/hp_p999 (above HP_HZ),
    per_s (pulses a second), height (dB, 99.9 % window over the median one),
    period_ms + period_corr (strongest repeat 20 ms - 1 s of the envelope),
    sync_db (dBFS rms of the pulse, folded at that period: repeats add up,
    the noise does not) and sync_height (dB over the rest of the period)."""
    h = highpass(x)
    n = len(h) // WIN
    env = np.sqrt((h[:n * WIN].reshape(n, WIN) ** 2).mean(axis=1))
    edb = db(env)
    base = np.median(edb)
    over = edb > base + OVER_DB
    starts = int(over[0]) + int(np.count_nonzero(over[1:] & ~over[:-1]))
    e = env - env.mean()
    ac = np.fft.irfft(np.abs(np.fft.rfft(e, 2 * n)) ** 2)[:n]
    ac = ac / ac[0] if ac[0] > 0 else ac
    lo, hi = 20, min(1000, n // 3)
    lag = 0
    if hi > lo:
        # The shortest repeat, not a multiple of it: in whole ms a 102.4 ms
        # beacon lines up best at 512 ms.
        top = ac[lo:hi].max()
        for i in range(lo, hi):
            if ac[i] >= 0.7 * top and ac[i] >= ac[i - 1] and ac[i] >= ac[i + 1]:
                lag = i
                break
    sync_db, sync_height, period = float("nan"), float("nan"), float(lag)
    if lag:
        power = h * h
        best = None
        for p in np.arange((lag - 0.6) * WIN, (lag + 0.6) * WIN, 1.0):
            f = fold(power, p)
            score = f.max() / max(np.median(f), 1e-30)
            if best is None or score > best[0]:
                best = (score, p, f)
        score, p, f = best
        period = p * 1000.0 / RATE
        sync_db = float(10 * np.log10(max(f.max(), 1e-30)))
        sync_height = float(10 * np.log10(score))
    return {"peak": float(db(np.abs(x).max())), "p999": float(db(np.percentile(np.abs(x), 99.9))),
            "hp_peak": float(db(np.abs(h).max())), "hp_p999": float(db(np.percentile(np.abs(h), 99.9))),
            "per_s": starts * 1000.0 / n, "height": float(np.percentile(edb, 99.9) - base),
            "period_ms": period, "period_corr": float(ac[lag]) if lag else 0.0,
            "sync_db": sync_db, "sync_height": sync_height}


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
        p = pulses(ch)
        lines.append("    pulses: peak %.1f  >%d Hz: peak %.1f p99.9 %.1f  %.1f/s  +%.1f dB  "
                     "repeat %.1f ms (corr %.2f) sync %.1f dBFS +%.1f dB" % (
                         p["peak"], HP_HZ, p["hp_peak"], p["hp_p999"], p["per_s"], p["height"],
                         p["period_ms"], p["period_corr"], p["sync_db"], p["sync_height"]))
    text = "\n".join(lines)
    print(text)
    with open(OUT, "a") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
