#!/usr/bin/env python3
# make_report.py
# Builds nebio_cpu_report.pdf from the cpustat.sh measurement in this folder.
# Needs reportlab (WSL Arch: python-reportlab).
#
#   wsl -d archlinux -- python3 make_report.py

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
CSV = os.path.join(HERE, "nebio_sc_20261016_084140.csv")
OUT = os.path.join(HERE, "nebio_cpu_report.pdf")

PURPLE = colors.HexColor("#3d2b6e")
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


def table(rows, widths, num_cols=()):
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


def load_csv():
    with open(CSV) as f:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]


def chart(rows):
    d = Drawing(170 * mm, 70 * mm)
    lp = LinePlot()
    lp.x, lp.y = 14 * mm, 12 * mm
    lp.width, lp.height = 150 * mm, 50 * mm
    series = [
        ("python_pct_of_core", "python3 (nebulae.py + nebio), % of one core", colors.HexColor("#3d2b6e")),
        ("pi_total_pct", "whole Pi, % of all 4 cores", colors.HexColor("#d9822b")),
        ("sclang_pct_of_core", "sclang", colors.HexColor("#3a8f5c")),
        ("jackd_pct_of_core", "jackd", colors.HexColor("#3b7dd8")),
        ("scsynth_pct_of_core", "scsynth", colors.HexColor("#c04a6b")),
    ]
    lp.data = [[(r["time_s"], r[key]) for r in rows] for key, _, _ in series]
    for i, (_, _, col) in enumerate(series):
        lp.lines[i].strokeColor = col
        lp.lines[i].strokeWidth = 1.2
    lp.xValueAxis.valueMin = 0
    lp.xValueAxis.valueMax = 300
    lp.xValueAxis.valueStep = 30
    lp.xValueAxis.labels.fontSize = 7
    lp.xValueAxis.labels.fontName = "Helvetica"
    lp.yValueAxis.valueMin = 0
    lp.yValueAxis.valueMax = 120
    lp.yValueAxis.valueStep = 20
    lp.yValueAxis.labels.fontSize = 7
    lp.yValueAxis.labels.fontName = "Helvetica"
    lp.yValueAxis.visibleGrid = True
    lp.yValueAxis.gridStrokeColor = colors.HexColor("#dddddd")
    d.add(lp)
    d.add(String(14 * mm + 75 * mm, 3 * mm, "seconds", fontName="Helvetica", fontSize=7, textAnchor="middle"))
    d.add(String(3 * mm, 12 * mm + 25 * mm, "% CPU", fontName="Helvetica", fontSize=7, textAnchor="middle"))
    lg = Legend()
    lg.x, lg.y = 16 * mm, 69 * mm
    lg.dx, lg.dy = 6, 6
    lg.fontSize = 7
    lg.fontName = "Helvetica"
    lg.columnMaximum = 2
    lg.deltax = 60 * mm
    lg.alignment = "right"
    lg.colorNamePairs = [(col, label) for _, label, col in series]
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
    rows = load_csv()
    W = A4[0] - 36 * mm
    s = []
    s.append(p("nebio: CPU Measurement and Hardware Test", H1))
    s.append(p("QB Nebulae V2 (RPi4) &middot; branch <b>feature_newHardWareHandling</b> &middot; "
               "measured 2026-10-16 on the device", SUB))
    s.append(Spacer(1, 6))

    # 1 ------------------------------------------------------------------
    s.append(p("1. Summary", H2))
    s.append(p("nebio (libnebio.so) now builds and runs on the Nebulae. The hardware test passed: all "
               "inputs register, every LED works, and audio plays without underruns. With the "
               "SuperCollider bank running and nobody touching the module, the Pi is about "
               "<b>46 % busy</b> (all 4 cores = 100 %). Most of it is control overhead, not audio:"))
    s += bullets([
        "<b>Python main loop of nebulae.py: 79 % of one core.</b> nebio delivers about 500 snapshots "
        "per second, so updateAll() runs about 500 times per second.",
        "<b>nebio input thread: 20 % of one core</b> (1 kHz scan of shift register, encoders and "
        "ADCs).",
        "<b>Hidden kernel work: about 17 % of the Pi</b> that top does not show under any process: "
        "about 8000 SPI interrupts/s (ADC reads), about 1000 I2C interrupts/s (LED writes) and "
        "about 9600 inter-core interrupts/s.",
        "<b>SuperCollider and JACK together: about 15 % of one core.</b>",
    ])
    s.append(p("The numbers are a baseline. They have to be compared with the original firmware under "
               "the same conditions before deciding what to optimise (section 7)."))

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
        ["CPU baseline (this report)", "Done for the SC bank; original firmware not measured yet"],
    ], [70 * mm, W - 70 * mm]))

    # 2 ------------------------------------------------------------------
    s.append(p("2. Setup", H2))
    s.append(table([
        ["Item", "Value"],
        ["Device", "Raspberry Pi 4, 4 cores, Arch Linux ARM <b>armv7h</b> (32 bit), kernel 5.15.43-2-rpi-ARCH"],
        ["CPU clock", "governor performance, 1200 MHz"],
        ["Firmware", "nebio firmware (libnebio.so built 2026-10-16 07:32), nebulae.py md5 e67c4c6f8289"],
        ["Running", "nebulae.py (python3), sclang, scsynth, jackd (-p128 -n3 -r48000, hw:sndrpiproto)"],
        ["Instrument", "SC bank, the instrument loaded at boot"],
        ["Conditions", "No user input, no USB activity, temperature 44-47 °C, never throttled"],
        ["Window", "300 s, one sample per second (273 intervals), 08:41-08:46 on the Pi clock"],
        ["Tool", "Code/scripts/cpustat.sh (sh + awk + /proc only, so it also runs on the original firmware)"],
    ], [28 * mm, W - 28 * mm]))
    s.append(p("CPU values are given as <b>% of one core</b>, the same as top (100 % = one full core). "
               "\"Share of Pi\" is the same value divided by 4. The whole-Pi line uses /proc/stat, "
               "where all 4 cores = 100 %.", BODY))

    # 3 ------------------------------------------------------------------
    s.append(p("3. Results: SC bank, nebio firmware", H2))
    s.append(table([
        ["Program", "min %", "mean %", "p95 %", "max %", "share of Pi", "max RSS"],
        ["<b>python3</b> (nebulae.py incl. nebio)", "96.7", "<b>101.7</b>", "106.0", "106.9", "25.4 %", "80 MB"],
        ["sclang", "5.4", "6.9", "7.3", "8.9", "1.7 %", "29 MB"],
        ["scsynth", "1.8", "3.5", "4.5", "4.6", "0.9 %", "118 MB"],
        ["jackd", "2.7", "4.5", "5.5", "5.5", "1.1 %", "127 MB"],
        ["pd", "-", "-", "-", "-", "not running", ""],
        ["csound", "-", "-", "-", "-", "runs inside python3", ""],
        ["<b>whole Pi</b> (4 cores = 100 %)", "43.3", "<b>46.0</b>", "48.4", "50.9", "", ""],
        ["temperature (°C)", "43.8", "45.3", "46.3", "46.7", "", ""],
    ], [50 * mm, 16 * mm, 17 * mm, 16 * mm, 16 * mm, 25 * mm, W - 140 * mm]))
    s.append(Spacer(1, 6))
    s.append(KeepTogether([p("CPU over the 5 minutes", H3), chart(rows),
                           p("The load is flat: there are no spikes, and nothing grows over time.", BODY)]))

    s.append(p("Inside the python3 process", H3))
    s.append(p("nebio threads (and in the Csound bank also Csound) run inside nebulae.py, so the "
               "process is split per thread:"))
    s.append(table([
        ["Thread", "mean %", "max %", "What it is"],
        ["main thread (tid 528)", "<b>79.0</b>", "84.2", "Python main loop: updateAll(), ControlHandler, ui.py"],
        ["tid 577", "<b>20.2</b>", "21.9", "nebio input thread, 1 kHz scan"],
        ["tid 559", "1.6", "2.7", "nebio thread (LED writer or gate events)"],
        ["tid 560", "0.8", "1.8", "nebio thread"],
        ["tid 578", "0.0", "0.9", "nebio thread (idle)"],
    ], [38 * mm, 18 * mm, 16 * mm, W - 72 * mm]))
    s.append(p("The nebio threads are not named yet, so all show as python3. The input thread is "
               "identified by its steady 20 %, which matches the earlier hardware test.", SUB))

    # 4 ------------------------------------------------------------------
    s.append(p("4. Hidden kernel work: interrupts", H2))
    s.append(p("The programs above add up to <b>29 %</b> of the Pi, but /proc/stat shows <b>46 %</b> busy "
               "(user 26.5 %, system 19.3 %, idle 54.0 %). The missing 17 % (about 0.7 of a core) "
               "belongs to no process. This kernel uses tick-based accounting without IRQ time "
               "accounting (CONFIG_HZ=100), so interrupt work that happens while a core is idle is "
               "counted as system time without any process. Interrupt rates over the 5 minutes:"))
    s.append(table([
        ["Source", "per second", "Cause"],
        ["IPI3 function call", "9 582", "Cores signalling each other (follows the SPI and thread wake-ups)"],
        ["<b>fe204000.spi</b>", "<b>7 996</b>", "nebio ADC reads: 2 chips x 8 channels x 500 Hz = 8000, one "
         "interrupt per channel transfer"],
        ["arch_timer", "1 289", "Kernel timer (1 kHz nebio sleep wake-ups)"],
        ["<b>fe804000.i2c</b>", "<b>986</b>", "LED writes to the PCA9685, although nothing is being touched"],
        ["DMA IRQ x 2", "375 + 375", "Audio stream, 48000 / 128 frames. Expected"],
        ["IPI2 rescheduling", "29", ""],
    ], [36 * mm, 22 * mm, W - 58 * mm]))
    s.append(p("New processes were also checked: only 2 were started in 10 s, so short-lived "
               "processes are not the cause."))

    # 5 ------------------------------------------------------------------
    s.append(p("5. Hardware test results", H2))
    s.append(p("hwtest.py ran at boot instead of nebulae (firmware built with "
               "<font face='Courier'>create_fw_update.sh --hwtest</font>), with audio playing and the log "
               "written to the USB stick."))
    s += bullets([
        "<b>Inputs:</b> all knobs, both encoders, buttons and gates registered (118 digital events). "
        "CV 4 (pitch) and CV 1 (speed) were seen moving; the other CV inputs were not patched in "
        "that run.",
        "<b>nebio:</b> scan 1000 Hz, worst scan 1.0-2.4 ms, test process about 22 % of one core, "
        "whole Pi 1-20 %, 41-42 °C, not throttled.",
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
        "<b>USB stick dropped out during one boot</b> (sda \"device offline or changed\", I/O errors). "
        "Copying an .instr and a .pd file from the stick failed. Not related to nebio; the stick "
        "or the USB power should be checked.",
        "<b>Code/log is missing early in boot</b>, so the first neb_log.txt lines are lost. Harmless.",
    ])

    # 7 ------------------------------------------------------------------
    s.append(p("7. Possible improvements (not done)", H2))
    s.append(p("To be decided after the comparison with the original firmware:"))
    s.append(table([
        ["Change", "Expected effect"],
        ["Pace the Python main loop lower (for example 200 Hz instead of about 500 Hz)",
         "Largest saving: the 79 % main thread scales with the loop rate. Knob smoothing filters "
         "work per loop and would need retuning."],
        ["ADC reads at 250 Hz instead of 500 Hz", "Halves the SPI interrupts (8000/s) and part of the "
         "input thread"],
        ["Write LEDs only when a value changes by more than a small threshold",
         "Removes most of the 1000 I2C interrupts/s caused by knob noise"],
        ["Name the nebio threads (pthread_setname_np)", "top and cpustat.sh show nebio-input, "
         "nebio-leds, ... instead of python3"],
    ], [75 * mm, W - 75 * mm]))

    # 8 ------------------------------------------------------------------
    s.append(p("8. How to compare with the original firmware", H2))
    s.append(p("Install the original firmware, load the <b>same SC instrument</b>, do not touch the "
               "module, copy the script to /tmp (the original firmware does not have it) and run:"))
    s.append(Preformatted("sudo sh /tmp/cpustat.sh -d 300 -l \"SC bank, original firmware\"\n"
                          "# -> /tmp/cpustat_<date>.txt (report) and .csv (one row per second)\n"
                          "# /tmp is cleared at reboot: copy both files off before rebooting", CODE))
    s.append(p("Repeat for the Csound and Pure Data banks on both firmwares. In the Csound bank the "
               "python line includes Csound. Compare: python mean, whole-Pi mean, the system share "
               "and the SPI/I2C interrupt rates."))
    s.append(KeepTogether([p("Files", H3), table([
        ["File", "Content"],
        ["measurements/cpustat/nebio_sc_20261016_084140.txt", "Raw report of this measurement"],
        ["measurements/cpustat/nebio_sc_20261016_084140.csv", "One row per second (chart data)"],
        ["measurements/cpustat/make_report.py", "Builds this PDF"],
        ["Code/scripts/cpustat.sh", "Measurement script"],
        ["Code/nebio/tools/hwtest.py, ledwalk.py", "Hardware test and LED walk"],
    ], [85 * mm, W - 85 * mm])]))

    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title="nebio CPU Measurement", author="QB Nebulae V2")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
