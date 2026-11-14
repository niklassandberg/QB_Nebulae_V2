#!/usr/bin/env python3
# Writes the random scenarios tests/scenarios/fuzz_*.txt (fixed seeds, so the
# same files every time): long mixed op sequences for compare.py.
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "scenarios")


def num(r):
    """A typed number token as the scenarios write them."""
    kind = r.random()
    if kind < 0.15:
        return "i:%d" % r.randint(-3, 5)
    if kind < 0.25:
        return "f:%r" % r.choice([0.0, 1.0, 0.5, -0.0, 0.125, 0.3333333333333333, 1e-05, 2.675])
    return "f:%r" % round(r.uniform(-0.5, 1.5), r.randint(1, 17))


def adc_code(r, last):
    m = r.random()
    if m < 0.3:
        return last
    if m < 0.6:
        return max(0, min(4095, last + r.randint(-12, 12)))
    if m < 0.8:
        return r.randint(0, 4095)
    return r.choice([0, 1, 2047, 2048, 4094, 4095])


def fuzz_adc(r, n):
    out = ["# random knob and CV values through AdcData / HybridData"]
    codes = {(d, c): 2048 for d in (0, 1) for c in range(8)}
    objs = []
    out.append("n.snapshot")
    for i, (pot, cv, name, lo, hi, init) in enumerate([
            (1, 1, "blend", "i:0", "i:1", "f:0.5"), (0, -1, "start", "f:0.0", "f:1.0", "i:0"),
            (6, -1, "size_alt", "i:0", "i:1", "f:0.3"), (-1, 4, "x", "f:-1.0", "f:2.0", "i:1"),
            (7, 7, "overlap", "i:0", "i:3", "i:2")]):
        out.append("adc.new a%d %d %d %s %s %s %s" % (i, pot, cv, name, lo, hi, init))
        objs.append("a%d" % i)
    for i, (ch, name, lo, hi, init) in enumerate([
            (1, "speed", "f:0.0", "f:1.0", "f:0.625"), (4, "pitch", "i:0", "i:1", "f:0.4"),
            (2, "other", "i:0", "i:2", "i:1"), (-1, "speed_alt", "i:0", "i:32", "i:5")]):
        out.append("hyb.new h%d %d %s %s %s %s" % (i, ch, name, lo, hi, init))
        objs.append("h%d" % i)
    for _ in range(n):
        m = r.random()
        if m < 0.25:
            for _ in range(r.randint(1, 4)):
                key = r.choice(list(codes))
                codes[key] = adc_code(r, codes[key])
                out.append("adc %d %d %d" % (key[0], key[1], codes[key]))
            out.append("n.snapshot")
        o = r.choice(objs)
        if o[0] == "a":
            op = r.choices(["getValue", "getPot", "getCV", "setValue", "setIgnoreHID", "setResistVal",
                            "clearResistVal", "isResisting", "getPotValue", "getCVValue", "clipControl",
                            "setCVOffset", "getRawPotValue", "getRawCVValue"],
                           [40, 6, 6, 4, 3, 2, 2, 2, 2, 2, 3, 1, 2, 2])[0]
        else:
            op = r.choices(["getValue", "setValue", "setIgnoreHID", "getStaticVal", "getRawCVValue",
                            "getCVValue", "setCVOffset"], [50, 8, 3, 2, 3, 3, 1])[0]
        args = ""
        if op in ("setValue", "setResistVal", "clipControl"):
            args = " " + num(r)
        elif op == "setIgnoreHID":
            args = " b:%s" % r.choice(["True", "False"])
        elif op == "setCVOffset":
            args = " f:%r" % round(r.uniform(-0.05, 0.05), 4)
        prefix = "adc" if o[0] == "a" else "hyb"
        out.append("%s.%s %s%s" % (prefix, op, o, args))
    return out


