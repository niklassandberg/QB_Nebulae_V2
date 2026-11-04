# Programs bank

Any program that makes sound through JACK and listens for OSC can be a
Nebulae instrument. It is chosen in the instr selector like the Csound, SC
and Pd instruments: the programs page comes after Pure Data, before the
config page, and has both speed LEDs dark. While a program plays, the speed
LEDs stay dark too (unless the program gives speed pages).

The programs are not part of the firmware: like the SuperCollider patches,
they come from the USB stick. This folder holds one folder per program, with
what goes on the stick (the program and its `.prog`) and its source.

## The .prog file

A text file next to the program, e.g. `miRings.prog`. Only the lines between
`nebconfigbegin` and `nebconfigend` count; text around them is free.

```
nebconfigbegin
run,miRings
oscport,3020
kernel,normal
blocksize,128
osc:blend,/rings/structure,0,1
osc:overlap,/rings/model,0,11,int
nebconfigend
```

| Entry | Meaning |
|---|---|
| `run,<program>` | What to start. A bare name is in `/home/alarm/prog/` (copied from the USB stick together with the `.prog`). `.sh` runs with `sh`, `.py` with `python3`, anything else as a binary. |
| `oscport,<port>` | The UDP port the program listens on (127.0.0.1), default 3020. |
| `osc:<control>,<path>,<min>,<max>[,<curve>]` | Control `<control>` is sent to `<path>` as one float, scaled from 0..1 to min..max. Curve `lin` (default), `exp` (min and max > 0) or `int` (rounded). min > max turns the control around. One line per control; no comment after an entry. |
| `kernel`, `blocksize`, `-n`, `-r` | As for .scd/.pd: kernel, JACK period, periods, sample rate. |

Controls: `pitch speed start size blend density overlap window` (0..1, knob and
CV), `reset freeze record source file` (buttons and gates, 0/1; `file` counts
up), and in secondary controls the same names with `_alt`. Only bound controls
are sent: when a value changes, and every value once a second. Button modes
as for the other banks, e.g. `reset,momentary,rising` (a gate: 1 while held).

## Encoder pages (more parameters than knobs)

The speed and pitch encoders can have pages, as `Supercollider/Chompi/chompi.scd`:

```
page:pitch:note,/audrey/note,16,76,lin,0.4      page:<encoder>:<name>,<path>,<min>,<max>[,curve[,default 0..1]]
page:pitch:shape,/audrey/shape,0,1
cv:pitch,note                                    the page the encoder's CV goes to at first (or none)
```

- Click = next page, turn = the value of the page shown (0..1, sent scaled like
  `osc:`). Holding speed 1.5 s still opens the instr selector.
- The two LEDs: colour = page (1 white, 2 cyan/blue, 3 yellow/red, 4 green,
  5 pink/magenta), only the left LED = minimum, only the right = maximum.
- The encoder's CV input (speed CV, pitch CV) is added to one page. To choose
  it: **hold file + reset, turn pitch or speed** (its LEDs blink the colour of
  the chosen page, dim white = nowhere), **release both**. While both are held,
  file and reset do nothing else.
- The values and CV targets are saved per program
  next to the `.prog` (`/home/alarm/prog/<name>.state`, 1 s after a change; a
  firmware update and the USB stick leave it) and come back at the next
  load. The page always starts at page 1.
- A pitch page over 60 semitones keeps the pitch CV at 1V/oct.
- An encoder with pages is not sent as the control `speed`/`pitch`.

A change of the bindings is a change of the text: no compile.

## What a program must do

- Start with `--port <port> <path of the .prog>` (it may ignore both).
- Register with jackd and connect its own ports, e.g. to `system:capture_1`
  and `system:playback_1/2`. The jackd process runs when the program starts,
  but may need a moment before it takes clients: retry for a few seconds
  (miRings: 10 s).
- Listen for OSC floats on 127.0.0.1:<port>.
- Stop on SIGTERM (after 4 s it gets SIGKILL).

## On the USB stick

Everything goes in the root of the stick, like the other instruments: the
`.prog` and the program it runs (`miRings.prog` + `miRings`). A program with a
bare name in `run,` that is on the stick is copied with its .prog to
`/home/alarm/prog/` and made executable. Like the other banks, that folder then
holds exactly the stick's programs.

## The programs here

| Folder | For the USB stick | Source | Build (on the Pi) |
|---|---|---|---|
| `miRings/` | `miRings`, `miRings.prog` | `source/`: Mutable Instruments Rings DSP (vendored, MIT) | `sh Programs/miRings/source/build.sh` |
| `audrey/` | `audrey`, `audrey.prog` | `source/`: AudreyTouch's engine (Infrasonic Audio / Synthux Academy, MIT); DaisySP (MIT); ReverbSc and Tone from DaisySP-LGPL (LGPL-2.1) | `sh Programs/audrey/source/build.sh` |
| `Proxy/` | `proxy`, `proxy.prog` | `source/main.cc`: the template for your own C/C++ program: input to output, one OSC value (`/proxy/level` on blend). Copy the folder, rename, put your sound in `process()` | `sh Programs/Proxy/source/build.sh` |

The build puts the binary next to its `.prog`. The binaries are built on the Pi
(aarch64), so they run on the Nebulae's aarch64 image only.
