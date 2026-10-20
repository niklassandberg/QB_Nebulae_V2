# rawencoder: design

Status: implemented, not yet tested on the device (2026-10-17, branch `refactor_controlhandler`, uncommitted).

## Goal

A SuperCollider patch can declare `speed` and/or `pitch` as `rawencoder` in its nebconfig block.
For those encoders:

- nebio sends the raw encoder steps (-1/+1) and the click (press/release) straight to sclang.
- sclang decides the value and drives the encoder's two RGB LEDs, through nebio.
- sclang also **saves** the value itself, together with any other value the patch owns.
  Python and nebio take no part in saving.
- The ControlHandler holds **no value** for the control. It only switches the routing on and off.
- Encoders that aren't declared `rawencoder` stay `hybrid`, exactly as today.

Buttons (`freeze`, `reset`, ...) will get the same treatment later (`/neb/btn/<name>`). In the
.scd that will be declared for all buttons at once. They aren't covered here.

## Declaring it in the .scd

```
/*
nebconfigbegin
ksmps,64
sr,48000
pitch,rawencoder
speed,rawencoder
freeze,latching,rising
...
nebconfigend
*/
```

- `InstrParser` already turns this into `configData['pitch'] == ['rawencoder']`. Nothing changes in the parser.
- The value is compared without case, so `rawEncoder` also works.
- Only `speed` and `pitch` accept it.
  - `speed_alt` (input level) is never raw: Python sets it and its LEDs in `secondary controls` as today.
  - `pitch_alt`: when pitch is a rawencoder, ui.py doesn't set `pitch_alt` or the pitch LEDs in
    `secondary controls`. TODO, next version: `pitch_alt` can be declared raw (sclang sets it).
- The Csound and Pure Data banks ignore it (always `hybrid`).

## Who owns what

| Thing | Owner |
|---|---|
| Encoder steps and click, while raw is active | nebio, which sends them to sclang |
| The control's value | sclang |
| Saving and loading the value (and the patch's other values) | sclang (`NebInterface`), its own file per patch |
| The encoder's LEDs (`<name>_pos`, `<name>_neg`), while raw is active | sclang, through nebio |
| When raw is active | Python (control mode) |

**Raw is active only in `supercollider` mode, once the patch is loaded.** In `secondary controls`
and `instr selector`, Python takes the encoders and LEDs back, because it needs them for input
level, restoring defaults and moving through the patch list. Those modes behave exactly as today.

The `/sc/up` handshake (`NebInterface.ready`, `/neb/hasbeenloaded`, `synthIsUpStatus()`) is
**not changed**.

## OSC messages

Ports are unchanged: Python/nebio → sclang on **3010**, sclang → nebio on **3011**.
The existing `/neb/<name> value` messages for the other controls are also unchanged.

### nebio → sclang (port 3010)

| Address | Args | When |
|---|---|---|
| `/neb/enc/<name>` | `i` steps | Encoder turned. Sent from nebio's input thread, only when steps != 0. Normally ±1, can be ±n if turned fast (steps added up since the last scan). As ui.py does for a hybrid encoder, the first steps after a direction change are dropped, so a single glitch step backwards never arrives. |
| `/neb/enc/<name>/click` | `i` 1 = pressed, 0 = released | Encoder click edge (debounced, as today). Sent for **both** encoders in `supercollider` mode, raw or hybrid (for a hybrid encoder Python still handles the click too). If raw is switched off while the click is held, nebio sends the `0` itself, so sclang always gets a press followed by a release. |

`<name>` is `speed` or `pitch`.

**No mode messages.** This follows Qu-bit's pattern: sclang is never told which mode
Nebulae is in, it only sees which addresses arrive. In `supercollider` mode `/neb/enc/...`
arrives; in `secondary controls` it stops and `/neb/speed_alt` / `/neb/pitch_alt` arrive
exactly as today; in `instr selector` nothing arrives. When Python gives the encoder back,
nebio shows sclang's last LED values again, so sclang never needs to resend them.

### sclang → nebio (port 3011)

| Address | Args | Meaning |
|---|---|---|
| `/sc/led/<led>` | `i` r, `i` g, `i` b (0–4095, same scale as `libDriver.Color`) | Sets one LED. `<led>` is `speed_pos`, `speed_neg`, `pitch_pos` or `pitch_neg`. Always remembered by nebio, but only shown while that encoder is raw (sclang owns the LED). Values are clamped to 0–4095. |
| `/sc/clip` | none | The audio input clipped. Sent by NebInterface's clip detector (started in `init`) for every 128 samples (2.7 ms at 48 kHz) that clipped, like Csound's check per block. nebio counts them (`nebio_sc_clip_count`); in `secondary controls` ui.py makes all four encoder LEDs red while the reports come (8 ms after each), so they flicker with the signal. Csound does the same with its `inclip` channel (`conductor.py`). |

There are no save or load messages: sclang reads and writes its own file.

## Saving (sclang, NebInterface)

- One file per patch: `Code/config/sc/<patch>.scstate` (`NebInterface.statePath`), written with
  SC's `writeArchive`, so it can hold any archivable SC object, not only numbers.
- **Not** next to the .scd: `fileloader.copyType()` runs `rm /home/alarm/sc/*` on every USB load.
- `<patch>` comes from the path in `/neb/loadScFile`. When a patch isn't loaded by Nebulae
  (e.g. run on a PC), nothing is read or written.
- Read in `NebInterface.init`, so values are there before the patch builds its synths.
- Written by sclang itself:
  - `saveDelay` (1 s) after the last `statePut`, so turning a knob doesn't write the SD card for every step;
  - at once when the next patch is loaded (before `prSoftReset` clears the clocks) and on `/neb/quit`.
- Today the root filesystem stays read-write all the time (`neb_globals.remount_fs = False`), so
  sclang and Python never clash. If `remount_fs` is ever switched on, `mountfs.sh` needs a
  counter with a lock (rw +1, ro −1, read-only only at 0) before both processes can use it.

```supercollider
~cutoff = NebInterface.stateAt(\cutoff, 1000);   // saved value, or the default
NebInterface.statePut(\cutoff, ~cutoff);         // saved 1 s later
```

### Settings: saved numbers with their own bus

For values that synths read (e.g. the pages of a speed rawencoder), `initSettings` hides the
state + bus code. Call it after `NebInterface.init`, before the SynthDefs that read the settings.

```supercollider
NebInterface.initSettings([
    [\speed,  1.0],            // name, default
    [\reverb, 0.0],
    [\tape,   0.0]
]);

speed = NebSetting.kr(\speed);                        // in a SynthDef
NebInterface.setSetting(\speed, v);                   // sets the bus, saved 1 s later
NebInterface.setting(\speed);                         // current value
```

- NebInterface knows no ranges: the patch clips its values itself.
- A saved value is used only if it's a number. Otherwise (first time, a new
  setting, a value from another version of the patch) the default is used. Saved settings that
  aren't declared any more are dropped.