def fuzz_digital(r, n):
    out = ["# random button and gate edges through DigitalData in every mode",
           "time 5000", "sr 0", "sr.new s", "sr.update s"]
    gpios = {23: 1, 24: 1, 25: 1, 4: 1, 17: 1}
    for p in gpios:
        out.append("gpio %d 1" % p)
    objs = []
    k = 0
    for mode in ("latching", "triggered", "momentary", "incremental"):
        for edge in ("falling", "rising"):
            for bg, gate, button in ((1, 24, 3), (2, 6, 5), (0, 17, 25), (5, -1, 0), (4, -1, 4)):
                name = r.choice(["record", "source", "file", "file_alt", "x", "reset_alt"])
                lt = r.choice(["0", "1"])
                inc = r.randint(0, 2)
                maximum = r.choice(["i:1", "i:3", "i:5", "f:4.0"])
                init = r.choice(["i:0", "i:1", "f:2.0", "i:7"])
                out.append("dd.new d%d %s %d %d %d s %s %s %s %s %d %s" % (
                    k, name, bg, gate, button, mode, edge, maximum, lt, inc, init))
                objs.append("d%d" % k)
                k += 1
    srbits = 0
    for _ in range(n):
        m = r.random()
        if m < 0.15:
            srbits ^= 1 << r.choice([0, 3, 4, 5, 6, 7])
            out.append("sr %d" % srbits)
            out.append("sr.update s")
        elif m < 0.25:
            p = r.choice(list(gpios))
            gpios[p] ^= 1
            out.append("gpio %d %d" % (p, gpios[p]))
            out.append("advance 0.26")
        elif m < 0.33:
            out.append("advance %r" % round(r.uniform(0.0, 0.06), 4))
        elif m < 0.36:
            out.append("rand %d %d" % (r.randint(-1, 6), r.randint(0, 3)))
        o = r.choice(objs)
        op = r.choices(["getValue", "getLEDValue", "setIgnoreHID", "setIgnoreGate", "setIgnoreNextButton",
                        "setOutputPeriod", "setMode", "getTrigSource", "setValue", "setIncOrder"],
                       [60, 15, 2, 2, 2, 1, 1, 3, 1, 1])[0]
        args = ""
        if op in ("setIgnoreHID", "setIgnoreGate"):
            args = " b:%s" % r.choice(["True", "False"])
        elif op == "setOutputPeriod":
            args = " i:%d" % r.choice([5, 10, 40])
        elif op == "setMode":
            args = " s:%s s:%s" % (r.choice(["latching", "triggered", "momentary", "incremental"]),
                                   r.choice(["falling", "rising"]))
        elif op == "setValue":
            args = " i:%d" % r.randint(0, 4)
        elif op == "setIncOrder":
            args = " i:%d" % r.randint(0, 2)
        out.append("dd.%s %s%s" % (op, o, args))
    return out


def fuzz_pages(r, n):
    out = ["# random encoder page use"]
    curves = [("lin", "f:0.0", "f:1.0"), ("exp", "f:20.0", "f:20000.0"), ("int", "i:1", "i:16"),
              ("lin", "i:-5", "i:5"), ("exp", "f:0.5", "f:4.0")]
    pages = []
    for i in range(7):
        c, lo, hi = r.choice(curves)
        step = r.choice(["", " f:0.01", " f:0.05", " i:1"])
        out.append("pg.new p%d n%d /neb/page/n%d %s %s %s %s%s" % (i, i, i, lo, hi, c, num(r), step))
        pages.append("p%d" % i)
    out.append("ep.new e0 speed p0,p1,p2 n1")
    out.append("ep.new e1 pitch p3,p4,p5,p6 None")
    out.append("ep.new e2 speed p0 n0 4095,2000,0")
    out.append("ps.new st pages/fuzz.pages")
    eps = ["e0", "e1", "e2"]
    now = 0
    for _ in range(n):
        e = r.choice(eps)
        op = r.choices(["step", "move", "nextPage", "startChoosing", "setCandidate", "candidateShown",
                        "commitCandidate", "outputs", "state", "colour", "marked", "save", "changed"],
                       [30, 8, 8, 3, 6, 3, 3, 15, 8, 2, 2, 2, 4])[0]
        if op == "step":
            out.append("ep.step %s i:%d" % (e, r.randint(-30, 30)))
        elif op == "move":
            out.append("ep.move %s %s" % (e, num(r)))
        elif op == "setCandidate":
            out.append("ep.setCandidate %s b:%s" % (e, r.choice(["True", "False"])))
        elif op == "outputs":
            out.append("ep.outputs %s %s" % (e, num(r)))
        elif op in ("colour", "marked"):
            out.append("ep.%s %s i:%d" % (op, e, r.randint(-2, 7)))
        elif op == "save":
            out.append("ps.saveIfDue st i:%d speed=e0,pitch=e1" % now)
            out.append("file.read pages/fuzz.pages")
        elif op == "changed":
            out.append("ps.changed st i:%d" % now)
        else:
            out.append("ep.%s %s" % (op, e))
        now += r.randint(0, 400)
    out.append("ps.save st speed=e0,pitch=e1")
    out.append("pg.new l0 n1 x f:0.0 f:1.0 lin f:0.0")
    out.append("pg.new l1 n2 x f:0.0 f:1.0 lin f:0.0")
    out.append("ep.new le speed l0,l1 None")
    out.append("ps.load st speed=le")
    out.append("ep.state le")
    return out


