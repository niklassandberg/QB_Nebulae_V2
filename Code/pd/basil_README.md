# basil.pd: two-oscillator wavefolding synth voice

`basil.pd` is a Pure Data synth voice for the Nebulae's Pd bank. It makes its own
sound and does not use the audio inputs: two oscillators, a waveshaper,
cross-modulation, a wavefolder and hard sync. Think "West Coast" synth: bright,
buzzy and metallic when folded, tearing and vocal when synced.

It came with the original Nebulae V2 code (Stephen Hensley, 2019), written for
Terminal Tedium-style hardware that read its own ADC. It has since been adapted
to the Nebulae: the controls arrive from Nebulae over `netreceive 3000`, like
in `template.pd`.

## Install and play
1. Copy `basil.pd` to the USB stick, next to your other Pd patches.
2. Start the Nebulae with the stick in: the file loader copies it to `/home/alarm/pd/`.
3. Pick it in the instr selector, Pd bank.

## Controls

| Nebulae control | basil parameter | Range |
|---|---|---|
| **start** knob + CV | VCO 1 base pitch | MIDI note 0 - 118 (about 8 Hz - 7 kHz) |
| **overlap** knob + CV | VCO 2 base pitch | MIDI note 0 - 118 |
| **pitch** encoder + CV | transposes **both** VCOs, 1V/oct | 0.2 per octave; 0.6 = no shift |
| **size** knob + CV | waveshape amount | 0 - 1 |
| **density** knob + CV | cross-modulation between the VCOs | 0 - 0.5 |
| **window** knob + CV | mix between the oscillators | 0 - 2 |
| **blend** knob + CV | wavefold depth | 0 - 3 |
| **reset** button / gate | hard sync on / off (toggles on each press) | |

speed, freeze, record, file and source are not used.

### Pitch
- start and overlap set each oscillator's note freely (not quantised, they glide).
- The pitch input follows 1V/oct and moves both oscillators together, so the
  interval between them, and with it the sync and cross-mod timbre, stays the
  same over the keyboard. Play melodies from a sequencer into the pitch CV and
  set the timbre with start and overlap.
- The note is clipped to MIDI 0 - 127 after the transposition.

## The sound, step by step
1. **VCO 1 and VCO 2** (`pd saw~`): band-limited sawtooth waves. The saw is built
   from a table with a smooth half cycle of a square wave
   (`pd transition-table`, first and third harmonics only), which keeps aliasing low.
2. **Waveshaper** (`pd waveshape~`, size): bends the waveforms through cosine /
   tanh curves; from plain saw towards rounder or more complex shapes.
3. **Cross-modulation and mix** (`pd crossfade~`, density and window): the
   oscillators modulate each other and are mixed.
4. **Wavefolder** (`pd wavefolder~`, blend): when the signal goes past the limit
   it is folded back instead of clipped, which adds many bright harmonics. The
   more blend, the more folds.
5. **Hard sync** (reset): one oscillator restarts the other's cycle. The heard
   pitch stays, the timbre follows the interval between the two.

## Patch ideas
- **Sync sweep**: press reset (sync on), start low, slowly turn overlap up, or put
  an LFO / envelope on the overlap CV.
- **Folded bass**: start and overlap close together (slow beating), blend up a bit,
  envelope into blend CV for plucks.
- **Clangs and bells**: overlap at a non-musical interval from start, density up.
- **Melody**: sequencer into pitch CV; with sync on, the timbre stays the same on
  every note.

## For patch writers
- Nebulae sends `name value;` messages over TCP port 3000 (Code/nebulae/pdsender.py):
  knobs 0 - 1, pitch -0.3 - 1.3, buttons 0 / 1. Every value is sent when it
  changes, and all of them again once a second.
- basil turns the knobs into the 0 - 4095 values of the old Terminal Tedium ADC
  (`* 4095` -> `s adc0` ... `s adc5`), so the rest of the patch works as written:
  adc0 = start, adc1 = size, adc2 = density, adc3 = overlap, adc4 = window, adc5 = blend.
- reset goes through `change` and `sel 1`, so only a press toggles sync (the
  once-a-second resend doesn't).
