# Vendored AudreyTouch engine

Unchanged copies of the files `audrey` (../main.cc) needs, nothing else:

| Folder | From | Commit | Licence |
|---|---|---|---|
| `audrey/` | https://github.com/Synthux-Academy/AudreyTouch (`Source/`, the sound engine only) | 80e097e09fd1662a69707043f56eddcce9b8e1e0 (2026-07-30) | MIT (`audrey/LICENSE`, credits in `audrey/CREDITS.md`) |
| `daisysp/` | https://github.com/electro-smith/DaisySP (AudreyTouch's submodule commit) | 599511b740f8f3a9b8db72a0642aa45b8a23c3a3 (2025-05-28) | MIT (`daisysp/LICENSE`) |
| `daisysp-lgpl/` | https://github.com/electro-smith/DaisySP-LGPL (DaisySP's submodule commit): `ReverbSc`, `Tone` | c89d380c62620d6fee9105c5035e081c9b7ea843 (2023-12-21) | LGPL-2.1 (`daisysp-lgpl/LICENSE`) |

Not taken: the touch pads, switches, MIDI and the Daisy hardware (`FeedbackSynthControls`,
`simple-daisy-touch.h`, libDaisy). `../main.cc` does their job with JACK and OSC, with the same
parameter curves as `FeedbackSynthControls.cpp`.

`../shim/` replaces three Daisy-only headers without editing the copies: `daisysp.h` (only the
DaisySP parts used, instead of all of DaisySP), `memory/sdram_alloc.h` (the Daisy's SDRAM pool is
ordinary memory here) and the 32-bit ARM headers `dev/sdram.h`, `arm_math.h` (empty).

Copied rather than fetched or patched at build time, so the build works offline and nothing
upstream can change it. To update: copy the same files from newer commits and change the commits
above. The list is what `g++ -MM` reports for main.cc and the .cpp files.

The LGPL parts are shipped as source with their licence, so anyone can change and rebuild them
together with the rest (`../build.sh`).