def fuzz_texts(r, n):
    out = ["# random texts through the number parsing of configsettings and the scale curves"]
    pieces = ["0", "1", "5", "9", ".", "_", "e", "-", "+", " ", "1_0", "inf", "nan", "x", "00", "2.5"]
    for _ in range(n):
        text = "".join(r.choice(pieces) for _ in range(r.randint(0, 5))).replace(" ", "\\_")
        kind = r.random()
        if kind < 0.25:
            out.append("cfg.holdoff s:%s" % text)
        elif kind < 0.5:
            out.append("cfg.rate s:%s i:7" % text)
        elif kind < 0.75:
            key = r.choice(["led_dim", "nebio_scan_hz", "gate_holdoff_ms", "power_regulator", "wifi"])
            out.append("cfg.checked %s=%s" % (key, text))
        else:
            c = r.choice(["lin", "exp", "int"])
            out.append("scale %s %s %s %s" % (num(r), num(r), num(r), c))
        if r.random() < 0.2:
            out.append("hyst %s %s %s" % (num(r), num(r), num(r)))
    return out


HANDLER_SETTINGS = ("speed,0.625|pitch,0.6|start,0|size,0|blend,0|density,0|overlap,0|window,0|reset,0|"
                    "freeze,0|source,0|record,0|file,0|speed_alt,23|pitch_alt,0|start_alt,0|size_alt,0|"
                    "blend_alt,0|density_alt,0|overlap_alt,0|window_alt,0.0|reset_alt,0|freeze_alt,0|"
                    "source_alt,0|record_alt,0|file_alt,0")
HANDLER_CONFIGS = [
    ("p.scd", "speed,pages|page:speed:cut,/p/cut,100,8000,exp,0.5|page:speed:res,/p/res,0,1,lin,0.2,0.05|"
              "page:pitch:note,/p/note,16,76,int,0.4,0.02|cv:speed,cut|cv:pitch,none|"
              "hold:record:pitch:echo,/p/echo,0,1,lin,0.3|hold:record:speed:fb,/p/fb,0,2|"
              "hold:record+file:pitch:vol,/p/vol,0,10,int,0.5|freeze,triggered,rising|record,momentary,rising"),
    ("r.scd", "speed,rawencoder|freeze,toggle|file,incremental,falling|"
              "hold:freeze:pitch:x,/r/x,0,1|hold:freeze+source:speed:y,/r/y,-1,1"),
    ("h.scd", "pitch,hybrid|reset,triggered,falling"),
]