- A patch that never calls `initSettings` keeps the saved settings in the file untouched.
- `NebSetting.kr` of an undeclared name throws when the SynthDef is built.

File layout (`writeArchive`), version 1:

```
IdentityDictionary[
    \version  -> 1,
    \state    -> IdentityDictionary[ ...statePut keys... ],
    \settings -> IdentityDictionary[ \speed -> 1.0, \reverb -> 0.3, ... ]
]
```

A file without `\version` is version 0 (the state dictionary alone, as written before settings
existed). It's read as the state, and its numbers can become settings, so old values carry over.
A file with an unknown version is ignored (warning) and the defaults are used.

## Sequences

### Load an SC patch (also when `SCControlHandler` is reused)

```
Nebulae.start_supercollider(patch, fromSC)
  parse .scd -> configData                          (on every load, also on reuse)
  new SCControlHandler(... configData)            or, when reused:
  c_handle.setConfig(sc_parser)        (new and reused handler)
      raw off, forget sclang's LED colours
      speed/pitch -> rawencoder or hybrid (swapped in place)
  enterSuperColliderMode()
  loadScSynth(path)        -> /neb/loadScFile ... /sc/up          (unchanged)
      sclang: saves the old patch's values, sets the patch name,
              NebInterface.init reads the new patch's values
  c_handle.startRawEncoders()
      raw on -> nebio routes steps/click, LEDs owned by sclang
```

### Turning a raw encoder (Python not involved)

```
nebio input thread: steps -1  -> /neb/enc/speed -1
sclang: onStep.(-1)   the patch does what it wants, e.g. its own value,
        a bus, statePut(...), NebInterface.led(\speed_pos, 4095, 0, 0)
```

### Leaving supercollider mode (secondary / instr selector / reload)

```
enterSecondaryMode() / enterInstrSelMode() / run_supercollider() before the next patch
  setRawActive(False)     nebio: sends click 0 if the click is held,
                                 steps go back to encoder_steps() for ui.py,
                                 LEDs go back to Python
```

`enterSuperColliderMode()` switches raw on again (once the patch is loaded). nebio then
shows sclang's last LED values again (it keeps them in a separate buffer).

## Implementation

### nebio (C++)

