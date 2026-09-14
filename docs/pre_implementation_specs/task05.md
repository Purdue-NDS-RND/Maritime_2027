# Task 05: Scale Repeated-Category Scenarios and Align Assets

**Goal:** Make scenario generation and simulation assets support multiple
distinct buoys with the same category.

**Source:** `Things_To_Fix_Before_Implementation.md`, sections 5 and 6.

**Prerequisites:** Task 03 approved. May run in parallel with Task 04.

**Exclusive write scope:**

- `Simulation/scripts/render_scenario.py`
- `Simulation/scenarios/**`
- `Simulation/models/aruco_buoy_id0/**`
- `Simulation/models/aruco_buoy_id3/**`
- Scenario-specific fixtures under `Simulation/tests/`

Do not edit Adapter bridge files, runtime orchestration, Makefiles, root tests,
or documentation outside `Simulation/scenarios/README.md`.

## Required Work

- Require unique entity names while allowing repeated marker IDs.
- Generate model names and manifest records from entity identity rather than
  `buoy_<marker_id>`.
- Add a committed scenario with at least two distinct same-category buoys.
- Align marker 0 model material and description to white and marker 3 to blue.
- Add renderer/manifest tests proving repeated categories remain separate.
- Provide the generated entity roster needed by Task 06 for scalable truth
  bridging and entity-keyed evaluator storage.

## Acceptance

- The new scenario renders successfully and its SDF and manifest contain both
  same-category entities exactly once.
- Duplicate entity identities fail with an actionable error; repeated marker
  IDs succeed.
- Marker/category assertions pass for white, red, green, and blue.
- Existing `one`, `gate`, and `multi` scenarios continue to render.
- `cd Simulation && make validate` passes or any failure is demonstrated to be
  solely the not-yet-integrated Adapter relocation and recorded precisely.

## Handoff

Return the manifest schema/version and exact roster interface consumed by Task
06. Do not add entity IDs to autonomy-facing detection messages.

