#!/usr/bin/env python3
# make_report.py
# Builds nebio_cpu_report.pdf from the cpustat.sh measurements in this folder.
# Main result: original firmware (0419df1) against nebio with matched input
# rates, both with the Csound instrument a_granularlooper. Also the first
# comparison (SC bank, nebio at its default rates).
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
from reportlab.platypus import (KeepTogether, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_ORIG_CS = os.path.join(HERE, "orig_cs_granular_20261016_222919.csv")
CSV_NEBIO_CS = os.path.join(HERE, "nebio_matched_cs_granular_20261016_230314.csv")
CSV_ORIG_SC = os.path.join(HERE, "orig_sc_20261016_102031.csv")
CSV_NEBIO_SC = os.path.join(HERE, "nebio_sc_20261016_084140.csv")
OUT = os.path.join(HERE, "nebio_cpu_report.pdf")

PURPLE = colors.HexColor("#3d2b6e")
ORANGE = colors.HexColor("#d9822b")
GREEN = colors.HexColor("#2e7d4f")
LIGHT = colors.HexColor("#ece8f5")
GREY = colors.HexColor("#666666")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Title"], textColor=PURPLE, fontSize=22, leading=26, spaceAfter=2)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], textColor=GREY, fontSize=9.5)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], textColor=PURPLE, fontSize=14, spaceBefore=12, spaceAfter=6)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontName="Helvetica-BoldOblique", fontSize=11,
                    spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("BODY", parent=ss["Normal"], fontSize=9.5, leading=13, spaceAfter=5)
NOTE = ParagraphStyle("NOTE", parent=BODY, textColor=GREY, fontSize=8.5, leading=11)
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


def chart(series, ymax):
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
    lg.columnMaximum = 2
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
    orig_cs = load_csv(CSV_ORIG_CS)
    neb_cs = load_csv(CSV_NEBIO_CS)
    W = A4[0] - 36 * mm
    s = []
    s.append(p("nebio vs. Original Firmware: CPU", H1))
    s.append(p("QB Nebulae V2 (RPi4) &middot; nebio (<b>feature_newHardWareHandling</b>) against the "
               "original firmware (<b>0419df1</b>) &middot; measured 2026-10-16 and 17 on the device", SUB))
    s.append(Spacer(1, 6))

    # 1 ------------------------------------------------------------------
    s.append(p("1. Summary", H2))
    s.append(p("When nebio does the same work as the original firmware, <b>it uses less CPU</b>. Both "
               "were measured with the original Nebulae instrument (Csound <b>a_granularlooper</b>), "
               "updateAll() running about <b>400 times per second</b> in both, and nebio reading the "
               "hardware as often as the original does. 5 minutes each, nobody touching the module."))
    s.append(table([
        ["", "Original (0419df1)", "nebio, matched rates", "Difference"],
        ["updateAll() calls/s", "400.3 (388-407)", "399.9 (399.2-400.2)", "same rate, nebio steadier"],
        ["<b>Control overhead</b> (python3 minus the Csound thread, % of one core)", "78.9 %",
         "<b>70.4 %</b>", "<b>-8.5 points (-11 %)</b>"],
        ["<b>Python main loop</b> (% of one core)", "71.1 %", "<b>52.5 %</b>", "<b>-18.6 (-26 %)</b>"],
        ["Whole Pi busy (4 cores = 100 %)", "35.7 %", "31.8 %", "-3.9 points (Csound load similar "
         "in these two runs)"],
        ["CPU time per updateAll() pass", "1.78 ms", "<b>1.31 ms</b>", "<b>-26 %</b>"],
        ["I2C interrupts/s (LED writes)", "5 702", "<b>1 111</b>", "<b>-81 %</b>"],
        ["Inter-core interrupts/s", "16 140", "6 619", "-59 %"],
        ["SPI interrupts/s (ADC reads)", "6 415", "6 391", "same (reading is matched)"],
    ], [52 * mm, 33 * mm, 35 * mm, W - 120 * mm]))
    s.append(Spacer(1, 4))
    s += bullets([
        "<b>Control overhead</b> is the fair measure: the Csound thread's load depends on the knob "
        "settings (more grains are stacked at some settings) and changed between 49.5 and 65.5 % "
        "of a core across the runs, so it is left out. What remains is the firmware's own work.",
        "<b>The firmware's own work costs 8.5 points of a core less with nebio</b>, including "
        "nebio's input thread (14.8 % of a core), which replaces the two Python encoder threads "
        "and the hardware reads in the main loop.",
        "<b>Each updateAll() pass is 26 % cheaper</b>: the Python side no longer does the SPI and "
        "GPIO reads itself, it reads a snapshot that nebio has already filled.",
        "<b>LED writes dropped by 81 %</b>, because nebio only writes LEDs that changed.",
        "<b>Optimisations inside nebio afterwards</b> (section 5) gave about 2 more points of a "
        "core: skipping 2 unused ADC channels and an optional fast GPIO path (section 6).",
        "<b>The first comparison looked worse</b> (section 7) because nebio then ran updateAll() "
        "about 25 % more often and scanned the hardware 2.5 times as often as the original. "
        "That was more work, not more cost per unit of work.",
        "<b>To look at:</b> nebio's input thread is sometimes held up for several milliseconds "
        "(worst scan up to 6.2 ms against an 833 &micro;s period), section 4.",
    ])

    # 2 ------------------------------------------------------------------
    s.append(p("2. How the comparison was made", H2))
    s.append(p("Same instrument, same work: the original sets the pace, nebio is configured to match it."))
    s.append(table([
        ["What", "Original firmware (0419df1)", "nebio, matched"],
        ["updateAll() rate", "as fast as it can: measured 400/s", "at most 400/s: each snapshot waits "
         "for new ADC data (ADC 400 Hz). Measured 399.9/s"],
        ["Shift register (buttons, source gate)", "once per updateAll(), ~400/s", "400 Hz (digital rate)"],
        ["Encoder clicks", "once per pass, ~400/s", "400 Hz (digital rate)"],
        ["ADCs (knobs, CV)", "once per pass, ~400/s", "400 Hz (ADC rate)"],
        ["Encoders", "2 Python threads, sleep(1 ms): just under 1000/s", "1200 Hz (scan rate). A bit "
         "above the original, so not in nebio's favour"],
        ["Gates", "read once per pass", "edge interrupts (no cost while no gate arrives)"],
        ["Button debounce", "3 equal reads", "8 ms = 3 reads at 400 Hz"],
    ], [42 * mm, 58 * mm, W - 100 * mm]))
    s.append(Spacer(1, 4))
    s.append(p("<b>Setting the rates.</b> nebio got a third rate for this (digital) next to the scan and "
               "ADC rates, a one-time C++ change. The rates are now set from Python, no recompiling:"))
    s.append(Preformatted("# Code/nebulae/controlhandler.py\n"
                          "NEBIO_SCAN_HZ = 1200     # encoders, every scan (the input thread's clock)\n"
                          "NEBIO_DIGITAL_HZ = 400   # shift register + encoder clicks, every 3rd scan\n"
                          "NEBIO_ADC_HZ = 400       # knobs + CV, every 3rd scan; caps updateAll() at 400/s\n"
                          "nebio.set_input_rates(NEBIO_SCAN_HZ, NEBIO_DIGITAL_HZ, NEBIO_ADC_HZ)", CODE))
    s.append(p("<b>Counting updateAll().</b> Both firmwares got the same counter in "
               "ControlHandler.updateAll(): one increment per call and a log line every 10 s "
               "(<font face='Courier'>updateAll: N calls/s</font>) in /tmp/nebulae_logging.log. nebio "
               "also logs its own rates (<font face='Courier'>nebio: scan 1200 Hz, snapshot 400 Hz, worst "
               "scan ... us</font>); its snapshot count matched the Python counter."))
    s.append(p("<b>CPU.</b> Code/scripts/cpustat.sh (sh + awk + /proc only), 300 s, one sample per second. "
               "CPU values are <b>% of one core</b> like top; the whole-Pi value uses /proc/stat, where all "
               "4 cores = 100 %. Raspberry Pi 4, Arch Linux ARM armv7h (32 bit), kernel 5.15, governor "
               "performance, 1200 MHz. The nebio run started after 60 s of warm-up after boot."))

    # 3 ------------------------------------------------------------------
    s.append(p("3. Main result: Csound a_granularlooper", H2))
    s.append(table([
        ["Program", "Firmware", "min %", "mean %", "p95 %", "max %", "share of Pi", "max RSS"],
        ["<b>python3</b> (incl. Csound)", "original", "126.5", "130.7", "133.4", "134.7", "32.7 %", "307 MB"],
        ["", "nebio", "114.5", "<b>119.9</b>", "123.8", "125.7", "30.0 %", "303 MB"],
        ["<b>whole Pi</b>", "original", "32.2", "35.7", "37.4", "41.1", "", ""],
        ["(4 cores = 100 %)", "nebio", "20.9", "<b>31.8</b>", "39.1", "39.9", "", ""],
        ["temperature °C", "original", "41.9", "43.5", "44.3", "45.3", "", ""],
        ["", "nebio", "37.5", "40.5", "42.4", "42.8", "", ""],
    ], [34 * mm, 19 * mm, 14 * mm, 16 * mm, 14 * mm, 14 * mm, 21 * mm, W - 132 * mm]))
    s.append(p("sclang was idle (0 %) in both runs; scsynth, jackd and pd were not running (Csound uses "
               "ALSA directly and runs inside python3).", NOTE))
    s.append(KeepTogether([p("CPU over the 5 minutes", H3), chart([
        (orig_cs, "python_pct_of_core", "python3, original (% of one core)", PURPLE, True),
        (neb_cs, "python_pct_of_core", "python3, nebio (% of one core)", PURPLE, False),
        (orig_cs, "pi_total_pct", "whole Pi, original (% of 4 cores)", ORANGE, True),
        (neb_cs, "pi_total_pct", "whole Pi, nebio (% of 4 cores)", ORANGE, False),
    ], 160), p("Dashed: original. Solid: nebio. The python3 lines are steady in both runs. nebio's "
               "whole-Pi line swings between about 21 and 39 % with a period of a few seconds; this "
               "is a measurement effect, see the note below.", NOTE)]))

    s.append(p("Note on the per-second whole-Pi values", H3))
    s.append(p("The swing in nebio's whole-Pi line is not real load. In some seconds the whole-Pi value "
               "(e.g. 23 %) is <b>lower than the python3 process alone</b> (about 30 % of the Pi), which "
               "is impossible. The python3 process itself is as steady as in the original (standard "
               "deviation 0.5 against 0.4 points); the swing is entirely in whole Pi minus python3 "
               "(standard deviation 5.6 against 1.1 points)."))
    s.append(p("Likely cause: this kernel counts busy time by sampling at 100 Hz but counts idle time "
               "exactly, and nebio's input thread wakes at 1200 Hz, an exact multiple of 100 Hz. The "
               "two drift slowly against each other, so for a few seconds the samples tend to land on "
               "busy moments, then on idle ones. The original has no fixed-rate thread like this."))
    s.append(p("<b>The results are not affected.</b> The 5-minute means add up the kernel's totals "
               "over about 60 such cycles, so the swing averages out (python3 30.0 % + rest 1.9 % = "
               "31.8 %). Per-process and per-thread figures, the updateAll() rate, interrupt counts "
               "and nebio's own statistics are counted, not sampled, and show no swing. Only single "
               "per-second whole-Pi values for nebio should not be read on their own.", BODY))

    s.append(p("Inside the python3 process", H3))
    s.append(table([
        ["Thread", "Original", "nebio", "What it is"],
        ["<b>main thread</b>", "71.1 %", "<b>52.5 %</b>", "Python main loop: updateAll(), ControlHandler, ui.py"],
        ["Csound performance thread", "51.8 %", "49.5 %", "audio; the same instrument, so about the same"],
        ["encoder threads (2)", "5.8 %", "-", "original: Python threads polling the encoders"],
        ["nebio input thread", "-", "14.8 %", "1200 Hz scan: encoders; shift register, clicks, ADCs at 400 Hz"],
        ["other threads", "2.0 %", "3.0 %", "nebio: LED writer, gate events, reset LED PWM"],
        ["<b>total</b>", "<b>130.7 %</b>", "<b>119.9 %</b>", ""],
    ], [40 * mm, 20 * mm, 20 * mm, W - 80 * mm]))
    s.append(p("Per updateAll() pass the main loop costs 71.1 % / 400.3 = <b>1.78 ms</b> in the original "
               "and 52.5 % / 399.9 = <b>1.31 ms</b> with nebio.", BODY))

    s.append(p("Kernel work and interrupts", H3))
    s.append(table([
        ["", "Original", "nebio"],
        ["user / system / idle (% of Pi)", "28.9 / 6.8 / 64.3", "27.0 / 5.3 / 67.7"],
        ["Kernel time without a process (% of Pi)", "3.0 %", "1.8 %"],
    ], [70 * mm, 45 * mm, W - 115 * mm]))
    s.append(Spacer(1, 4))
    s.append(table([
        ["Interrupts per second", "Original", "nebio", "Cause"],
        ["IPI3 function call", "16 140", "6 619", "cores signalling each other"],
        ["fe204000.spi", "6 415", "6 391", "ADC reads: matched"],
        ["arch_timer", "3 368", "2 289", "kernel timer"],
        ["fe804000.i2c", "5 702", "<b>1 111</b>", "LED writes to the PCA9685"],
        ["DMA IRQ x 2", "94 + 94", "94 + 94", "audio (Csound, 512-frame blocks). Same"],
    ], [40 * mm, 20 * mm, 20 * mm, W - 80 * mm]))
    s.append(p("The extra kernel time seen in the first comparison (section 7) is gone: with matched "
               "rates the measured programs explain almost all of the Pi's load.", BODY))

    # 4 ------------------------------------------------------------------
    s.append(p("4. To look at: nebio's worst scan time", H2))
    s.append(p("nebio logs the longest scan of every 10 s window. At 1200 Hz a scan has 833 &micro;s, "
               "but the worst scan was <b>4.3 ms on average and 6.2 ms at most</b> during the run. The "
               "average rate stays exactly 1200 Hz (the thread catches up), but now and then the input "
               "thread is held up for several milliseconds."))
    s += bullets([
        "Likely cause: the input thread runs at <b>normal priority</b> and competes with Csound and "
        "the Python main loop.",
        "Effect: averages are not affected; during such a stall a fast-turned encoder could lose a "
        "step, and inputs arrive a few ms later.",
        "Possible fix: give the input thread real-time priority <b>below</b> the audio (jackd runs "
        "at 75), and check that the mutex shared with snapshot() cannot cause priority inversion.",
    ])

    # 5 ------------------------------------------------------------------
    s.append(p("5. Optimisations inside nebio", H2))
    s.append(p("After the matched comparison, three ideas to lower nebio's own cost were tried, each "
               "measured separately (same rates 1200/400/400, Csound a_granularlooper, 5 minutes):"))
    s.append(table([
        ["Optimisation", "Result", "Kept?"],
        ["<b>Skip the unused knob ADC channels 3 and 4</b> (read 14 instead of 16 channels; all 8 CV "
         "channels are still read)", "SPI interrupts 6 391 -> <b>5 600/s (-12.4 %)</b>, input thread "
         "14.8 -> <b>13.4 %</b> of a core", "<b>yes</b>"],
        ["<b>SPI polling mode</b> (kernel parameter spi_bcm2835.polling_limit_us 30 -> 100, set at "
         "run time)", "SPI interrupts 6 414 -> 0/s, but whole Pi 32.9 -> <b>36.4 %</b>: the thread "
         "busy-waits instead of sleeping", "<b>no</b>, set back to 30"],
        ["<b>Fast GPIO</b>: shift register and encoder/click pins through /dev/gpiomem instead of "
         "libgpiod (about 10 400 fewer syscalls/s)", "input thread 13.6 -> <b>13.1 %</b> of a core "
         "(measured back to back, fast off/on)", "<b>in the code, off by default</b> (flag, section 6)"],
    ], [68 * mm, 70 * mm, W - 138 * mm]))
    s.append(Spacer(1, 6))
    s.append(table([
        ["Run (% of one core)", "python3", "- Csound", "= control overhead", "main loop", "input handling"],
        ["Original (0419df1)", "130.7", "51.8", "<b>78.9</b>", "71.1", "5.8 (2 encoder threads)"],
        ["nebio, matched rates", "119.9", "49.5", "<b>70.4</b>", "52.5", "14.8"],
        ["nebio + skip pot 3/4", "135.9", "65.5", "<b>70.4</b>", "53.9", "13.4"],
        ["nebio + skip pot 3/4, fast GPIO off", "132.4", "61.7", "<b>70.7</b>", "53.9", "13.6"],
        ["nebio + skip pot 3/4, fast GPIO on", "131.1", "61.7", "<b>69.4</b>", "53.2", "13.1"],
    ], [52 * mm, 18 * mm, 18 * mm, 28 * mm, 20 * mm, W - 136 * mm]))
    s.append(p("The fast GPIO off/on pair was measured back to back, each right after a restart, with "
               "the same Csound load (61.7 % in both). updateAll() ran at 399.8-399.9/s in all nebio "
               "runs. The main loop varies by about 1 point between runs.", NOTE))
    s.append(p("<b>Why the gain is small.</b> On the Pi 4 a GPIO syscall costs only about 1 &micro;s, so "
               "removing 10 400 of them per second saves about 1.2 % of a core, and the 1 &micro;s "
               "safety pulses of the fast path (18 per shift-register read, busy-waited) cost about "
               "0.7 % back. Most of the input thread's 13 % is waking up 1200 times per second for "
               "the encoders and the 14 SPI transfers per ADC read, not the GPIO access. The worst "
               "scan time (section 4) did not change, which confirms that it is a scheduling issue, "
               "not a syscall one. The bigger levers are now the Python main loop (about 53 % of a "
               "core) and the encoder scan rate (section 10).", BODY))

    # 6 ------------------------------------------------------------------
    s.append(p("6. Fast GPIO: how to switch it on", H2))
    s.append(p("Fast GPIO is <b>off by default</b>. It is kept in the code because it can matter on "
               "slower boards such as the Raspberry Pi 3, where syscalls cost more."))
    s.append(table([
        ["Where", "What"],
        ["<b>Switch (measuring phase)</b>", "<font face='Courier'>/home/alarm/nebio_fast_gpio</font>: "
         "if this file exists when nebulae starts, fast GPIO is switched on. Delete it to switch off."],
        ["Code/nebulae/controlhandler.py", "<font face='Courier'>NEBIO_FAST_GPIO_FLAG</font> (next to the "
         "NEBIO_*_HZ rates) and in <font face='Courier'>ControlHandler.__init__()</font>, right after "
         "<font face='Courier'>nebio.set_input_rates(...)</font>: "
         "<font face='Courier'>nebio.set_fast_gpio(True)</font> when the file exists"],
        ["Python API (Code/nebulae/nebio.py)", "<font face='Courier'>nebio.set_fast_gpio(True/False)</font> "
         "returns True when fast GPIO is in use; <font face='Courier'>nebio.fast_gpio()</font>. Call "
         "after the inputs are running."],
        ["C API (Code/nebio/include/nebio.h)", "<font face='Courier'>nebio_set_fast_gpio(int on)</font>, "
         "<font face='Courier'>nebio_fast_gpio()</font>"],
        ["Implementation", "Code/nebio/src/gpiomem.h/.cpp (register access), inputs.cpp "
         "(readShiftRegisterFast, readPolledFast, fastSelfCheck, setFastGpio)"],
    ], [52 * mm, W - 52 * mm]))
    s.append(p("Switching it on, on the Pi (the root file system is read-only):", BODY))
    s.append(Preformatted("sudo sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw\n"
                          "sudo touch /home/alarm/nebio_fast_gpio        # rm -f ... to switch off\n"
                          "sudo sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro\n"
                          "sudo systemctl restart nebulae.service", CODE))
    s.append(p("Check in /tmp/nebulae_logging.log and the journal:", BODY))
    s.append(Preformatted("nebio fast GPIO requested (/home/alarm/nebio_fast_gpio): on\n"
                          "[nebio] INFO: fast GPIO self-check ok (0/50 and 0/50 reads differ)\n"
                          "[nebio] INFO: fast GPIO on (/dev/gpiomem, BCM2711 (Pi 4))\n"
                          "nebio: scan 1200 Hz, snapshot 400 Hz, worst scan ... us, gpio fast", CODE))
    s.append(p("Safety", H3))
    s += bullets([
        "<b>Boards:</b> only BCM2835/2836/2837/2711 (Pi 1-4, Zero), recognised from the device tree. "
        "They share the GPIO register layout; /dev/gpiomem hides the different base addresses. "
        "Anything else (e.g. Pi 5) is refused and nebio stays on libgpiod.",
        "<b>Pin functions are never changed.</b> libgpiod still requests the lines and sets "
        "direction and pulls. Before switching, nebio reads the function registers (read only) and "
        "refuses unless latch/clock (GPIO 15/14) are outputs and the data and encoder/click pins "
        "are inputs.",
        "<b>Only two pins can be written</b> through the fast path: latch and clock, enforced by a "
        "fixed write mask.",
        "<b>Pulse width does not depend on the rates:</b> every latch/clock level is held at least "
        "1 &micro;s (the CD4021 needs a few hundred ns at 3.3 V). Raising the scan or digital rate "
        "gives more reads per second, never shorter pulses. Rates are clamped (scan 100-2000 Hz).",
        "<b>Self-check:</b> in the input thread, 50 shift-register and 50 pin reads are compared "
        "between the fast path and libgpiod; with more than 5 differences it stays on libgpiod.",
        "<b>Tested on the Pi 4:</b> read-only check of the registers first, then the self-check "
        "(0/50 differences) and a hand test of all buttons and both encoders, which worked as before.",
        "<b>Not tested on a Pi 3 yet.</b> nebio itself needs libgpiod 2 (kernel 5.10 or newer) there.",
    ])

    # 7 ------------------------------------------------------------------
    s.append(p("7. First comparison: SC bank, nebio at its default rates", H2))
    s.append(p("Measured earlier the same day, before the rates were matched. nebio then scanned at "
               "1000 Hz and read the ADCs at 500 Hz, so updateAll() could run about 500 times per "
               "second against the original's ~408 (measured later with the counter):"))
    s.append(table([
        ["", "Original (0419df1)", "nebio, default rates", "Difference"],
        ["updateAll() calls/s", "~408 (measured later)", "~500 (estimated: ADC rate cap)", "about +25 %"],
        ["Shift register reads/s", "~408", "1000", "x 2.5"],
        ["Whole Pi busy", "26.5 %", "46.0 %", "+19.5 points"],
        ["Python main loop", "74.2 %", "79.0 %", "+4.8"],
        ["nebio input thread", "-", "20.2 %", "new"],
        ["Kernel time without a process (% of Pi)", "2.7 %", "16.8 %", "+14.1"],
        ["SPI interrupts/s", "5 266", "7 996", "+52 %"],
        ["I2C interrupts/s", "4 680", "986", "-79 %"],
    ], [52 * mm, 33 * mm, 42 * mm, W - 127 * mm]))
    s.append(p("At the time this looked like nebio being more expensive. The matched measurement "
               "shows that it was <b>more work</b>: more updateAll() passes, 2.5 times as many "
               "shift-register reads and more ADC reads. The extra kernel time came with those high "
               "rates and disappeared when they were matched. These SC numbers are kept for "
               "reference; the comparison in sections 1-3 is the valid one.", BODY))

    # 8 ------------------------------------------------------------------
    s.append(p("8. Hardware test (nebio)", H2))
    s += bullets([
        "hwtest.py ran at boot instead of nebulae (firmware built with "
        "<font face='Courier'>create_fw_update.sh --hwtest</font>), log on the USB stick.",
        "<b>Inputs:</b> all knobs, both encoders, buttons and gates registered.",
        "<b>LEDs:</b> PCA9685 registers matched the expected values; ledwalk.py lit every LED and "
        "colour on its own, all worked.",
        "<b>Audio:</b> played during the test, 0 underruns.",
    ])

    # 9 ------------------------------------------------------------------
    s.append(p("9. Other findings", H2))
    s += bullets([
        "The Pi is <b>32 bit (armv7h)</b>, not aarch64.",
        "sudo asks for the root password; pacman 7 needs <font face='Courier'>--disable-sandbox</font> "
        "on kernel 5.15. libgpiod 2.3.1 was installed for nebio.",
        "ClassLogger writes to <font face='Courier'>/tmp/nebulae_logging.log</font>, not to the "
        "journal.",
        "The Pi's clock jumps when it syncs time after boot (about 2 h on 2026-10-16); updateAll() "
        "counting uses time.time(), so one 10 s sample spans the jump. Use time.monotonic() for pacing.",
        "Older python2 firmwares do not run on this image (no OSC module, broken hashlib). OSC.py was "
        "copied into the Python 2 site-packages; the python3 firmwares do not need it.",
        "check_wifi.py and check_calibration.py use nebio through switch.py (the step 1 report says "
        "they use the old drivers).",
        "One boot had a USB stick drop-out (I/O errors); a_granularlooper.instr could not be copied "
        "then. Not related to nebio.",
    ])

    # 10 -----------------------------------------------------------------
    s.append(p("10. Next steps", H2))
    s.append(table([
        ["Step", "Why"],
        ["<b>Python main loop</b>: fewer updateAll() passes (e.g. 200/s, needs the knob smoothing "
         "retuned) or cheaper Python code in updateAll()", "the biggest cost left: about 53 % of a core"],
        ["<b>Encoder scan rate</b>: read the encoders at e.g. 600 Hz, or by interrupt", "1200 wake-ups/s "
         "are most of the input thread's 13 %"],
        ["Real-time priority for nebio's input thread (below the audio)", "worst scan 4-7 ms, "
         "section 4; not CPU, but timing"],
        ["Measure the SC and PD banks with matched rates", "only Csound is compared like for like so far"],
        ["Test fast GPIO on a Pi 3", "where syscalls cost more, the gain may be larger"],
        ["Fix update.sh: build nebio before check_calibration.py", "the calibration check fails right "
         "after an update because libnebio.so is not built yet"],
        ["Decide the default rates (and remove the counter later)", "keep the setter for tuning"],
        ["Name the nebio threads (pthread_setname_np)", "easier to read in top and cpustat"],
        ["Optional: run with a scan rate that is not a multiple of 100 Hz (e.g. 1170/390/390)",
         "only to confirm the cause of the per-second swing (section 3 note)"],
    ], [95 * mm, W - 95 * mm]))

    s.append(KeepTogether([p("Files", H3), table([
        ["File", "Content"],
        ["orig_cs_granular_20261016_222919.txt / .csv", "original, Csound a_granularlooper"],
        ["nebio_matched_cs_granular_20261016_230314.txt / .csv", "nebio 1200/400/400, Csound a_granularlooper"],
        ["orig_updateall_20261016.log", "original: updateAll() rate every 10 s"],
        ["nebio_matched_updateall_20261016.log", "nebio: updateAll() rate, nebio rates, worst scan"],
        ["orig_sc_20261016_102031.txt / .csv", "original, SC bank (first comparison)"],
        ["nebio_sc_20261016_084140.txt / .csv", "nebio default rates, SC bank (first comparison)"],
        ["nebio_opt2_cs_granular_20261017_002742.txt / .csv", "nebio + skip pot 3/4"],
        ["nebio_fastgpio_off_cs_granular_20261017_004525.txt / .csv", "nebio + skip pot 3/4, fast GPIO off"],
        ["nebio_fastgpio_on_cs_granular_20261017_003852.txt / .csv", "nebio + skip pot 3/4, fast GPIO on"],
        ["nebio_opt2_updateall_20261017.log, nebio_fastgpio_updateall_20261017.log", "updateAll() rate, "
         "nebio rates, worst scan, fast GPIO state"],
        ["make_report.py", "builds this PDF"],
    ], [92 * mm, W - 92 * mm]), p("All files are in measurements/cpustat/. The measurement script is "
                                  "Code/scripts/cpustat.sh.", NOTE)]))

    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title="nebio CPU Comparison", author="QB Nebulae V2")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