# audrey's and miRings' blocks (Programs/*/*.prog).
PROG_CONFIGS = [
    ("a.prog", "oscport,3021|reset,momentary,rising|freeze,latching,rising|file,momentary,rising|"
               "osc:density,/audrey/feedback,0,1|osc:blend,/audrey/reverb_mix,0,1|"
               "osc:size,/audrey/reverb_size,0,1|osc:window,/audrey/lpf,0,1|osc:overlap,/audrey/hpf,0,1|"
               "osc:start,/audrey/body,0,1|osc:reset,/audrey/gate,0,1|osc:freeze,/audrey/drone,0,1|"
               "osc:source,/audrey/source,0,1|osc:record,/audrey/echo,0,1|osc:file,/audrey/echo_tap,0,1|"
               "page:pitch:note,/audrey/note,16,76,lin,0.4|page:pitch:shape,/audrey/shape,0,1,lin,0|"
               "page:speed:input,/audrey/input,0,1,lin,0.3|page:speed:lfo,/audrey/lfo,0,2,int,0|"
               "hold:record:speed:echo_cutoff,/audrey/echo_cutoff,100,8000,exp,0.4745|"
               "hold:record:pitch:echo_feedback,/audrey/echo_feedback,0,1.5,lin,0.5|"
               "hold:record+file:pitch:echo_volume,/audrey/echo_volume,0,1,lin,0.5|"
               "hold:record+file:speed:echo_wownflutter,/audrey/echo_wownflutter,0,1,lin,0.5|"
               "cv:pitch,note|cv:speed,none"),
    ("m.prog", "oscport,3020|osc:pitch,/rings/note,24,84|osc:speed,/rings/fm,-12,12|"
               "osc:blend,/rings/structure,0,1|osc:window,/rings/brightness,0,1|osc:density,/rings/damping,0,1|"
               "osc:start,/rings/position,0,1|osc:overlap,/rings/model,0,11,int|osc:size,/rings/polyphony,1,4,int|"
               "osc:reset,/rings/strum,0,1|osc:freeze,/rings/internal_exciter,1,0|osc:blend_alt,/rings/fm_in,0,48|"
               "osc:record_alt,/rings/mono,0,1"),
]


def fuzz_handler(r, n, bank="sc"):
    """A handler's main loop (the SC or programs bank): buttons (one edge per
    pass), knobs, CV and encoders, page turns, mode changes and instrument
    switches."""
    sc = bank == "sc"
    configs = HANDLER_CONFIGS if sc else PROG_CONFIGS
    out = ["# random main-loop passes through controlhandler%s.py and its bases" % ("SC" if sc else "Prog"),
           "cs.none", "mx.reset lib", "file.write defaultnebsettings.txt " + HANDLER_SETTINGS]
    for name, block in configs:
        out.append("file.write %s nebconfigbegin|%s|nebconfigend" % (name, block))
        out.append("nc.new c%s %s" % (name[0], name))
    first = configs[0][0][0]
    if sc:
        out += ["h.new h sc 5 p supercollider cp", "h.setConfig h cp p.pages", "h.startScOscServer h",
                "h.enterSuperColliderMode h", "h.startRawEncoders h", "time 5000", "calls"]
    else:
        out += ["h.new h prog 5 %s programs c%s" % (first, first), "h.setConfig h c%s %s.pages" % (first, first),
                "h.enterProgramsMode h", "time 5000", "calls"]
    codes = {(d, c): 2048 for d in (0, 1) for c in range(8)}
    bits = 0
    for _ in range(n):
        m = r.random()
        if m < 0.3:
            bits ^= 1 << r.choice([0, 0, 3, 3, 3, 4, 5, 7, 7, 7])
            out.append("sr %d" % bits)
        elif m < 0.55:
            for _ in range(r.randint(1, 3)):
                key = r.choice(list(codes))
                codes[key] = adc_code(r, codes[key])
                out.append("adc %d %d %d" % (key[0], key[1], codes[key]))
        elif m < 0.65:
            out.append("ret encoder_steps %d" % r.choice([-3, -1, 0, 0, 1, 2]))
        out.append("advance %r" % r.choice([0.001, 0.0025, 0.01, 0.05, 0.18, 0.6, 1.2]))
        out.append("h.updateAll h")
        if m < 0.3:
            out.append("h.enc h")
        k = r.random()
        if k < 0.08:
            enc = r.choice(["speed", "pitch"])
            op = r.choice(["pageStep", "pageStep", "pageJump", "nextPage"])
            out.append("h.%s h s:%s%s" % (op, enc, "" if op == "nextPage" else " i:%d" % r.randint(-4, 4)))
        elif k < 0.10:
            out.append("h.setCvOn h s:%s b:%s" % (r.choice(["speed", "pitch"]), r.choice(["True", "False"])))
        elif k < 0.11:
            out.append(r.choice(["h.enterInstrSelMode h", "h.enterNormalMode h", "h.enterSecondaryMode h"]))
        elif k < 0.115:
            c = r.choice(configs)[0]
            out.append("h.setConfig h c%s %s.pages" % (c[0], c[0]))
            if r.random() < 0.7 and sc:
                out.append("h.startRawEncoders h")
        elif k < 0.12:
            out.append(r.choice(["h.saveInstrument h", "h.sendPages h b:True", "h.closeSockets h"]))
        if r.random() < 0.15:
            out.append("calls")
        if r.random() < 0.05:
            out.append(r.choice(["h.enc h", "h.pages h", "h.state h" if sc else "h.prog h", "h.chans h"]))
    out += ["calls", "h.enc h", "h.pages h", "h.state h", "h.chans h", "h.saveInstrument h",
            "file.read %s.pages" % first, "file.read nebsettings.txt"]
    if not sc:
        out.append("h.prog h")
    return out


