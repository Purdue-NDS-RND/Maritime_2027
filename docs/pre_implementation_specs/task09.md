# Task 09: Integrate Deployment, Readiness, Persistence, and Shutdown

**Goal:** Perform the single-owner integration cutover so one selected Adapter
feeds autonomy through deterministic startup and shutdown behavior.

**Source:** `Things_To_Fix_Before_Implementation.md`, the cross-file portions of
sections 2–4 and all of section 7.

**Prerequisites:** Tasks 04–08 approved and their handoffs reviewed. Task 08 and
this task merge as one atomic cutover.

**Required inputs:** The reviewed commits and handoff blocks from Tasks 04–08,
all three files under `docs/contracts/`, and Task 06's Adapter/evaluation
entrypoint table.

**Exclusive write scope:**

- `Simulation/Makefile`
- `Simulation/container/compose*.yaml`
- `Simulation/scripts/run.sh`
- `Simulation/scripts/validate.sh`
- `Simulation/scripts/verify-rgbd.sh`
- `deployment/**`
- Cross-service startup wiring explicitly delegated by Tasks 06–08

Do not modify root acceptance tests or operational Markdown.

## Required Work

- Update all build contexts and paths for `Adapter/simulation/`; leave no active
  flat Adapter convention.
- Add deployment selection for exactly one of Simulation Adapter or Hardware
  Adapter and prevent duplicate publication of the public MAVROS/camera surface.
- Remove `FCU_URL` handoff to autonomy and configure it only on the selected
  Adapter. Ensure exactly one MAVROS instance can bind SITL UDP `14552`.
- Remove `ACTIVE_BUOY_IDS` and every marker-ID-based entity roster from
  `Simulation/scripts/run.sh`, Compose, and runtime handoffs. Supply the
  identity-preserving manifest/roster defined by Tasks 03 and 05.
- Wire Task 06's simulation-only evaluation image/package and update
  `sensor-smoke`, `mavros-smoke`, and RGB-D verification commands so evaluators
  are invoked explicitly, never during normal Adapter startup or on hardware.
- Implement the ordered launch chain: fresh scenario/manifest, advancing Gazebo
  simulation and vehicle, SITL MAVLink, selected Adapter sources and MAVROS,
  then the autonomy application.
- Gate every handoff on bounded semantic readiness with actionable error and log
  collection. Separate process liveness, camera/calibration readiness, FCU
  connection/telemetry, required state/TF freshness, and application readiness.
- Propagate required-process failures visibly and implement graceful cleanup for
  `make down`, Ctrl-C, startup failure, and verification exit.
- Preserve logs and SITL EEPROM/parameter state across ordinary restarts and
  retain `WIPE_PARAMS` for an explicit clean FCU state.
- Start every application run with empty observation/map state and record
  run/scenario/configuration identity with persisted logs.

## Acceptance

- Compose resolution and static validation pass for simulation and hardware
  selections; configurations selecting zero or two Adapters fail.
- Failure injection at each handoff yields the correct readiness category,
  bounded timeout, logs, and non-zero failure.
- Ordinary stop and failed startup leave no stack containers, orphan publishers,
  SITL/MAVProxy/Gazebo children, or occupied project ports.
- Restart preserves FCU parameter state and logs but not mapping-session state;
  `WIPE_PARAMS` creates a clean FCU state.
- No healthy service status is used as evidence for camera, FCU, or application
  semantic readiness unless the corresponding live probe passes.

## Handoff

Return a complete service/startup/shutdown table and exact resolved Compose
commands for Task 10. Preserve all runtime evidence for Task 12.
