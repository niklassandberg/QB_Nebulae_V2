# SuperCollider patches

A `.scd` patch starts with a nebconfig block inside a comment. sclang never sees the block:

```
/*
nebconfigbegin
blocksize,128
speed,rawencoder
freeze,latching,rising
nebconfigend
*/
```

The keys are the same as for every instrument (`Code/nebulae/nebconfig.py`). The speed and pitch encoders can each be one of three kinds:

| Kind | Declared with | Who handles the encoder |
|---|---|---|
| hybrid | nothing (the default) | Python. The patch gets `/neb/speed`. |
| pages | `page:` lines (see `Pages/pages.scd`, `Programs/README.md`) | Python: pages, LEDs and CV target. The patch reads `NebPage.kr(\name)`. |
| rawencoder | `speed,rawencoder` | The patch: its steps, click, value and LEDs. |

## rawencoder

A raw encoder only works in supercollider mode. In secondary controls and the instr selector, Python takes the encoder back.

```supercollider
NebInterface.rawEncoder(\speed,
    onStep:  { |steps| ... },     // -1 / 1, or -n / n when turned fast
    onClick: { |state| ... });    // 1 pressed, 0 released
NebInterface.led(\speed_pos, 4095, 0, 0);    // r, g, b 0..4095
NebInterface.encoderClick(\pitch, { |state| ... });   // any encoder, click only
```

OSC used underneath:
- From nebio to sclang (port 3010): `/neb/enc/<name> i` and `/neb/enc/<name>/click i`.
- From sclang to nebio (port 3011): `/sc/led/<speed|pitch>_<pos|neg> r g b`.

## Saved values

Each patch has its own file, `/home/alarm/sc/<patch>.state`, next to its `.scd`. It is written 1 s after the last change. A newer copy on the USB stick replaces it.

```supercollider
~cutoff = NebInterface.stateAt(\cutoff, 1000);   // saved value, or the default
NebInterface.statePut(\cutoff, ~cutoff);

NebInterface.initSettings([[\speed, 1.0], [\reverb, 0.0]]);  // after init, before the SynthDefs
NebSetting.kr(\speed);                  // in a SynthDef
NebInterface.setSetting(\speed, v);     // sets the bus and saves it
NebInterface.setting(\speed);
```

Python saves the encoder pages separately, in `<patch>.pages`.