def fuzz_pd(r, n):
    """The Pd handler's main loop, with the connection and sends failing."""
    out = ["# random main-loop passes through controlhandlerPD.py",
           "cs.none", "mx.reset lib", "file.write defaultnebsettings.txt " + HANDLER_SETTINGS,
           "h.new h pd 5 p puredata None", "ret pd_is_connected 1", "h.enterPureDataMode h",
           "time 5000", "calls"]
    codes = {(d, c): 2048 for d in (0, 1) for c in range(8)}
    bits = 0
    for _ in range(n):
        m = r.random()
        if m < 0.25:
            bits ^= 1 << r.choice([0, 3, 4, 5, 7])
            out.append("sr %d" % bits)
        elif m < 0.6:
            for _ in range(r.randint(1, 3)):
                key = r.choice(list(codes))
                codes[key] = adc_code(r, codes[key])
                out.append("adc %d %d %d" % (key[0], key[1], codes[key]))
        elif m < 0.65:
            out.append("ret %s %d" % (r.choice(["pd_is_connected", "pd_send", "pd_take_ready"]), r.choice([0, 1])))
        out.append("advance %r" % r.choice([0.001, 0.0025, 0.01, 0.05, 0.18, 0.6, 1.2]))
        out.append("h.updateAll h")
        if r.random() < 0.01:
            out.append(r.choice(["h.enterInstrSelMode h", "h.enterNormalMode h", "h.enterSecondaryMode h",
                                 "h.saveInstrument h", "h.closeSockets h"]))
        if r.random() < 0.2:
            out.append("calls")
        if r.random() < 0.05:
            out.append(r.choice(["h.pd h", "h.state h", "h.chans h"]))
    out += ["calls", "h.pd h", "h.state h", "h.chans h"]
    return out


def main():
    gens = [("fuzz_adc", fuzz_adc, 4000), ("fuzz_digital", fuzz_digital, 5000),
            ("fuzz_pages", fuzz_pages, 2500), ("fuzz_texts", fuzz_texts, 2500),
            ("fuzz_handler", fuzz_handler, 6000),
            ("fuzz_prog", lambda r, n: fuzz_handler(r, n, "prog"), 6000),
            ("fuzz_pd", fuzz_pd, 5000)]
    for seed, (name, gen, n) in enumerate(gens, 1):
        lines = gen(random.Random(seed * 7919), n)
        with open(os.path.join(OUT, name + ".txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        print("%s: %d lines" % (name, len(lines)))


if __name__ == "__main__":
    main()
