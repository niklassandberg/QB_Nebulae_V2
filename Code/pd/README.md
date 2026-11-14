# Pd patches on the Nebulae

Nebulae sends the controls to the patch as OSC on UDP port 3000, one message
per control: `/start 0.25`. The patch receives them with

```
[netreceive -u -b 3000]
|
[oscparse]
|
[list trim]
|
[route start size density ...]
```

so `/start 0.25` arrives as `start 0.25`. Start from `template.pd`.

Nebulae waits until the patch listens on port 3000, sends every value once,
then only the values that change. A patch's own `[loadbang]` values come
first: Pd reads Nebulae's messages once the patch has loaded.

## Older patches

Patches written for the old link, a TCP `[netreceive 3000]`, keep working:
when one is loaded, Nebulae writes a converted copy next to it
(`.<name>.osc.pd`, hidden) and starts that one. The original is not changed.
Only that `[netreceive 3000]` is converted; any other `[netreceive]` or
`[netsend]` in the patch stays as it is.

A patch is started unconverted, and gets no values, when the conversion is
not safe: more than one `[netreceive 3000]`, something connected into it, or
its connection-count outlet in use. The log says which.
