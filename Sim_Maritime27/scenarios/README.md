# RGB-D buoy scenarios

`one.json`, `gate.json`, and `multi.json` are the editable source of truth for
the RGB-D test worlds. Each buoy has a stable model name and marker ID, a
nominal pose, and optional symmetric jitter limits. Launch the nominal layout
with `SCENARIO=gate make run`, or a reproducible randomized layout with
`SCENARIO=gate BUOY_SEED=42 make run`.

The renderer validates IDs, test-area bounds, and separation, then writes the
untracked world and exact resolved pose manifest under `logs/generated-worlds/`.
