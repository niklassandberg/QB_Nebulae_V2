# Pd patches on the Nebulae

Nebulae sends the controls to the patch over TCP, as Pd messages
(`start 0.25;`), into `[netreceive 3000]`. Start from `template.pd`.

## Telling Nebulae the patch is ready

Until the patch says it is ready, Nebulae sends every value once a second,
with the message `nebready`. The patch answers `ready` back over the same
connection by sending `[send ready(` into its `[netreceive 3000]`:

```
[netreceive 3000]
|
[route nebready]
|              \
[send ready(    (all other messages, as before)
|
(back into [netreceive 3000])
```

After the answer, Nebulae sends every value once more, then only the values
that change. If the connection fails, it asks again.

A patch that sets itself up slowly (loading samples, its own `[loadbang]`
values) can hold the answer back with a `[spigot]` until it is done, so
Nebulae's values arrive after its own and are not overwritten.

All patches in this repository have the answer. A patch without it keeps
working: it gets every value once a second.
