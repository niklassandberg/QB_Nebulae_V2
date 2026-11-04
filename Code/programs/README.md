# Programs bank

Any program that makes sound through JACK and listens for OSC can be a
Nebulae instrument. It is chosen in the instr selector like the Csound, SC
and Pd instruments: the programs page comes after Pure Data, before the
config page, and has both speed LEDs dark. While a program plays, the speed
LEDs stay dark too.

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
| `run,<program>` | What to start. A bare name is looked up in `/home/alarm/prog/` (copied from the USB stick), then in `Code/bin/` (shipped with the firmware). `.sh` runs with `sh`, `.py` with `python3`, anything else as a binary. |
| `oscport,<port>` | The UDP port the program listens on (127.0.0.1), default 3020. |
| `osc:<control>,<path>,<min>,<max>[,<curve>]` | Control `<control>` is sent to `<path>` as one float, scaled from 0..1 to min..max. Curve `lin` (default), `exp` (min and max > 0) or `int` (rounded). min > max turns the control around. One line per control; no comment after an entry. |
| `kernel`, `blocksize`, `-n`, `-r` | As for .scd/.pd: kernel, JACK period, periods, sample rate. |

Controls: `pitch speed start size blend density overlap window` (0..1, knob and
CV), `reset freeze record source file` (buttons and gates, 0/1; `file` counts
up), and in secondary controls the same names with `_alt`. Only bound controls
are sent: when a value changes, and every value once a second.

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
bare name in `run,` that is on the stick is copied with its .prog and made
executable. Without it on the stick, the firmware's `Code/bin/` one is used.

## Programs in the firmware

| Program | Source | Build |
|---|---|---|
| `miRings` | `rings/` (Mutable Instruments Rings DSP, vendored, MIT) | `sh Code/programs/rings/build.sh` on the Pi → `Code/bin/miRings` |
