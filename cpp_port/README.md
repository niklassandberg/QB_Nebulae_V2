# C++ port of the control handlers and the classes they use

All Python control handlers (`controlhandler.py`, `controlhandlerEncoders.py`,
`controlhandlerSC.py`, `controlhandlerProg.py`, `controlhandlerPD.py`) and
the classes they use (here called **B**), translated to C++ (**W**),
with tests that run both on the same scenarios and require identical
results. Outside the Nebulae code: nothing in `Code/` is changed or used by it.

The port is faithful first: where Python is dynamic (int or float values, a
dict's order) the C++ copies it, mostly through `neb::Value` (`src/pyvalue.h`).
The handlers use plain C++ types where Python's types are fixed anyway.
Taking out the rest of the Python shape comes after, with these tests as the
safety net.

## B → W

| Python (B) | C++ (W) | |
|---|---|---|
| `control.py`: `addHysteresis`, `AdcData`, `StaticData`, `HybridData`, `RawEncoderData`, `CommChannel`, `ControlChannel` | `src/control.*` | |
| `digitaldata.py`: `DigitalData` | `src/digitaldata.*` | |
| `switch.py`, `shiftregister.py`, `MCP3208.py` | `src/inputs.*` | |
| `nebio.py` (inputs, SC/OSC/PD, gate and rate settings) | `src/nebio.*` | LED part (`LedDriver`, ui.py's) not ported |
| `encoderpages.py`: `scale`, `pulse`, `Page`, `EncoderPages`, `PageState` | `src/encoderpages.*` | |
| `settings.py`: `SettingManager` | `src/settings.*` | |
| `wavewriter.py`: `WaveWriter` | `src/wavewriter.*` | |
| `nebmixer.py` | `src/nebmixer.*` | |
| `pdsender.py`, `scsender.py` | `src/senders.*` | |
| `configsettings.py` | `src/configsettings.*` | |
| `classlogger.py` | `src/classlogger.*` | formatting and levels; not the crash hooks |
| `nconfig.py` (configparser) | `src/nconfig.*` | |
| `nebconfig.py`: `NebConfig` (block, `entry`, `value`, `asDict`, `encoderType`, `outputPeriod`, `encoderPages`, `holdPages`, `cvTargets`, `oscBindings`, `oscPort`, `speedLeds`) | `src/nebconfig.*` | also the `.pd` comment boxes; not yet: the JACK, kernel and `run` keys |
| `controlhandler.py`: `ControlHandler` | `src/controlhandler.*` | the Csound bank; settings dir, WAV writer and the writing thread in `HandlerEnv` |
| `controlhandlerEncoders.py`: `EncoderControlHandler` | `src/controlhandlerEncoders.*` | |
| `controlhandlerSC.py`: `SCControlHandler` | `src/controlhandlerSC.*` | `/proc/net/udp` paths in `udpTables` |
| `controlhandlerProg.py`: `ProgControlHandler` | `src/controlhandlerProg.*` | |
| `controlhandlerPD.py`: `PDControlHandler` | `src/controlhandlerPD.*` | keeps the 1 ms sleep per pass |
| `textfile.py`: UTF-8 (BOM, any line end) or `fatal` | `src/textfile.*` | Python's strict decoder rejects the same bytes |
| `fatal.py`: stop on a file that is not UTF-8 | `src/fatal.*` | LEDs, stick, journal, exit behind `fatal::Backend` |
| Python semantics: `round`, `repr(float)`, `float()`/`int()` of a text, `str.strip()` with Unicode spaces, int/float types | `src/pyvalue.*` | |

Everything outside goes through interfaces in `src/nebio_api.h`: nebio's C
functions (`NebioC`), Csound's channels, the clock and random numbers, and in
`nebmixer.h`/`wavewriter.h` libasound and the USB stick. `src/real_backends.cpp`
has the production ones (nebio's `include/nebio.h`, libasound); it is
compiled, not run by the tests.

Not ported, as nothing calls it: `DigitalData.ogGetValue`, `averageInput`,
`AdcData.evaluateNoise`/`getAltValue`, `SettingManager.offloadWrite`.

## The tests

A scenario (`tests/scenarios/*.txt`) is a list of operations, one per line:
set an ADC code or a GPIO level, move the clock, make an object, call a
method. Two runners play it, each printing a trace with every result and its
Python type (`i:0` is not `f:0.0`):

- `tests/py/runner.py` runs the **original Python files from `Code/nebulae`**,
  unchanged. Only the outermost layer is faked (`tests/py/harness.py`):
  nebio's C functions, Csound's channels, `time`, `random`, file paths.
- `tests/cpp/runner.cpp` runs the port with the same fakes.

The fakes log every call to nebio, Csound and libasound into the trace, so a
call made in a different order or with another type is a difference too.

Three checks, all in `run_tests.sh`:

1. `ctest`: the C++ unit tests (`tests/cpp/unit_tests.cpp`, the Python
   semantics) and every scenario against `tests/expected/<name>.txt`.
2. `tests/py/test_originals.py` (unittest): the originals against the same
   expected traces.
3. `tests/compare.py`: both runners side by side; prints a diff on any
   difference.

The expected traces are the originals' output. If an original changes on
purpose, run `compare.py` (it writes `tests/traces/`) and copy the new
`*.py.txt` traces to `tests/expected/`.

`tests/gen_scenarios.py` writes the `fuzz_*` scenarios: about 20 000 random
operations (knob and CV moves, button and gate edges in every mode, page
steps, number texts), fixed seeds.

### Running

```
# WSL archlinux: g++, cmake; a Python 3 with numpy (wavewriter imports it)
python3 -m venv ~/cpp_port_venv && ~/cpp_port_venv/bin/pip install numpy
PYTHON=~/cpp_port_venv/bin/python ./run_tests.sh ~/cpp_port_build
```

### Result (2026-11-13)

24 scenarios, 74 210 trace lines: Python and C++ identical. 26/26 ctest,
28/28 unittest. Also clean with `-fsanitize=address,undefined`.

The handlers: `handler_csound.txt` (Csound's channels back: end of loop,
record status; a file-edit freeze writing the record buffer; secondary
controls; the instrument selector; button modes from the block),
`handler_sc.txt` (encoder sources, pages, hold layers, CV assign, the modes,
the sclang handshakes and its UDP port, an instrument switch) and
`fuzz_handler.txt` (6000 random main-loop passes over three instruments:
button edges, knobs, CV, encoder steps, page turns, mode changes, switches),
`handler_prog.txt` and `fuzz_prog.txt` (the programs bank with audrey's and
miRings' blocks: osc: bindings, changes only, the echo hold layers,
playback speed, bad osc: lines and ports), `handler_pd.txt` and
`fuzz_pd.txt` (Pd messages, changes only, the 1 s resend, a lost connection
or failed send resending everything, the patch's "ready" answer, a .pd
patch's comment boxes),
`nebconfig.txt` the block's parsing and its error messages. The Python runs
give the same trace under any `PYTHONHASHSEED` (checked with 12).

`textfiles.txt` covers the text files: BOM, `\r\n`/`\r`, Unicode spaces and
line separators in every class that reads a file; bytes that are not UTF-8
(Latin-1, overlong, surrogate, > U+10FFFF, cut off, lone continuation) with
`fatal` off (NebFile: `BadTextFile`, read as an unreadable file) and on (a
system file with and without a stick, an instrument's file on the Pi and on
the stick: what is deleted, renamed `.bad` and written to `neb_error.txt`).

## What the tests showed about the originals

Behaviour the port keeps, as the handlers depend on it or it is how the
device behaves today:

- **int or float.** An `AdcData` with `minimum=0` returns the int `0` at the
  bottom of the knob, `HybridData` keeps an int static value int. SC then gets
  `/neb/x` as an int (`[0]`), not a float. The port carries Python's types.
- **`is` instead of `==`.** `source is "hybrid"`, `name is "speed"` work only
  because the handlers pass literals (Python interns them); a name built at
  run time would not match. The port uses `==`.
- **Calibration file.** `gatherOffset("speed")` also reads `speed_alt,...`
  lines (prefix match), the last one wins; a line without a comma ends the
  reading.
- **`scale(..., "int")`** never gives `-0.0` (`round()` is an int).
- **Two hold buttons down in one pass.** `updateHolds()` walks
  `holdButtons()`, a set: its order changes with the hash seed, so each start
  of Nebulae can differ. It matters when two hold buttons count as pressed in
  the same pass: pressed within one scan, or held while `updateHolds()` does
  not run (secondary controls, the instrument selector) or
  over an instrument switch (`setConfig` forgets them). "record" first gives
  the record+file layer, "file" first only the record layer. The port takes
  `HOLD_PINS`' order (record, file, reset, freeze, source); the Python tests
  set the same order (`tests/py/runner.py`).
- **A bad page: line still makes the encoder paged.** `encoderPages()` makes
  the encoder's list before it reads the fields (`setdefault()` first), so an
  encoder whose only page: line is wrong gets an `EncoderPages` without
  pages: it sends nothing (not even /neb/speed), turning it raises
  `IndexError`, `nextPage` `ZeroDivisionError`.

Places where the originals raise (the port raises the same error):

- `WaveWriter`: no `/mnt/memory` → `FileNotFoundError` out of
  `WriteStereoWaveFile`, the stick stays mounted.
- `DigitalData`: incremental with random order and a float maximum →
  `TypeError` (Python 3.12+); a `ShiftRegister` of `None` → `AttributeError`
  on the first read.
- `SettingManager`: a blank line or a line without a comma in
  `defaultnebsettings.txt` → `IndexError`; an `_alt` value from the
  instrument that is not a number before any that is → `UnboundLocalError`;
  after a failed `read()` there are no `mutableSettings`.
- `ControlChannel`: an `init` of `None` (a setting missing from the file)
  → `TypeError`.
- `ControlHandler`: a button in the block with a mode and no edge
  (`freeze,triggered`) or no values (`reset`) → `IndexError`; an `_alt`
  button mode (`file_alt,triggered,rising`) → `UnboundLocalError` from
  `SettingManager` (it reads `_alt` entries as numbers).
- `NebConfig.outputPeriod()`: `ksmps`/`sr` not an int → `ValueError`,
  `sr,0` → `ZeroDivisionError`.

One deliberate fix: `nebmixer.init()` passes the text `"Capture"` to
`snd_mixer_find_selem`, which wants a selem id (libasound then reads past
the text). The real backend looks it up with a proper selem id; the call the
port makes is the same, so the traces are unchanged.

## Threads, speed and long runs

`tests/py/test_threads.py` (unittest, runs with the others) and
`tests/cpp/thread_tests.cpp` (ctest; build it with `-fsanitize=thread` too)
put `configsettings` under the threads it has on the device. Against the
originals (2026-11-13) three failed, now fixed in both:

- the job thread's `_syncCmdline` (applyAtStart) beside `setPowerRegulator`:
  both wrote `cmdline.txt.new`, `FileNotFoundError` in both, and
  `setPowerRegulator` is not caught in ui.py. Now under their own lock.
- NebFile's CherryPy threads saving at once: `FileNotFoundError` in 918 of
  2400 saves (one temp name). Now a temp file per process and thread.
- a save while Nebulae takes the request: the last save lost in 19-31 % of
  trials (read, then remove). Now claimed by a rename first.
- C++ only: the getters read without the lock (a data race in C++, not in
  Python with its GIL). Now locked; ThreadSanitizer clean.

`tests/bench/` (not in ctest, they take minutes):

```
./scenario_runner tests/bench/main_loop.txt  ;  python tests/py/runner.py tests/bench/main_loop.txt
```

- `main_loop.txt`: the granular looper's 15 controls, `bench` = passes of
  snapshot, shift register, update() and getValue() of every channel, time
  to stderr (the fake nebio not timed). Per pass, 2026-11-13: PC (i7-4710HQ)
  Python 80.5 us, C++ 9.3 us; Pi 4 (Nebulae playing) Python 295-346 us,
  C++ 28-32 us, about 11 times. Traces identical after 20 000 passes.
- `soak.txt` (both, 1 M passes = 17 min at 1 kHz, plus ScSend.send of every
  value) and `soak_long_cpp.txt` (C++, 10 M = 2.8 h): RSS per chunk to
  stderr. Flat after the first chunks (C++ 9.3 MB; 45.9 MB in the long run,
  the fake's call log; Python 36 MB); traces identical after 1 M passes.
  nebio's own send cache (real library) is not in it.

## Not verified

- The real backends against hardware (`real_backends.cpp` only compiles).
- `ConfigSettings`' background thread running scripts: the tests catch the
  jobs instead (same order and commands).
- numpy's `astype('int16')` of samples outside -1..1 (undefined in numpy);
  the port wraps.
- configparser beyond the cases in `logger_nconfig.txt`.
- `fatal`'s real C++ backend (the Python one is tested on the Pi 4: red
  LEDs, silence, stick report, exit code 3 not restarted).
- `str.lower()` of non-ASCII configparser keys (the port lowers ASCII only).
- The record buffer's thread: the tests run the WAV writing in place
  (`HandlerEnv::runWorker`); the port's own `std::thread` path is not run.
- The handlers with the real nebio: the sclang handshakes and the UDP port
  wait run against the fake clock.