C API (`nebio.h`), with wrappers in `nebio.py` that take the encoder name (`"speed"`/`"pitch"`):

```c
/* id from nebio_encoder_id: 0 = pitch, 1 = speed */
NEBIO_API void nebio_encoder_set_raw(int id, int on);   /* routing + LED ownership */
NEBIO_API int  nebio_encoder_raw(int id);
NEBIO_API void nebio_encoder_set_click(int id, int on); /* click only, for hybrid encoders */
NEBIO_API void nebio_led_clear_sc(void);                /* forget sclang's LED colours */
```

- **inputs.cpp:** each encoder has a raw state. While raw, the input thread sends the steps
  (`/neb/enc/<name>`) and debounced click edges (`/neb/enc/<name>/click`) itself, and
  `encoderSteps()` returns 0. Encoder ↔ click pin: pitch 17/27 ↔ 22, speed 6/13 ↔ 26.
  Switching raw on throws away old steps; a click held at that moment is ignored until it is
  released. Switching raw off while the click is held sends `click 0`.
- **links.cpp:** listener method for `/sc/led/<led>` (accepts f/i/d), passed to leds.
  Encoder messages bypass the "changed" cache.
- **leds.cpp:** sclang's own colour for each of the four encoder LEDs. It is shown while sclang
  owns the LED, and Python's `setRgb()` is ignored for it. Taking ownership shows the remembered
  colour, or dark if sclang has sent none.

### Python

- **control.py:** `RawEncoderData`. It keeps no value; `setActive()` switches nebio's routing.
  `ControlChannel(source="rawencoder")` creates it.
- **controlhandler.py:** only `isRaw(name)`, which always returns `False` in the base class.
  The speed/pitch channel lines are unchanged.
- **controlhandlerSC.py:**
  - `__init__` builds `encoders[name]["hybrid"]` (the channel ControlHandler built) and
    `encoders[name]["rawencoder"]` once for speed and pitch; both are reused for every patch.
  - `setConfig(scParser)`: looks up `encoders[name][scParser.getType(name)]`. The channel is **replaced in
    place** in `self.channels` (`resistNormalSettings()` pairs `channels[i]` with
    `altchannels[i]`). It runs in `__init__` and, when the handler is reused, from `start_supercollider()`.
  - `startRawEncoders()`: after `loadScSynth()`, switches raw on if the mode is `supercollider`.
  - `enterSuperColliderMode()` switches raw on, but only once the patch is loaded.
  - `enterSecondaryMode()` / `enterInstrSelMode()` / `closeSockets()`: raw off.
  - `updateAll()` / `sendScOscMessages()` skip raw channels (no `/neb/speed` for them).
- **nebulae.py:** the .scd is parsed on every SC load (also on reuse). `startRawEncoders()` runs
  after `loadScSynth()`, and `run_supercollider()` switches raw off before the next patch.
- **ui.py:** in `supercollider` mode, for a declared raw encoder, `set_speed_amount()` /
  `set_pitch_amount()` and the LED functions are skipped. It checks "declared", not "raw on right
  now", because a long press switches raw off in the middle of `update_speed()`.
  The speed long press (1.5 s → instr selector) still works.

### SuperCollider (NebInterface.sc)

```supercollider
// After NebInterface.init.
NebInterface.rawEncoder(\speed,
    onStep:  { |steps| ... },       // -1 / 1 (-n / n if turned faster than nebio scans)
    onClick: { |state| ... });      // 1 pressed, 0 released
NebInterface.led(\speed_pos, 4095, 0, 0);

// Any encoder, raw or hybrid: only the press/release.
NebInterface.encoderClick(\pitch, { |state| ... });   // 1 pressed, 0 released
```

- `rawEncoder` only passes the steps and the click on. It keeps no value, sets no bus and saves
  nothing: the patch does that itself, if it wants (its own variables, `NebInterface.bus(\speed).set(...)`,
  `stateAt` / `statePut`, `led`).
- `prSoftReset` already frees all OSCdefs, so a new patch starts clean.
- The existing lines in `loadScFile` and `quit` are unchanged; lines are only added there
  (save the old patch's values, set the patch name).

## Decisions

1. `/neb/enc/<name>` is sent straight from nebio's input thread, with no queue in between.
   sclang and scsynth have to cope with the rate.
2. Buttons will follow the same pattern (`/neb/btn/<name>`, `/sc/led/<name>`). In the .scd,
   that will be declared for all buttons at once. This is designed later, as its own step.
3. sclang saves the patch's values itself. Python and nebio only route; no save/load over OSC.
4. The `/sc/up` handshake is not changed.
