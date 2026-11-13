# Runs a scenario (tests/scenarios/*.txt) against the original Python classes
# Names and sources are interned: the handlers pass literals, and control.py
# compares them with "is" (source is "hybrid", name is "speed").
# and prints the trace: "L<line> <result>". tests/cpp/runner.cpp does the same
# against the C++ port; compare.py checks the two traces are identical.
import os
import shutil
import sys
import tempfile

import harness
from harness import fmt, number, tokens

clock, clib = harness.setup()

import importlib
import logging

import classlogger
import configsettings
import control
import controlhandler
import controlhandlerEncoders
import controlhandlerProg
import controlhandlerSC
import digitaldata
import encoderpages
import fatal
import MCP3208
import nebconfig
import nconfig
import nebio
import nebmixer
import pdsender
import scsender
import settings
import shiftregister
import switch
import textfile
import wavewriter

rng = harness.FakeRandom()
digitaldata.time = clock
digitaldata.random = rng
scsender.time = clock

CALIBRATION = "/home/alarm/QB_Nebulae_V2/Code/misc/calibration_data.txt"
BUFFER_CNT = "/home/alarm/QB_Nebulae_V2/Code/config/buffer_cnt.txt"


def val(text):
    """Typed scenario value: i:3 f:0.5 b:True s:text None L:a,b (list of str)."""
    if text == "None":
        return None
    kind, _, rest = text.partition(":")
    if kind == "i":
        return int(rest)
    if kind == "f":
        return float(rest)
    if kind == "b":
        return rest == "True"
    if kind == "s":
        return rest
    if kind == "L":
        return [x for x in rest.split(",")] if rest else []
    return number(text)


