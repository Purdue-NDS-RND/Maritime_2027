# RGB-D buoy scenarios

`one.json`, `gate.json`, `multi.json`, and `repeated_red.json` are the editable
source of truth for the RGB-D test worlds. Each buoy has a unique, stable entity
name, a category marker ID, a nominal pose, and optional symmetric jitter
limits. Marker IDs may repeat: `repeated_red.json` contains two separate red
entities that both use marker ID 1. Launch the nominal layout with
`SCENARIO=gate make run`, or a reproducible randomized layout with
`SCENARIO=gate BUOY_SEED=42 make run`.

The renderer validates entity names, marker IDs, test-area bounds, and
separation, then writes the untracked world and versioned entity-roster manifest
under `logs/generated-worlds/`. The fixed marker/category mapping is 0=white,
1=red, 2=green, and 3=blue.
