#!/usr/bin/env python3
# make_report.py
# Builds nebio_cpu_report.pdf from the cpustat.sh measurements in this folder:
# the nebio firmware and the original firmware (0419df1), both in the SC bank.
# Needs reportlab (WSL Arch: python-reportlab).
#
#   wsl -d archlinux -- python3 /mnt/c/Users/niksan/Documents/QB_Nebulae_V2/measurements/cpustat/make_report.py

import csv
import os

from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_NEBIO = os.path.join(HERE, "nebio_sc_20261016_084140.csv")
CSV_ORIG = os.path.join(HERE, "orig_sc_20261016_102031.csv")
OUT = os.path.join(HERE, "nebio_cpu_report.pdf")

PURPLE = colors.HexColor("#3d2b6e")
ORANGE = colors.HexColor("#d9822b")
LIGHT = colors.HexColor("#ece8f5")
GREY = colors.HexColor("#666666")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Title"], textColor=PURPLE, fontSize=22, leading=26, spaceAfter=2)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], textColor=GREY, fontSize=9.5)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], textColor=PURPLE, fontSize=14, spaceBefore=12, spaceAfter=6)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontName="Helvetica-BoldOblique", fontSize=11,
                    spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("BODY", parent=ss["Normal"], fontSize=9.5, leading=13, spaceAfter=5)
CELL = ParagraphStyle("CELL", parent=BODY, fontSize=8.5, leading=11, spaceAfter=0)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
BUL = ParagraphStyle("BUL", parent=BODY, leftIndent=12, bulletIndent=2, spaceAfter=2)
CODE = ParagraphStyle("CODE", parent=ss["Code"], fontSize=8, leading=10, leftIndent=8, spaceAfter=6)


def p(text, style=BODY):
    return Paragraph(text, style)


def bullets(items):
    return [Paragraph(t, BUL, bulletText="•") for t in items]


def table(rows, widths):
    data = [[Paragraph(str(c), CELLB if r == 0 else CELL) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in range(1, len(rows)):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    t.setStyle(TableStyle(style))
    return t


def load_csv(path):
    with open(path) as f:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]


def chart(series, ymax, legend_cols=2):
    """series: list of (rows, column, label, color, dashed)."""
    d = Drawing(170 * mm, 72 * mm)
    lp = LinePlot()
    lp.x, lp.y = 14 * mm, 12 * mm
    lp.width, lp.height = 150 * mm, 48 * mm
    lp.data = [[(r["time_s"], r[col]) for r in rows] for rows, col, _, _, _ in series]
    for i, (_, _, _, col, dashed) in enumerate(series):
        lp.lines[i].strokeColor = col
        lp.lines[i].strokeWidth = 1.2
        if dashed:
            lp.lines[i].strokeDashArray = [3, 2]
    lp.xValueAxis.valueMin = 0
    lp.xValueAxis.valueMax = 300
    lp.xValueAxis.valueStep = 30
    lp.yValueAxis.valueMin = 0
    lp.yValueAxis.valueMax = ymax
    lp.yValueAxis.valueStep = 20
    for axis in (lp.xValueAxis, lp.yValueAxis):
        axis.labels.fontSize = 7
        axis.labels.fontName = "Helvetica"
    lp.yValueAxis.visibleGrid = True
    lp.yValueAxis.gridStrokeColor = colors.HexColor("#dddddd")
    d.add(lp)
    d.add(String(14 * mm + 75 * mm, 3 * mm, "seconds", fontName="Helvetica", fontSize=7,
                 textAnchor="middle"))
    d.add(String(3 * mm, 36 * mm, "% CPU", fontName="Helvetica", fontSize=7, textAnchor="middle"))
    lg = Legend()
    lg.x, lg.y = 16 * mm, 71 * mm
    lg.dx, lg.dy = 6, 6
    lg.fontSize = 7
    lg.fontName = "Helvetica"
    lg.columnMaximum = legend_cols
    lg.deltax = 75 * mm
    lg.alignment = "right"
    lg.colorNamePairs = [(col, label) for _, _, label, col, _ in series]
    d.add(lg)
    return d


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 10 * mm, "QB Nebulae V2 - nebio CPU measurement")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, "Page %d" % doc.page)
    canvas.restoreState()


