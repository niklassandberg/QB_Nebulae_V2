#!/usr/bin/env python3
# Compares the results of noise_compare.sh (one tar per firmware/state), on
# the PC:   python3 noise_compare_analyze.py noise_compare_*.tar
# Per tar: the noise of the tap (noise_measure.py's spectrum: rms, floor,
# known tones), clicks and pops in the time signal, and CPU, headroom and
# heat from cpu.csv; then everything side by side.
import csv
import io
import os
import sys
import tarfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_measure as nm  # noqa: E402  (spectrum, analyse; RATE 48000)

TONES = (34, 67, 94, 135, 400)   # hum series, Csound blocks (-B512), Nebulae scans


def level_at(c, freq):
    f, a = nm.spectrum(c)
    lv = 20 * np.log10(np.maximum(a, 1e-12))
    k = int(round(freq * nm.SEG / nm.RATE))
    return float(lv[k - 2:k + 3].max())


def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / nm.RATE)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def events(x, lo, hi, win_ms, above_db):
    """Windows standing above_db over the median window level, per minute."""
    y = band(x, lo, hi)
    win = int(nm.RATE * win_ms / 1000)
    n = len(y) // win
    w = np.sqrt((y[:n * win].reshape(n, win) ** 2).mean(1))
    db = 20 * np.log10(w + 1e-12)
    med = np.median(db)
    count = int((db > med + above_db).sum())
    return count * 60.0 * nm.RATE / len(y), float(db.max() - med)


def load(path):
    r = {"name": os.path.basename(path)}
    with tarfile.open(path) as t:
        files = {os.path.basename(m.name): t.extractfile(m).read() for m in t.getmembers() if m.isfile()}
    info = dict(l.split("=", 1) for l in files["info.txt"].decode().splitlines() if "=" in l)
    if info.get("mode") == "load":
        return load_load(path, files, info)
    r["label"] = info.get("label", r["name"])
    r["info"] = info
    x = np.frombuffer(files["noise.raw"], dtype="<f4").astype(np.float64).reshape(-1, 2).T
    r["secs"] = x.shape[1] / nm.RATE
    c = x[0]
    rms, floor, tones, _ = nm.analyse(c)
    r["rms"], r["floor"] = rms, floor
    r["tones"] = {f: level_at(c, f) for f in TONES}
    r["top"] = ", ".join("%.0f Hz %.0f" % (f, lv) for lv, f in tones[:5])
    r["clicks"], r["click_max"] = events(c, 1000, 20000, 1, 20)   # sharp, high
    r["pops"], r["pop_max"] = events(c, 20, 1000, 5, 12)          # low thumps
    rows = list(csv.DictReader(io.StringIO(files["cpu.csv"].decode())))
    col = lambda k: np.array([float(row[k]) for row in rows])
    r["busy"], r["neb"], r["spin"] = col("sys_busy_pct"), col("nebulae_pct_of_one_core"), col("spin_pct_of_one_core")
    r["temp"], r["freq"] = col("temp_c"), col("freq_mhz")
    r["cores"] = int(info.get("cores", 4))
    hz = int(info.get("hz", 100))
    # threads: CPU over the run, % of one core
    def threads(name):
        out = {}
        for l in files[name].decode().splitlines():
            tid, ticks, comm = l.split(" ", 2)
            out[tid] = (int(ticks), comm)
        return out
    a, b = threads("threads_start.txt"), threads("threads_end.txt")
    secs = len(rows)
    th = [(100.0 * (b[t][0] - a[t][0]) / hz / secs, b[t][1]) for t in b if t in a]
    th.sort(reverse=True)
    r["threads"] = ", ".join("%s %.0f%%" % (comm, p) for p, comm in th[:5])
    return r


PHASES = ("normal", "cpu", "sd", "recover")


