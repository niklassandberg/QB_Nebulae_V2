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
`nebconfigbegin` and `nebconfigend` count; text around them is free. Inside,
a line starting with `#` is a comment (a whole line only, not after an entry).

```
nebconfigbegin
# miRings on the stick
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
| `speedleds,playback` | The `osc:speed` value is a playback speed (1 = normal, negative = backward): the speed LEDs show it as the granular looper shows its speed (right = forward, left = backward; white 1/8, orange 1/4, yellow 1/2, blue 1, green 2, purple 4, bright on those speeds). Without it the speed LEDs stay dark (unless speed has pages). |

Controls: `pitch speed start size blend density overlap window` (0..1, knob and
CV), `reset freeze record source file` (buttons and gates, 0/1; `file` counts
up), and in secondary controls the same names with `_alt`. Only bound controls
are sent: every value once as soon as the program listens on its OSC port
(Nebulae waits for it), then when a value changes. Button modes
as for the other banks, e.g. `reset,momentary,rising` (a gate: 1 while held).

## Encoder pages (more parameters than knobs)

The speed and pitch encoders can have pages, as `Supercollider/Chompi/chompi.scd`:

```
page:pitch:note,/audrey/note,16,76,lin,0.4      page:<encoder>:<name>,<path>,<min>,<max>[,curve[,default 0..1[,step]]]
page:pitch:shape,/audrey/shape,0,1
cv:pitch,note                                    the page the encoder's CV goes to at first (or none)
```

- Click = next page, turn = the value of the page shown (0..1, sent scaled like
  `osc:`). Holding speed 1.5 s still opens the instr selector.
- `step`: how much of the range one encoder click moves. Default 0.01 (100
  clicks from min to max); smaller is finer: 0.002 = 500 clicks. As on pitch,
  turning faster accelerates (step × clicks³ per reading) and the first click
  after a change of direction is dropped; step 0.001 turns exactly like pitch.
  Held and turned: a jump of 0.2 per click, as pitch's octaves. Example, the
  note page in 0.1-semitone clicks over its 60 semitones:
  `page:pitch:note,/audrey/note,16,76,lin,0.4,0.00167`.
- The two LEDs show the value as pitch does (white → orange → yellow → blue →
  green → purple, the left LED below the middle, the right one above, a flash
  on each step), and the LED that stays dark there shows the page's colour,
  pulsing dimly: 2 red, 3 blue, 4 green, 5 pink (page 1 none, as the plain
  encoder).
- The encoder's CV input (speed CV, pitch CV) is added to one page. To choose
  it: **hold file + reset**, click pitch or speed to show the next page,
  **turn clockwise = CV on that page** (both LEDs white), **counter-clockwise
  = off** (dark, page 2+ pulsing in the page colour), **release both**. On
  turned on another page moves the CV there; all off = the CV goes nowhere.
  While both are held, file and reset do nothing else.
- The values and CV targets are saved per program
  next to the `.prog` (`/home/alarm/prog/<name>.pages`, 1 s after a change; a
  firmware update and the USB stick leave it) and come back at the next
  load. The page always starts at page 1.
- Before Nebulae restarts (Restart on the settings page) the program gets
  `/neb/save 1` on its port. Nebulae already saves everything it sends; a
  program that keeps values of its own can save them then, quickly: it is
  stopped right after.
- A pitch page over 60 semitones keeps the pitch CV at 1V/oct.
- An encoder with pages is not sent as the control `speed`/`pitch`.
- The same `page:`/`cv:` lines work in a SuperCollider `.scd` (read with
  `NebPage.kr(
ame)`, example `Supercollider/Pages/pages.scd`). Both banks use
  `Code/nebulae/controlhandlerEncoders.py`.

## Held buttons (more parameters on the encoders)

While a button is held, speed and pitch can set other values:

```
hold:record:speed:echo_cutoff,/audrey/echo_cutoff,100,8000,exp,0.4745
hold:record:pitch:echo_feedback,/audrey/echo_feedback,0,1.5,lin,0.5
```

`hold:<button>:<encoder>:<name>`, then the same fields as `page:` (path, min,
max, curve, default, step). Buttons: `record file reset freeze source`.

- While the button is down, the encoders show and change the button's values;
  turn and click as on the pages (several lines for one encoder are its
  pages, click = next). The LEDs show the value as on the pages, the dark LED
  pulses cyan. Released, the encoders show their own pages again, unchanged.
- The button is pressed only by a short press: released within half a
  second with no encoder turned. Such a button reacts when it is released (a
  latching, triggered or incremental button gets the falling edge). A
  momentary button is also on while it is down.
- A second layer on two buttons: `hold:record+file:<encoder>:<name>,...`.
  While record is held, pressing file switches to that layer (the dark LED
  pulses orange); releasing file goes back to record's layer, releasing
  record goes back to the pages. During that, file's own press does nothing
  (no tap, its LED stays dark) until it is released; file's gate still
  works. So file can stay `momentary` and follow fast gates.
- No CV on these values. Saved with the pages (`<name>.pages`, as
  `record:speed` and `record+file:speed`).
- Holding file + reset still chooses the CV targets.
- Works the same in a SuperCollider `.scd`.

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
| `TheLaboratory/` | `thelaboratory`, `thelaboratory.prog` | `source/`: The Laboratory, a 2-minute stereo record buffer looped like the granular looper's (record, reset, file + reset clears, start, speed -1..1), at 96 kHz / 128. The sound is in `looper.h` | `sh Programs/TheLaboratory/source/build.sh` |
| `Proxy/` | `proxy`, `proxy.prog` | `source/main.cc`: the template for your own C/C++ program: input to output, one OSC value (`/proxy/level` on blend). Copy the folder, rename, put your sound in `process()` | `sh Programs/Proxy/source/build.sh` |

The build puts the binary next to its `.prog`. The binaries are built on the Pi
(aarch64), so they run on the Nebulae's aarch64 image only.
