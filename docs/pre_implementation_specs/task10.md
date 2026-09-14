# Task 10: Replace Boundary and Acceptance Tests

**Goal:** Make the automated suite assert the new ownership and public contracts
without preserving obsolete compatibility behavior.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 8.

**Prerequisites:** Task 09 integrated. Do not write tests against paths or
interfaces that have not landed.

**Exclusive write scope:** `tests/**` and test-only code under
`Simulation/tests/**`. Do not modify production packages, Compose, Makefiles,
runtime scripts, or documentation.

## Required Work

- Rewrite container-boundary assertions for Adapter-owned `FCU_URL`, MAVROS
  runtime/configuration/launch, GeographicLib, and FCU health, and prove autonomy
  owns none of them.
- Replace standalone-autonomy-with-`FCU_URL` expectations with mutually exclusive
  Simulation/Hardware Adapter deployment tests against the shared contracts.
- Update ROS boundary smoke for generic camera topics/frames, actual camera and
  MAVROS delivery to autonomy, and exclusion of truth from navigation inputs/TF.
- Prove autonomy images/packages exclude Gazebo, manifests/truth, ZED drivers,
  MAVROS launch/runtime, and environment transport settings.
- Cover configured camera rosters, `CameraInfo`-driven dimensions, encodings,
  depth units, registration, timestamp/frame compatibility, stale input, and
  missing-source diagnostics.
- Cover two visible same-category buoys with distinct truth entities and no
  entity IDs leaking to perception/autonomy.
- Test liveness, source readiness, FCU readiness, and application readiness as
  separate assertions.
- Keep `make mavros-smoke` simulation-only with bounded neutral-command and
  disarm cleanup.

## Acceptance

- Run `python3 -m unittest discover -s tests -v` successfully.
- Run focused renderer, camera, evaluator, and readiness tests successfully.
- Demonstrate at least one negative test for each prohibited ownership and
  readiness confusion.
- Search the active suite and remove obsolete assertions for legacy public
  camera names, flat Adapter paths, autonomy-owned `FCU_URL`, and
  autonomy-launched MAVROS. Assert that `ACTIVE_BUOY_IDS` and marker-ID entity
  rosters are absent from current runtime configuration.
- `git diff --check` passes.

## Handoff

List which checks are static, image-inspection, live-interface, or semantic
mission checks. Do not describe static or container-health results as live
acceptance.