def gaps(x):
    """Dropouts in a sounding signal: 1 ms windows more than 30 dB under the
    median window, between louder ones (a buffer that came too late is a
    short silence or a cut). Counted as events (touching windows = one).
    None when the signal is too quiet to tell (source on live input)."""
    win = nm.RATE // 1000
    n = len(x) // win
    if n < 100:
        return None
    w = np.sqrt((x[:n * win].reshape(n, win) ** 2).mean(1))
    db = 20 * np.log10(w + 1e-12)
    med = np.median(db)
    if med < -60:
        return None
    low = db < med - 30
    low[:5] = low[-5:] = False
    return int(np.sum(low[1:] & ~low[:-1]))


def phase_jumps(x):
    """With a steady sine at the input: its phase per 50 ms block (least
    squares fit at the dominant frequency); a jump of more than 0.2 rad
    between blocks = input samples lost (or the oscillator itself: compare
    with the normal phase). None without a clear low tone."""
    x = x - x.mean()
    if len(x) < nm.RATE or np.sqrt(np.mean(x ** 2)) < 1e-3:
        return None
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1.0 / nm.RATE)
    k = np.argmax(spec[10:]) + 10
    f0 = f[k]
    if f0 > 1000:
        return None
    blk = nm.RATE // 20
    t = np.arange(blk) / float(nm.RATE)
    phases = []
    for i in range(len(x) // blk):
        tt = t + i * blk / float(nm.RATE)
        a = np.column_stack([np.cos(2 * np.pi * f0 * tt), np.sin(2 * np.pi * f0 * tt), np.ones(blk)])
        c = np.linalg.lstsq(a, x[i * blk:(i + 1) * blk], rcond=None)[0]
        phases.append(np.arctan2(-c[1], c[0]))
    d = np.angle(np.exp(1j * np.diff(np.unwrap(phases))))
    d = d - np.median(d)   # the slow drift of the f0 estimate
    return int(np.sum(np.abs(d) > 0.2))


def load_load(path, files, info):
    r = {"name": os.path.basename(path), "label": info.get("label", path), "info": info}
    rows = list(csv.DictReader(io.StringIO(files["cpu.csv"].decode())))
    r["phases"] = {}
    for ph in PHASES:
        sel = [row for row in rows if row["phase"] == ph]
        if not sel:
            continue
        col = lambda k: np.array([float(row[k]) for row in sel])
        g = clk = jumps = None
        raw = files.get("phase_%s.raw" % ph)
        if raw:
            x = np.frombuffer(raw, dtype="<f4").astype(np.float64).reshape(-1, 2).T
            g = gaps(x[0])
            jumps = phase_jumps(x[0])
            # A steady tone at the input: samples lost when Csound falls
            # behind are a jump = a click above 1 kHz (count, not per minute)
            per_min, _ = events(x[0], 1000, 20000, 1, 20)
            clk = int(round(per_min * x.shape[1] / nm.RATE / 60.0))
        r["phases"][ph] = {"busy": col("sys_busy_pct").mean(), "neb": col("nebulae_pct_of_one_core").mean(),
                           "temp": col("temp_c").max(), "freq": col("freq_mhz").min(),
                           "msgs": int(info.get("msgs_%s" % ph, "0") or 0), "gaps": g, "clicks": clk,
                           "jumps": jumps}
    return r


def print_load(rs):
    print("ROBUSTNESS UNDER LOAD (per phase: Csound dropout messages, gaps found in the sound,")
    print("system %, Nebulae % of one core, max temp, lowest clock)")
    for r in rs:
        print("%s  (%s | %s | Csound threads with real-time policy: %s | RSS %s kB)" % (
            r["label"], r["info"].get("kernel", "?"), r["info"].get("firmware", "?"),
            r["info"].get("csound_rt", "").strip() or "none", r["info"].get("rss_kb", "?")))
        print("   %-8s %6s %6s %6s %6s %9s %9s %7s %7s" % ("phase", "msgs", "jumps", "gaps", "clicks", "system %",
                                                       "Nebulae", "max C", "MHz"))
        dash = lambda v: "-" if v is None else v
        for ph in PHASES:
            p = r["phases"].get(ph)
            if p:
                print("   %-8s %6d %6s %6s %6s %8.1f%% %8.1f%% %7.0f %7.0f" % (
                    ph, p["msgs"], dash(p["jumps"]), dash(p["gaps"]), dash(p["clicks"]),
                    p["busy"], p["neb"], p["temp"], p["freq"]))
    print("msgs = Csound's underrun/overrun lines. jumps = phase jumps of a steady sine at the input")
    print("(lost input samples; the reliable check): compare a phase with 'normal', not with zero.")
    print("gaps/clicks: the simple detectors, unreliable with a granular or unsteady signal.")


NOISE_KEYS = ("rms", "floor", "secs", "tones", "top", "clicks", "click_max", "pops", "pop_max")


def merge_0db(rs):
    """A pair LABEL + LABEL_0db is one row: the noise at Master 0 dB (as ours
    runs) from LABEL_0db, CPU and heat from LABEL (the volume doesn't change
    those, and LABEL measured them longer)."""
    by = {r["label"]: r for r in rs}
    out, notes = [], []
    for r in rs:
        if r["label"].endswith("_0db") and r["label"][:-4] in by:
            continue
        z = by.get(r["label"] + "_0db")
        if z:
            m = dict(r)
            m.update({k: z[k] for k in NOISE_KEYS})
            notes.append("%s: noise from %s (Master 0 dB), CPU and heat from %s" % (
                r["label"], z["label"], r["label"]))
            out.append(m)
        else:
            out.append(r)
    return out, notes


def main(paths):
    all_rs = [load(p) for p in paths]
    loads = [r for r in all_rs if "phases" in r]
    if loads:
        print_load(loads)
        print()
    rs, notes = merge_0db([r for r in all_rs if "phases" not in r])
    if not rs:
        return
    for n in notes:
        print(n)
    if notes:
        print()
    w = max(12, max(len(r["label"]) for r in rs))
    print("NOISE (left channel, dBFS; tap = what Csound hears, cable output->input)")
    print("%-*s %6s %6s %7s " % (w, "", "rms", "floor", "secs") + " ".join("%7s" % ("%d Hz" % f) for f in TONES)
          + "  clicks/min (max dB)  pops/min (max dB)")
    for r in rs:
        print("%-*s %6.1f %6.1f %7.0f " % (w, r["label"], r["rms"], r["floor"], r["secs"])
              + " ".join("%7.1f" % r["tones"][f] for f in TONES)
              + "  %6.1f (%4.1f)        %6.1f (%4.1f)" % (r["clicks"], r["click_max"], r["pops"], r["pop_max"]))
    print()
    print("CPU AND HEAT (mean over the run; Nebulae = its process incl. Csound, % of ONE core)")
    print("%-*s %9s %9s %9s %8s %8s %8s %8s" % (w, "", "system %", "headroom", "Nebulae", "spin", "temp", "max C",
                                              "MHz"))
    for r in rs:
        print("%-*s %9.1f %8.1f%% %8.1f%% %7.0f%% %6.1f C %6.0f C %8.0f" % (
            w, r["label"], r["busy"].mean(), 100 - r["busy"].mean(), r["neb"].mean(), r["spin"].mean(),
            r["temp"][-60:].mean(), r["temp"].max(), r["freq"].mean()))
    print()
    print("headroom = share of all cores not busy (spin counts as busy: it gives way to any real work,")
    print("so with spin the real headroom is headroom + spin/cores).")
    print()
    for r in rs:
        print("%s: %s | %s | %s" % (r["label"], r["info"].get("model", "?"), r["info"].get("kernel", "?"),
                                    r["info"].get("firmware", "?")))
        print("   threads: %s" % r["threads"])
        print("   strongest tones: %s" % r["top"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("python3 noise_compare_analyze.py noise_compare_*.tar")
    main(sys.argv[1:])