def build():
    neb = load_csv(CSV_NEBIO)
    org = load_csv(CSV_ORIG)
    W = A4[0] - 36 * mm
    s = []
    s.append(p("nebio: CPU Measurement and Hardware Test", H1))
    s.append(p("QB Nebulae V2 (RPi4) &middot; nebio firmware (<b>feature_newHardWareHandling</b>) "
               "compared with the original firmware (<b>0419df1</b>) &middot; measured 2026-10-16 on "
               "the device", SUB))
    s.append(Spacer(1, 6))

    # 1 ------------------------------------------------------------------
    s.append(p("1. Summary", H2))
    s.append(p("nebio (libnebio.so) builds and runs on the Nebulae, and the hardware test passed: all "
               "inputs register, every LED works, and audio plays without underruns. The CPU "
               "measurement, however, shows that <b>the nebio firmware currently uses more CPU than "
               "the original firmware</b>. Both were measured with the SuperCollider bank, the same "
               "jackd settings, and nobody touching the module for 5 minutes:"))
    s.append(table([
        ["", "Original (0419df1)", "nebio", "Difference"],
        ["<b>Whole Pi busy</b> (4 cores = 100 %)", "26.5 %", "46.0 %", "<b>+19.5 points (about +0.8 core)</b>"],
        ["python3 process (% of one core)", "81.6 %", "101.7 %", "+20.1"],
        ["&nbsp;&nbsp;Python main loop", "74.2 %", "79.0 %", "+4.8 (about the same)"],
        ["&nbsp;&nbsp;nebio input thread", "-", "20.2 %", "+20.2 (new)"],
        ["Kernel time without a process (% of Pi)", "2.7 %", "16.8 %", "+14.1"],
        ["I2C interrupts/s (LED writes)", "4 680", "986", "<b>-79 %</b>"],
        ["SPI interrupts/s (ADC reads)", "5 266", "7 996", "+52 %"],
        ["python3 memory (max RSS)", "307 MB", "80 MB", "<b>-227 MB</b>"],
    ], [58 * mm, 30 * mm, 24 * mm, W - 112 * mm]))
    s.append(Spacer(1, 4))
    s += bullets([
        "<b>The Python main loop costs about the same in both firmwares</b> (74 % vs 79 % of a "
        "core). Moving the hardware access into C++ did not make the Python side cheaper, because "
        "updateAll() and the control logic dominate, not the I/O calls.",
        "<b>nebio adds two costs on top:</b> its 1 kHz input thread (20 % of a core) and about "
        "14 points of extra kernel time that is not charged to any process.",
        "<b>nebio is better at LEDs and memory:</b> almost 5 times fewer I2C interrupts, and the "
        "Python process uses 227 MB less memory.",
        "SuperCollider and JACK are the same in both (sclang 6-7 %, scsynth 3.5 %, jackd 4 %).",
    ])
    s.append(p("Section 7 lists what to change so that nebio ends up cheaper than the original. "
               "The biggest single item is the extra kernel time, whose cause is not proven yet."))

    s.append(p("Status", H3))
    s.append(table([
        ["Item", "Result"],
        ["libgpiod installed on the Pi", "Done: libgpiod 2.3.1 (cmake, gcc, make, pkgconf, liblo 0.34 were already there)"],
        ["nebio build on the Pi", "Done: libnebio.so, 0 warnings (armv7h, gcc 15.2)"],
        ["Hardware test firmware (hwtest.py)", "Runs at boot, log on the USB stick"],
        ["Inputs: knobs, CV, buttons, gates, encoders", "All register (user test)"],
        ["LEDs: 5 button LEDs, 4 RGB LEDs x 3 colours", "All work (ledwalk.py, checked by eye)"],
        ["Audio during the test", "Plays, 0 underruns"],
        ["Normal nebulae with nebio", "Starts, SC bank plays"],
        ["CPU: SC bank, both firmwares", "Done (this report)"],
        ["CPU: Csound and PD banks", "Not measured yet"],
    ], [70 * mm, W - 70 * mm]))

    # 2 ------------------------------------------------------------------
    s.append(p("2. Setup", H2))
    s.append(table([
        ["Item", "Value"],
        ["Device", "Raspberry Pi 4, 4 cores, Arch Linux ARM <b>armv7h</b> (32 bit), kernel 5.15.43-2-rpi-ARCH"],
        ["CPU clock", "governor performance, 1200 MHz (both runs)"],
        ["nebio firmware", "feature_newHardWareHandling, libnebio.so built 2026-10-16 07:32, "
         "nebulae.py md5 e67c4c6f8289. Measured 08:41-08:46 (Pi clock)"],
        ["Original firmware", "commit 0419df1 (the commit before nebio, python3, RPi.GPIO, Adafruit "
         "drivers, python-osc), nebulae.py md5 64995ce48aba, checked against git. Measured 10:20-10:25"],
        ["Running", "nebulae.py (python3), sclang, scsynth, jackd (-p128 -n3 -r48000, hw:sndrpiproto)"],
        ["Instrument", "SC bank, the instrument loaded at boot"],
        ["Conditions", "No user input, temperature 44-47 °C in both runs, never throttled"],
        ["Window", "300 s each, one sample per second"],
        ["Tool", "Code/scripts/cpustat.sh (sh + awk + /proc only)"],
    ], [30 * mm, W - 30 * mm]))
    s.append(p("CPU values are given as <b>% of one core</b>, the same as top (100 % = one full core). "
               "\"Share of Pi\" is the same value divided by 4. The whole-Pi line uses /proc/stat, "
               "where all 4 cores = 100 %.", BODY))

    # 3 ------------------------------------------------------------------
    s.append(p("3. Results side by side: SC bank", H2))
    s.append(table([
        ["Program", "Firmware", "min %", "mean %", "p95 %", "max %", "share of Pi", "max RSS"],
        ["<b>python3</b>", "original", "77.1", "81.6", "84.0", "85.0", "20.4 %", "307 MB"],
        ["", "nebio", "96.7", "<b>101.7</b>", "106.0", "106.9", "25.4 %", "80 MB"],
        ["sclang", "original", "4.5", "5.7", "6.3", "7.2", "1.4 %", "29 MB"],
        ["", "nebio", "5.4", "6.9", "7.3", "8.9", "1.7 %", "29 MB"],
        ["scsynth", "original", "2.7", "3.6", "4.5", "4.5", "0.9 %", "120 MB"],
        ["", "nebio", "1.8", "3.5", "4.5", "4.6", "0.9 %", "118 MB"],
        ["jackd", "original", "3.6", "4.2", "5.4", "5.4", "1.1 %", "127 MB"],
        ["", "nebio", "2.7", "4.5", "5.5", "5.5", "1.1 %", "127 MB"],
        ["<b>whole Pi</b>", "original", "23.2", "26.5", "30.1", "31.3", "", ""],
        ["(4 cores = 100 %)", "nebio", "43.3", "<b>46.0</b>", "48.4", "50.9", "", ""],
        ["temperature °C", "original", "43.8", "45.2", "46.3", "46.7", "", ""],
        ["", "nebio", "43.8", "45.3", "46.3", "46.7", "", ""],
    ], [30 * mm, 18 * mm, 15 * mm, 16 * mm, 15 * mm, 15 * mm, 22 * mm, W - 131 * mm]))
    s.append(p("pd and csound were not running in either measurement (Csound runs inside python3 "
               "in the Csound bank).", SUB))
    s.append(Spacer(1, 4))
    s.append(KeepTogether([p("CPU over the 5 minutes", H3), chart([
        (neb, "python_pct_of_core", "python3, nebio (% of one core)", PURPLE, False),
        (org, "python_pct_of_core", "python3, original (% of one core)", PURPLE, True),
        (neb, "pi_total_pct", "whole Pi, nebio (% of 4 cores)", ORANGE, False),
        (org, "pi_total_pct", "whole Pi, original (% of 4 cores)", ORANGE, True),
    ], 120), p("Solid lines: nebio. Dashed lines: original. Both are flat: no spikes, nothing grows "
               "over time.", BODY)]))

    s.append(p("Inside the python3 process", H3))
    s.append(table([
        ["Thread", "Original", "nebio", "What it is"],
        ["main thread", "74.2 % (max 78.0)", "<b>79.0 %</b> (max 84.2)", "Python main loop: updateAll(), ControlHandler, ui.py"],
        ["nebio input thread", "-", "<b>20.2 %</b> (max 21.9)", "1 kHz scan of shift register, encoders, ADCs"],
        ["other nebio threads", "-", "2.4 %", "LED writer, gate events, reset LED PWM"],
        ["Python threads (Thread-2, Thread-3)", "6.3 %", "-", "Python worker threads of the original firmware"],
        ["other", "1.1 %", "-", ""],
    ], [44 * mm, 30 * mm, 32 * mm, W - 106 * mm]))
    s.append(p("The nebio threads are not named yet, so they show as python3; the input thread is "
               "identified by its steady 20 %, which matches the hardware test.", SUB))

    # 4 ------------------------------------------------------------------
    s.append(p("4. Kernel work and interrupts", H2))
    s.append(p("This kernel uses tick-based CPU accounting without IRQ time accounting "
               "(CONFIG_HZ=100). Interrupt work that happens while a core is idle is counted as "
               "system time without any process, so it is invisible in top. The difference between "
               "the whole-Pi load and the measured programs shows it:"))
    s.append(table([
        ["", "Original", "nebio"],
        ["user / system / idle (% of Pi)", "18.8 / 7.5 / 73.4", "26.5 / 19.3 / 54.0"],
        ["Measured programs (% of Pi)", "23.8 %", "29.2 %"],
        ["<b>Kernel time without a process</b>", "<b>2.7 %</b>", "<b>16.8 %</b>"],
    ], [60 * mm, 50 * mm, W - 110 * mm]))
    s.append(Spacer(1, 6))
    s.append(table([
        ["Interrupt source (per second)", "Original", "nebio", "Cause"],
        ["IPI3 function call", "14 973", "9 582", "Cores signalling each other"],
        ["fe204000.spi", "5 266", "<b>7 996</b>", "ADC reads. nebio: 2 chips x 8 channels x 500 Hz, one "
         "interrupt per channel transfer"],
        ["fe804000.i2c", "<b>4 680</b>", "986", "LED writes to the PCA9685"],
        ["arch_timer", "2 718", "1 289", "Kernel timer"],
        ["DMA IRQ x 2", "374 + 374", "375 + 375", "Audio stream (48000 / 128). Same"],
        ["IPI2 rescheduling", "22", "29", ""],
    ], [40 * mm, 20 * mm, 18 * mm, W - 78 * mm]))
    s.append(Spacer(1, 4))
    s.append(p("The interrupt counts alone do not explain the extra kernel time: nebio has <b>fewer</b> "
               "interrupts in total (about 21 000/s against 28 000/s), yet about 14 points more "
               "unaccounted system time. Short-lived processes were ruled out (2 new processes in "
               "10 s). The most likely candidates are the per-transfer cost of the SPI path (each ADC "
               "channel is its own transfer, 8000 per second) and the 1 kHz wake-ups of the input "
               "thread, but this is <b>not proven yet</b>. The next step is to measure it directly: "
               "run nebio with the ADC rate lowered, then with the scan rate lowered, and see which "
               "one removes the extra system time."))

    # 5 ------------------------------------------------------------------
    s.append(p("5. Hardware test results (nebio)", H2))
    s.append(p("hwtest.py ran at boot instead of nebulae (firmware built with "
               "<font face='Courier'>create_fw_update.sh --hwtest</font>), with audio playing and the log "
               "written to the USB stick."))
    s += bullets([
        "<b>Inputs:</b> all knobs, both encoders, buttons and gates registered (118 digital events). "
        "CV 4 (pitch) and CV 1 (speed) were seen moving; the other CV inputs were not patched in "
        "that run.",
        "<b>nebio:</b> scan 1000 Hz, worst scan 1.0-2.4 ms, test process about 22 % of one core, "
        "41-42 °C, not throttled.",
        "<b>Audio:</b> 12 files looped on plughw:sndrpiproto, <b>0 underruns</b>.",
        "<b>LEDs:</b> the PCA9685 registers were read while the test ran and matched the expected "
        "values. ledwalk.py then lit every LED and colour on its own; all worked. In hwtest.py the "
        "pitch/speed LEDs do not behave like nebulae (encoders only dim the _neg LEDs, knobs set "
        "the _pos colours), which looked like \"not reacting\".",
    ])

    # 6 ------------------------------------------------------------------
    s.append(p("6. Other findings", H2))
    s += bullets([
        "<b>sudo</b> on the Pi asks for the root password, not alarm's.",
        "<b>pacman 7</b> needs <font face='Courier'>--disable-sandbox</font> on kernel 5.15 (no "
        "Landlock). The package database was stale (mirror 404); after <font face='Courier'>-Sy</font> "
        "glibc matched the repo, so libgpiod was installed on its own without a partial upgrade.",
        "<b>The Pi is 32 bit (armv7h)</b>, not aarch64 as the nebio step 1 report and the SC "
        "PKGBUILD assume.",
        "<b>The nebio build folder is owned by root</b> (built at boot by startup.sh), so manual "
        "builds must run as root.",
        "<b>Older python2 firmwares do not run on this image</b>: Python 2 has no OSC module (pyOSC) "
        "and a broken hashlib. A firmware from the niklassandberg branch crashed in a restart loop "
        "with <font face='Courier'>ImportError: No module named OSC</font>. OSC.py was copied into "
        "the Python 2 site-packages from /home/alarm/usr/lib/python2.7/site-packages; it is not "
        "needed by the python3 firmwares.",
        "<b>USB stick dropped out during one boot</b> (sda \"device offline or changed\", I/O errors). "
        "Copying an .instr and a .pd file from the stick failed. Not related to nebio.",
        "<b>Code/log is missing early in boot</b>, so the first neb_log.txt lines are lost. Harmless.",
    ])

    # 7 ------------------------------------------------------------------
    s.append(p("7. What to change (not done)", H2))
    s.append(p("Goal: the nebio firmware should use less CPU than the original, not more."))
    s.append(table([
        ["Change", "Expected effect"],
        ["Find the source of the extra kernel time (ADC rate and scan rate experiments, section 4)",
         "Up to 14 points of the Pi, the largest part of the difference"],
        ["ADC reads at 250 Hz instead of 500 Hz", "Halves the SPI transfers (8000/s), below the "
         "original's 5266/s"],
        ["Read the input thread at a lower rate, or wait for edges instead of polling",
         "Reduces the 20 % input thread"],
        ["Pace the Python main loop lower (for example 200 Hz instead of about 500 Hz)",
         "The 79 % main thread scales with the loop rate. Knob smoothing filters work per loop and "
         "would need retuning."],
        ["Name the nebio threads (pthread_setname_np)", "top and cpustat.sh show nebio-input, "
         "nebio-leds, ... instead of python3"],
    ], [80 * mm, W - 80 * mm]))

    # 8 ------------------------------------------------------------------
    s.append(p("8. Repeating the measurement", H2))
    s.append(p("Same instrument, nobody touching the module, script copied to /tmp:"))
    s.append(Preformatted("sudo sh /tmp/cpustat.sh -d 300 -l \"<bank>, <firmware>\"\n"
                          "# -> /tmp/cpustat_<date>.txt (report) and .csv (one row per second)\n"
                          "# /tmp is cleared at reboot: copy both files off before rebooting", CODE))
    s.append(p("Still to do: the Csound and Pure Data banks on both firmwares (in the Csound bank the "
               "python line includes Csound), and a new nebio run after each change in section 7."))
    s.append(KeepTogether([p("Files", H3), table([
        ["File", "Content"],
        ["measurements/cpustat/nebio_sc_20261016_084140.txt / .csv", "nebio firmware, SC bank"],
        ["measurements/cpustat/orig_sc_20261016_102031.txt / .csv", "original firmware 0419df1, SC bank"],
        ["measurements/cpustat/make_report.py", "Builds this PDF"],
        ["Code/scripts/cpustat.sh", "Measurement script"],
        ["Code/nebio/tools/hwtest.py, ledwalk.py", "Hardware test and LED walk"],
    ], [95 * mm, W - 95 * mm])]))

    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title="nebio CPU Measurement", author="QB Nebulae V2")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