class Runner(object):
    def __init__(self, workdir):
        self.dir = workdir
        self.objs = {}
        self.out = []
        self.cs = None
        self.cfgdata = None
        self.disk = None
        self.cmdline_nohlt = False
        self.bg = []
        self.line = 0
        self.stick_mounted = False
        self.stick_mountable = True
        os.chdir(workdir)
        self._patch()

    def path(self, name):
        return os.path.join(self.dir, name)

    # File paths of the originals, moved into the work dir.
    def _patch(self):
        real_open = open
        mapping = {CALIBRATION: self.path("calibration_data.txt"),
                   BUFFER_CNT: self.path("buffer_cnt.txt")}

        def text_open(p, *a, **k):
            return real_open(mapping.get(p, p), *a, **k)
        textfile.open = text_open

        nebconfig.INSTR_DIRS = {bank: (self.path(folder) + "/", ext) for bank, (folder, ext) in
                                (("instr", ("instr", ".instr")), ("supercollider", ("sc", ".scd")),
                                 ("puredata", ("pd", ".pd")), ("programs", ("prog", ".prog")))}
        fatal.STICK = self.path("stick") + "/"
        fatal.MARKER = self.path("nebulae-fatal")
        fatal._log = lambda line: self.emit("fatal log " + line)
        fatal._now = lambda: "2026-11-13 12:00:00"
        fatal._stopNebio = lambda: self.emit("fatal stopNebio")
        fatal._stickMounted = lambda: self.stick_mounted
        fatal._run = self.fatal_run
        fatal._exit = self.fatal_exit

        configsettings.CONFIG_FILE = self.path("configsettings.txt")
        configsettings.REQUEST_FILE = self.path("config_request")
        configsettings.CMDLINE = self.path("cmdline.txt")
        configsettings._kernelHasNohlt = lambda: self.cmdline_nohlt

        runner = self
        real_os = os

        class WaveOs(object):
            path = real_os.path

            @staticmethod
            def statvfs(p):
                if runner.disk is None:
                    return real_os.statvfs(runner.path("memory"))

                class S(object):
                    f_bsize, f_bfree = runner.disk
                return S()

            @staticmethod
            def system(cmd):
                runner.emit("system(%s)" % cmd)
                return 0

            @staticmethod
            def remove(p):
                return real_os.remove(p)

        wavewriter.os = WaveOs
        settings.os = WaveOs
        self._patch_handlers()

    # The handlers: their settings, WAV writer and /proc/net/udp in the work
    # dir, the clock faked, the WAV thread run in place.
    def _patch_handlers(self):
        import types
        runner = self
        real_open = open

        class Settings(settings.SettingManager):
            def __init__(s, config):
                super(Settings, s).__init__(config)
                s.filepath = runner.dir + "/"

        def make_writer():
            w = wavewriter.WaveWriter.__new__(wavewriter.WaveWriter)
            runner._wave_init(w)
            return w

        class InPlaceThread(object):
            def __init__(s, target=None):
                s.target = target

            def start(s):
                if s.target is None:
                    return
                try:
                    s.target()
                except Exception as e:
                    runner.emit("thread E:" + type(e).__name__)

            def is_alive(s):
                return False

            def join(s):
                pass

        udp = {"/proc/net/udp": self.path("proc_udp"), "/proc/net/udp6": self.path("proc_udp6")}
        # holdButtons() is a set: its order, which decides the layer when two
        # buttons go down in one pass, changes with the hash seed. The tests
        # take HOLD_PINS' order, as the port does.
        held = controlhandlerEncoders.EncoderControlHandler.holdButtons
        controlhandlerEncoders.EncoderControlHandler.holdButtons =             lambda h: [b for b in controlhandlerEncoders.HOLD_PINS if b in held(h)]
        controlhandler.settings = types.SimpleNamespace(SettingManager=Settings)
        controlhandler.wavewriter = types.SimpleNamespace(WaveWriter=make_writer)
        controlhandler.threading = types.SimpleNamespace(Thread=InPlaceThread)
        controlhandler.time = clock
        controlhandlerSC.time = clock
        controlhandlerSC.open = lambda p, *a, **k: real_open(udp.get(p, p), *a, **k)

    # The work dir differs between the runners: "W" in the trace.
    def emit(self, text):
        self.out.append("L%d %s" % (self.line, text.replace(self.dir, "W")))

    def put(self, v):
        self.emit(fmt(v))

    def run(self, lines):
        for n, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            self.line = n
            t = tokens(line)
            try:
                self.op(t[0], t[1:])
            except harness.FatalStop:
                self.emit("STOPPED")
            except Exception as e:
                self.emit("E:" + type(e).__name__)
        return self.out

    def lt_cb(self, name):
        return lambda: self.emit("LONGTOUCH " + name)

    def pages_dict(self, spec):
        out = {}
        for part in spec.split(",") if spec != "-" else []:
            name, _, oid = part.partition("=")
            out[name] = self.objs[oid]
        return out

    def op(self, op, a):
        o = self.objs
        # --- fakes -------------------------------------------------------
        if op == "time":
            clock.t = float(a[0])
        elif op == "advance":
            clock.t += float(a[0])
        elif op == "rand":
            rng.queue.extend(int(x) for x in a)
        elif op == "ret":
            clib.ret[a[0]] = val(a[1])
        elif op == "gpio":
            clib.gpio[int(a[0])] = int(a[1])
        elif op == "sr":
            clib.sr = int(a[0])
        elif op == "adc":
            clib.adc[int(a[0]) * 8 + int(a[1])] = int(a[2])
        elif op == "calls":
            for c in clib.calls:
                self.emit("call " + c)
            clib.calls = []
        elif op == "cs.new":
            self.cs = harness.FakeCsound()
        elif op == "cs.none":
            self.cs = None
        elif op == "cs.chan":
            self.cs.channelPtr(a[0], 0)
            self.cs.calls.pop()
            self.cs.chans[a[0]][0] = val(a[1])
        elif op == "cs.read":
            self.put(self.cs.chans[a[0]][0] if a[0] in self.cs.chans else None)
        elif op == "cs.tables":
            import numpy as np
            left, right = wave_data(a[0], int(a[1]), np)
            self.cs.tables[200], self.cs.tables[201] = left, right
        elif op == "cs.calls":
            for c in self.cs.calls:
                self.emit("cs " + c)
            self.cs.calls = []
        elif op == "usb.mounted":
            harness.FakeUsb.mounted = a[0] == "1"
        elif op == "usb.calls":
            for c in harness.FakeUsb.calls:
                self.emit("usb " + c)
            harness.FakeUsb.calls = []
        elif op == "disk":
            self.disk = None if a[0] == "real" else (int(a[0]), int(a[1]))
        elif op == "file.write":
            with open(self.path(a[0]), "w") as f:
                f.write(" ".join(a[1:]).replace("|", "\n"))
        elif op == "file.read":
            try:
                with open(self.path(a[0]), "rb") as f:
                    data = f.read()
                self.emit("file %s %s" % (a[0], data.decode("latin-1").replace("\n", "|")))
            except OSError:
                self.emit("file %s missing" % a[0])
        elif op == "file.hex":
            import hashlib
            with open(self.path(a[0]), "rb") as f:
                data = f.read()
            self.emit("file %s %d %s %s" % (a[0], len(data), data[:48].hex(),
                                             hashlib.sha256(data).hexdigest()))
        elif op == "file.rm":
            try:
                os.remove(self.path(a[0]))
            except OSError:
                pass
        elif op == "soak":
            self.soak(int(a[0]), int(a[1]), o[a[2]], o[a[3]], [o[x] for x in a[4:]])
        elif op == "bench":
            self.bench(int(a[0]), o[a[1]], [o[x] for x in a[2:]])
        elif op == "file.bytes":
            with open(self.path(a[0]), "wb") as f:
                f.write(bytes.fromhex("".join(a[1:])))
        elif op == "ls":
            try:
                self.emit("ls %s %s" % (a[0], ",".join(sorted(os.listdir(self.path(a[0]))))))
            except OSError:
                self.emit("ls %s missing" % a[0])
        elif op == "fatal.on":
            fatal.enabled = True
        elif op == "fatal.off":
            fatal.enabled = False
        elif op == "stick.mounted":
            self.stick_mounted = a[0] == "1"
        elif op == "stick.mountable":
            self.stick_mountable = a[0] == "1"
        elif op == "tf.read":
            self.put(textfile.read(self.path(a[0])))
        elif op == "tf.lines":
            self.put(textfile.lines(self.path(a[0])))
        elif op == "tf.instrument":
            self.put(fatal.instrumentOf(self.path(a[0])))
        elif op == "mkdir":
            os.makedirs(self.path(a[0]), exist_ok=True)
        elif op == "rmdir":
            shutil.rmtree(self.path(a[0]), ignore_errors=True)
        # --- nebio.py ----------------------------------------------------
        elif op.startswith("n."):
            self.nebio_op(op[2:], a)
        # --- switch / shiftregister / MCP3208 ----------------------------
        elif op == "sw.new":
            o[a[0]] = switch.Switch(int(a[1]))
        elif op == "sw.q":
            s = o[a[0]]
            self.put([s.risingEdge(), s.fallingEdge(), s.state(), s.prevState()])
        elif op == "sr.new":
            o[a[0]] = shiftregister.ShiftRegister()
        elif op == "sr.q":
            s, i = o[a[0]], int(a[1])
            self.put([s.risingEdge(i), s.fallingEdge(i), s.state(i), s.prevState(i)])
        elif op == "mcp.new":
            o[a[0]] = MCP3208.MCP3208(int(a[1]))
        elif op == "mcp.read":
            self.put(o[a[0]].read_adc(int(a[1])))
        # --- control.py --------------------------------------------------
        elif op == "hyst":
            self.put(control.addHysteresis(val(a[0]), val(a[1]), val(a[2])))
        elif op == "control.reload":
            if a[0] == "none":
                self.op("file.rm", ["nebulae.opt"])
            else:
                self.op("file.write", ["nebulae.opt"] + a)
            importlib.reload(control)
        elif op == "adc.new":
            o[a[0]] = control.AdcData(int(a[1]), int(a[2]), sys.intern(a[3]), val(a[4]), val(a[5]), val(a[6]))
        elif op == "hyb.new":
            o[a[0]] = control.HybridData(int(a[1]), sys.intern(a[2]), val(a[3]), val(a[4]), val(a[5]))
        elif op == "st.new":
            o[a[0]] = control.StaticData(val(a[1]))
        elif op == "raw.new":
            o[a[0]] = control.RawEncoderData(a[1])
        elif op == "comm.new":
            o[a[0]] = control.CommChannel(self.cs, a[1])
        elif op == "comm.flag":
            self.put(o[a[0]].rising_edge_flag)
        elif op == "ctl.new":
            kw = {}
            for item in a[4:]:
                k, _, v = item.partition("=")
                if k == "sr":
                    kw[k] = o[v]
                elif k == "config":
                    kw[k] = v.split(",")
                elif k == "longtouch_cb":
                    kw[k] = self.lt_cb(a[1])
                else:
                    kw[k] = val(v)
            o[a[0]] = control.ControlChannel(self.cs, sys.intern(a[1]), val(a[2]), sys.intern(a[3]), **kw)
        elif op == "ctl.chan":
            self.put(o[a[0]].channel[0])
        elif op == "calib":
            self.op("file.write", ["calibration_data.txt"] + a)
        elif op == "calib.none":
            self.op("file.rm", ["calibration_data.txt"])
        # --- digitaldata.py ----------------------------------------------
        elif op == "dd.new":
            # id name bgmode gate button sr mode edge max longtouch inc init
            cb = self.lt_cb(a[1]) if a[9] == "1" else None
            o[a[0]] = digitaldata.DigitalData(sys.intern(a[1]), int(a[2]), int(a[3]), int(a[4]), o.get(a[5]),
                                              a[6], a[7], val(a[8]), cb, int(a[10]), val(a[11]))
        # --- encoderpages.py ---------------------------------------------
        elif op == "scale":
            self.put(encoderpages.scale(val(a[0]), val(a[1]), val(a[2]), a[3]))
        elif op == "pulse":
            self.put(encoderpages.pulse(val(a[0])))
        elif op == "pg.new":
            step = val(a[7]) if len(a) > 7 else encoderpages.PAGE_STEP
            o[a[0]] = encoderpages.Page(a[1], a[2], val(a[3]), val(a[4]), a[5], val(a[6]), step)
        elif op == "pg.value":
            self.put(o[a[0]].value)
        elif op == "ep.new":
            pages = [o[p] for p in a[2].split(",")] if a[2] != "-" else []
            target = None if a[3] == "None" else a[3]
            hold = tuple(int(x) for x in a[4].split(",")) if len(a) > 4 else None
            o[a[0]] = encoderpages.EncoderPages(a[1], pages, target, hold)
        elif op == "ep.outputs":
            self.put(o[a[0]].outputs(val(a[1])))
        elif op == "ep.state":
            p = o[a[0]]
            self.put([p.current, p.cv_target, p.candidate, [x.value for x in p.pages]])
        elif op == "ps.new":
            o[a[0]] = encoderpages.PageState(self.path(a[1]))
        elif op in ("ps.load", "ps.save"):
            getattr(o[a[0]], op[3:])(self.pages_dict(a[1]))
        elif op == "ps.changed":
            o[a[0]].changed(val(a[1]))
        elif op == "ps.saveIfDue":
            o[a[0]].saveIfDue(val(a[1]), self.pages_dict(a[2]))
        elif op == "ps.dirty":
            self.put(o[a[0]].dirty_time)
        # --- settings.py -------------------------------------------------
        elif op == "cfgdata":
            if a[0] == "None":
                self.cfgdata = None
            else:
                self.cfgdata = {}
                for item in a:
                    k, _, v = item.partition("=")
                    self.cfgdata[k] = val(v)
        elif op == "set.new":
            s = settings.SettingManager(self.cfgdata)
            s.filepath = self.dir + "/"
            o[a[0]] = s
        elif op == "set.lines":
            self.put(o[a[0]].lines)
        elif op == "set.dicts":
            s = o[a[0]]
            self.put([[k, s.settingDict[k]] for k in s.settingDict])
            self.put([[k, s.defaultDict[k]] for k in s.defaultDict])
            self.put([[k, s.mutableSettings[k]] for k in s.mutableSettings])
        # --- wavewriter.py -----------------------------------------------
        elif op == "wav.new":
            w = wavewriter.WaveWriter.__new__(wavewriter.WaveWriter)
            self._wave_init(w)
            o[a[0]] = w
        elif op == "wav.write":
            import numpy as np
            n = int(a[2])
            left, right = wave_data(a[3], n, np)
            if len(a) > 4:
                right = right[:int(a[4])]
            self.put(o[a[0]].WriteStereoWaveFile(left, right, val(a[1])))
            self.put(o[a[0]].num_written)
        # --- nebmixer.py -------------------------------------------------
        elif op == "mx.reset":
            nebmixer._libasound = FakeAsound(self) if a[0] == "lib" else None
            nebmixer._mixer = None
            nebmixer._capturecontrol_handle = None
            nebmixer._hifi_output_handle = None
            nebmixer._enable = True
        elif op == "mx.fail":
            nebmixer._libasound.fail.add(a[0])
        elif op == "mx.nohandle":
            nebmixer._libasound.nohandle.add(a[0])
        elif op.startswith("mx."):
            fn = getattr(nebmixer, op[3:])
            self.put(fn(*[val(x) for x in a]))
        # --- pdsender.py / scsender.py -----------------------------------
        elif op == "pd.new":
            o[a[0]] = pdsender.PdSend()
        elif op == "sc.new":
            o[a[0]] = scsender.ScSend()
        elif op == "pd.send":
            self.put(o[a[0]].send([val(x) for x in a[1:]]))
        elif op == "sc.const":
            self.put([scsender.ScSend.rPort, scsender.ScSend.sPort, pdsender.PdSend.sport])
        elif op in ("sc.waitSynthIsUp",):
            self.put(o[a[0]].waitSynthIsUp(val(a[1])))
            self.put(clock.t)
        # --- configsettings.py -------------------------------------------
        elif op == "cmdline.nohlt":
            self.cmdline_nohlt = a[0] == "1"
        elif op == "cfg.new":
            c = configsettings.ConfigSettings()
            c._runInBackground = lambda cmd: self.emit(
                "bg " + (cmd.__name__ if callable(cmd) else " ".join(cmd)))
            o[a[0]] = c
        elif op == "cfg.props":
            c = o[a[0]]
            self.put([c.powerRegulator, c.noPwm, c.ledStagger, c.servicesQuiet, c.wifiOn,
                      c.ledDim, c.logLevel, c.nebioScanHz, c.nebioDigitalHz, c.nebioAdcHz,
                      c.nebioFastGpio, c.csoundRtPriority, c.gateInterrupts, c.gateHoldoffMs])
        elif op == "cfg.checked":
            self.put(sorted_items(configsettings.checkedRequest(kv(a))))
        elif op == "cfg.writeRequest":
            self.put(sorted_items(configsettings.writeRequest(kv(a))))
        elif op == "cfg.takeRequest":
            self.put(sorted_items(configsettings.takeRequest()))
        elif op == "cfg.holdoff":
            self.put(configsettings._holdoff(val(a[0])))
        elif op == "cfg.rate":
            self.put(configsettings._rate(val(a[0]), val(a[1])))
        elif op == "cfg.needsRestart":
            self.put(o[a[0]].powerNeedsRestart)
        elif op == "cfg.syncCmdline":
            o[a[0]]._syncCmdline()
        elif op == "cfg.setNebioRates":
            self.put(o[a[0]].setNebioRates(*[val(x) for x in a[1:]]))
        # --- classlogger.py ----------------------------------------------
        elif op == "log.priority":
            self.put(classlogger._priority(int(a[0])))
        elif op == "log.format":
            f = classlogger.JournalFormatter("%(levelname)s [%(filename)s:%(lineno)d]: %(message)s")
            f.journal = a[4] == "1"
            rec = logging.LogRecord("x", int(a[0]), a[1], int(a[2]), a[3].replace("|", "\n"), None, None)
            self.put(f.format(rec))
        # --- nconfig.py --------------------------------------------------
        elif op == "ini.new":
            o[a[0]] = nconfig.NConfig()
        elif op == "ini.get":
            self.put(o[a[0]].getValue(a[1], a[2], val(a[3])))
        # --- nebconfig.py ------------------------------------------------
        elif op == "nc.new":
            o[a[0]] = nebconfig.NebConfig.readFile(self.path(a[1]))
        elif op == "nc.entries":
            self.put([[k, v] for k, v in o[a[0]].asDict().items()])
        elif op == "nc.pages":
            pages, errors = o[a[0]].encoderPages()
            self.put([[e, [list(p) for p in ps]] for e, ps in pages.items()])
            self.put(errors)
        elif op == "nc.holds":
            holds, errors = o[a[0]].holdPages()
            self.put([[layer, [[e, [list(p) for p in ps]] for e, ps in encs.items()]]
                      for layer, encs in holds.items()])
            self.put(errors)
        elif op == "nc.cv":
            self.put([[k, v] for k, v in o[a[0]].cvTargets().items()])
        elif op == "nc.entry":
            self.put(o[a[0]].entry(a[1]))
        elif op == "nc.osc":
            bindings, errors = o[a[0]].oscBindings()
            self.put([list(b) for b in bindings])
            self.put(errors)
        # --- controlhandler*.py ------------------------------------------
        elif op == "h.new" and a[1] == "prog":
            # As nebulae.py's start_programs(): no configData, the port and
            # bindings from the block.
            config = o[a[5]]
            try:
                port = config.oscPort()
            except ValueError:
                port = nebconfig.DEFAULT_OSC_PORT
            o[a[0]] = controlhandlerProg.ProgControlHandler(
                self.cs, val(a[2]), None, a[3], bank=a[4], oscPort=port, bindings=config.oscBindings()[0])
        elif op == "h.new":
            cls = {"base": controlhandler.ControlHandler,
                   "sc": controlhandlerSC.SCControlHandler}[a[1]]
            cfg = None if a[5] == "None" else o[a[5]].asDict()
            o[a[0]] = cls(self.cs, val(a[2]), cfg, a[3], bank=a[4])
        elif op == "h.setConfig":
            o[a[0]].setConfig(o[a[1]], self.path(a[2]))
        elif op == "h.state":
            h = o[a[0]]
            self.put([h.control_mode, h.prev_control_mode, h.instr_sel_idx, h.prep_mode_change,
                      h.static_file_idx, h.in_ticks, h.writing_buffer, h.buffer_failure,
                      [[k, h.editFunctionFlag[k]] for k in sorted(h.editFunctionFlag)]])
        elif op == "h.enc":
            h = o[a[0]]
            self.put([h.hold_active, h.hold_used, sorted(h.hold_blocked),
                      [[k, h.hold_since[k]] for k in sorted(h.hold_since)], h.cv_assign,
                      [[k, h.page_sent[k]] for k in sorted(h.page_sent)], getattr(h, "rawReady", None),
                      sorted(h.holdFirstButtons()), sorted(h.holdButtons())])
        elif op == "h.chans":
            h = o[a[0]]
            self.put([[c.name, c.source, c.getValue()] for c in h.channels])
            self.put([[c.name, c.getValue()] for c in h.altchannels])
        elif op == "h.pages":
            h = o[a[0]]
            self.put([[k, p.current, p.cv_target, p.candidate, [x.value for x in p.pages],
                       list(p.hold) if p.hold else None] for k, p in h.allPages().items()])
        elif op == "h.prog":
            h = o[a[0]]
            self.put([h.oscPort, h.speed_leds, h.prog_resend_time,
                      [[k, h.prog_sent[k]] for k in sorted(h.prog_sent)],
                      [[k, [list(t) for t in h.bindings[k]]] for k in sorted(h.bindings)]])
        elif op == "h.rawChannels":
            self.put([c.name for c in o[a[0]].rawChannels()])
        # --- any method of an object -------------------------------------
        elif "." in op:
            obj = o[a[0]]
            self.put(getattr(obj, op.split(".", 1)[1])(*[val(x) for x in a[1:]]))
        else:
            raise ValueError("unknown op " + op)

    # Main loop passes (tests/bench): knobs, CV, buttons and gates moving,
    # then srg.update(), update() and getValue() of every channel and, with a
    # sender, ScSend.send() of every value. Only srg and the channels are
    # timed, not the fake nebio. Returns the timed seconds.
    def passes(self, first, n, srg, chans, last, changes, sender=None):
        import time
        total = 0.0
        for i in range(first, first + n):
            clock.t += 0.001
            for k in range(16):
                clib.adc[k] = (i * 37 + k * 101) % 4096
            clib.sr = (i // 100) % 256
            for p in (4, 6, 23, 24, 25):
                clib.gpio[p] = (i // (50 + p)) % 2
            nebio.snapshot()
            t0 = time.perf_counter()
            srg.update()
            for j, c in enumerate(chans):
                c.update()
                v = c.getValue()
                if v != last[j]:
                    changes[j] += 1
                    last[j] = v
            total += time.perf_counter() - t0
            if sender is not None:
                for c in chans:
                    sender.send(c.name, c.getValue())
        return total

    # The trace gets each channel's changes and last value: B and W must
    # agree over the whole run.
    def bench(self, n, srg, chans):
        last = [c.getValue() for c in chans]
        changes = [0] * len(chans)
        total = self.passes(0, n, srg, chans, last, changes)
        sys.stderr.write("bench python: %d passes, %d channels: %.2f us/pass\n"
                         % (n, len(chans), total / n * 1e6))
        self.put([[changes[j], last[j]] for j in range(len(chans))])

    # Hours of passes in chunks; resident memory after each chunk to stderr.
    def soak(self, chunks, n, srg, sender, chans):
        last = [c.getValue() for c in chans]
        changes = [0] * len(chans)
        rss = []
        for chunk in range(chunks):
            self.passes(chunk * n, n, srg, chans, last, changes, sender)
            del clib.calls[:]  # the fake's call log, not the code under test
            with open("/proc/self/statm") as f:
                rss.append(int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") // 1024)
        sys.stderr.write("soak python: %d x %d passes (%.1f h at 1 kHz), RSS KB: %s\n"
                         % (chunks, n, chunks * n / 3.6e6, " ".join(map(str, rss))))
        self.put([[changes[j], last[j]] for j in range(len(chans))])

    def fatal_run(self, cmd):
        self.emit("fatal run " + " ".join(cmd))
        if cmd[0] == "mount" and self.stick_mountable:
            self.stick_mounted = True
        elif cmd[0] == "umount":
            self.stick_mounted = False
        elif cmd[0] == "journalctl":
            return "journal line 1\njournal line 2\n"
        return ""

    def fatal_exit(self, code):
        self.emit("fatal exit %d" % code)
        raise harness.FatalStop()

    def _wave_init(self, w):
        # WaveWriter.__init__ with its two paths in the work dir.
        src = wavewriter.WaveWriter.__init__
        fpath = self.path("buffer_cnt.txt")
        outpath = self.path("memory") + "/"
        real_open = open
        wavewriter.open = lambda p, *a, **k: real_open(
            fpath if p == "/home/alarm/QB_Nebulae_V2/Code/config/buffer_cnt.txt" else p, *a, **k)

        class WavOsPath(object):
            @staticmethod
            def isfile(p):
                return os.path.isfile(fpath if p.endswith("buffer_cnt.txt") else p)

            @staticmethod
            def getsize(p):
                return os.path.getsize(fpath if p.endswith("buffer_cnt.txt") else p)
        wavewriter.os.path = WavOsPath
        src(w)
        wavewriter.os.path = os.path
        w.fpath = fpath
        w.outpath = outpath

    def nebio_op(self, name, a):
        fn = getattr(nebio, name)
        args = [val(x) for x in a]
        r = fn(*args)
        if name in ("adc_codes",):
            r = list(r)
        if name == "inputs":
            r = None
        self.put(r)


def wave_data(kind, n, np):
    i = np.arange(n, dtype=np.float64)
    if kind == "tri":
        return np.fmod(i * 37, 1000.0) / 500.0 - 1.0, np.fmod(i * 91, 999.0) / 499.5 - 1.0
    if kind == "ramp":
        return (i % 200) / 100.0 - 1.0, 1.0 - (i % 77) / 38.5
    return np.zeros(n), np.zeros(n)


class FakeAsound(object):
    """libasound's mixer functions as nebmixer calls them."""

    def __init__(self, runner):
        self.runner = runner
        self.fail = set()
        self.nohandle = set()

    def __getattr__(self, name):
        if not name.startswith("snd_"):
            raise AttributeError(name)

        def call(*args):
            shown = []
            for x in args:
                if hasattr(x, "_obj"):  # byref()
                    shown.append("&")
                elif hasattr(x, "value"):
                    shown.append(fmt(x.value))
                elif isinstance(x, (bytes, str, int, float)) or x is None:
                    shown.append(fmt(x))
                else:
                    shown.append(fmt(getattr(x, "raw", b"").rstrip(b"\0")))
            self.runner.emit("asound %s(%s)" % (name, ",".join(shown)))
            if name in self.fail:
                return -1
            if name == "snd_mixer_find_selem":
                return None if name in self.nohandle or self._nohandle(args) else 1234
            return 0
        return call

    def _nohandle(self, args):
        # args[1]: a create_string_buffer (capture) or the selem id (hifi)
        which = "capture" if hasattr(args[1], "raw") else "hifi"
        return which in self.nohandle


def kv(a):
    out = {}
    for item in a:
        k, _, v = item.partition("=")
        out[k] = v
    return out


def sorted_items(d):
    return [[k, d[k]] for k in sorted(d)]


def main():
    scenario = sys.argv[1]
    with open(scenario) as f:
        lines = f.read().splitlines()
    work = tempfile.mkdtemp(prefix="nebport_py_")
    try:
        out = Runner(work).run(lines)
    finally:
        os.chdir("/")
        shutil.rmtree(work, ignore_errors=True)
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
