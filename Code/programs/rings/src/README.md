# Vendored Rings DSP

Unchanged copies of the files `miRings` (../main.cc) needs, nothing else:

| Folder | From | Commit |
|---|---|---|
| `rings/` | https://github.com/pichenettes/eurorack (`rings/dsp`, `rings/resources.*`) | f4cfa7697095a28d292bff758beb51deb49b5a86 (2026-10-12) |
| `stmlib/` | https://github.com/pichenettes/stmlib (the eurorack submodule's commit) | e3bd7c9cc00e4364166f9905c0509b6ffd0535ec (2023-05-30) |

Code by Emilie Gillet, MIT License (`LICENSE`, also in every file's header).

Copied rather than fetched or patched at build time, so the build works offline and
nothing upstream can change it. To update: copy the same files from newer commits and
change the commits above. The list is what `g++ -MM` reports for main.cc and the .cc files.

Built with `-DTEST`: stmlib's portable code instead of the Cortex-M4 instructions.
