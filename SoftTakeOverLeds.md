# Soft takeover of the LEDs: design

Status: design, not implemented (2026-10-18, branch `refactor_controlhandler`).
Builds on the LED ownership added for rawencoder (see `RawEncoder_design.md`).

## Goal

Nebulae (Python), sclang, Pure Data, etc. can each **temporarily take over** one or more LEDs
to show something, for example that something went wrong. When they let go, the LED shows
exactly what it would have shown without the takeover. Nobody has to save or restore
anyone else's colours.

## Layers

Every LED has three layers in nebio. Each party writes only to its own layer. nebio shows
the top layer that is active.

| Layer | Who writes it | Active when |
|---|---|---|
| 3. Takeover | Anyone: nebulae, sclang, PD | Claimed, until released or the timeout runs out |
| 2. Owner | sclang (rawencoder), later PD | The encoder is raw (`nebio_encoder_set_raw`) |
| 1. Base | nebulae (`ui.py`, `nebio_led_set_rgb` / `nebio_led_set_button`) | Always (the bottom layer) |

On top of all three is the existing boot/loading animation (`nebio_led_animation`). It
stays as it is: it is drawn over everything while it runs.

### Rules

- **Every layer keeps its own buffer.** Writing to a layer that isn't shown is allowed and
  is remembered. When the layer above goes away, the layer below appears at once with its
  current value, never an old one.
- **The base layer is always written.** Today `Leds::setRgb()` is ignored while sclang owns
  the LED (`scOwned_`). With layers, Python's value is always stored in the base buffer and
  just not shown. This also fixes LEDs that freeze when ownership goes back to Python
  (e.g. the pitch LEDs in `secondary controls` with a pitch rawencoder).
- **Release or timeout** clears only the takeover layer. The owner or base layer below shows again.
- A takeover is per LED. A party can take one LED, a few, or all of them.

## Interface

### nebio C API (`nebio.h`)

```c
/* Claimer: who takes the LED (used for priority and release). */
#define NEBIO_LED_BY_NEBULAE 0
#define NEBIO_LED_BY_SC      1
#define NEBIO_LED_BY_PD      2

/* RGB LED (NEBIO_RGB_*): r g b 0..4095, shown at once (not staged).
 * ms > 0: released by itself after ms. */
NEBIO_API void nebio_led_takeover_rgb(int id, int by, double r, double g, double b, int ms);
/* Button LED (NEBIO_LED_*): brightness 0..1. */
NEBIO_API void nebio_led_takeover_button(int id, int by, double brightness, int ms);
/* Releases the takeover, only if `by` holds it. */
NEBIO_API void nebio_led_release(int id, int by);
/* Releases every LED `by` holds (e.g. when sclang reloads or quits). */
NEBIO_API void nebio_led_release_all(int by);
```

### Python (`nebio.py`)

```python
nebio.led_takeover("speed_pos", r, g, b, ms=2000)   # RGB LEDs, by nebulae
nebio.led_takeover("freeze", bright=1.0, ms=2000)   # button LEDs
nebio.led_release("speed_pos")
nebio.led_release_all()                             # everything nebulae holds
```

Names are the ones already in `nebio.py`: `RGB_LEDS` (`pitch_pos`, `pitch_neg`, `speed_pos`,
`speed_neg`) and `BUTTON_LEDS` (`record`, `next`, `source`, `freeze`, `reset`).

### sclang → nebio (OSC, port 3011)

Same pattern as `/sc/led/<led>`:

| Address | Args | Meaning |
|---|---|---|
| `/sc/led/<led>/takeover` | `i` r, `i` g, `i` b, `i` ms (optional) | Takes an RGB LED over |
| `/sc/led/<led>/takeover` | `f` brightness, `i` ms (optional) | Takes a button LED over |
| `/sc/led/<led>/release` | none | Lets it go |

```supercollider
NebInterface.ledTakeover(\speed_pos, 4095, 0, 0, 2000);   // red for 2 s
NebInterface.ledRelease(\speed_pos);
```

When a new patch is loaded, nebio releases everything sclang holds, so an LED can't stay
taken over by a patch that's gone. This goes with `nebio_led_clear_sc()` (called from
`SCControlHandler.setConfig()`). The `/sc/up` handshake (`nebio_sc_set_synth_down`) is not changed.

### Pure Data

PD talks to Python over the socket on port 3000, not OSC to nebio. Its path is designed when
PD gets rawencoder; the nebio layer is the same (`by = NEBIO_LED_BY_PD`).

## Implementation sketch (nebio, `leds.cpp`)

- `base_[16]` (today's `staged_`/`committed_`), `owner_[4][3]` (today's `scRgb_`/`scOwned_`),
  `take_[16]` + `takeBy_[16]` + `takeUntil_[16]` (ms, 0 = no timeout) per PWM channel group.
- The LED thread builds the output per LED: animation → takeover → owner → base, the first
  active one wins. Timeouts are checked in the same loop (it already reads the clock for
  the animation).
- `setRgb()` no longer returns early while owned: it writes the base buffer only.
- The reset LED (GPIO PWM, `resetDuty`) gets the same takeover and release.

## Open decisions

1. **Two claims on the same LED at once.** Proposal: nebulae always wins (it shows system
   errors); otherwise the last claim wins, and releasing it reveals the layer below
   (no stack of claims).
2. **Is the timeout required?** Proposal: yes for sclang and PD, so a crashed patch can never
   leave an LED stuck. Optional for nebulae.
3. **Which LEDs?** Proposal: all of them: the four encoder RGB LEDs, the button LEDs and the
   reset LED.
