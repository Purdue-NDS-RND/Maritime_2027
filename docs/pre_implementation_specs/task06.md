# Task 06: Complete the Simulation Adapter Boundary

**Goal:** Make the relocated Simulation Adapter own MAVROS, the normalized
camera boundary, and source diagnostics while removing evaluation behavior from
normal Adapter runtime.

**Source:** `Things_To_Fix_Before_Implementation.md`, Simulation Adapter items
in section 2 and all of sections 3 and 4.

**Prerequisites:** Tasks 01, 02, 03, 04, and 05 approved. May run in parallel
with Task 07.

**Required inputs:**
`docs/contracts/mavros_adapter_contract.md`,
`docs/contracts/camera_adapter_contract.md`,
`docs/contracts/scenario_entity_contract.md`, and the Task 04 and Task 05
handoffs and commits.

**Exclusive write scope:** `Adapter/simulation/**` and a dedicated runnable
evaluation environment under `Simulation/tests/**`. Do not edit shared Compose,
Simulation runtime scripts, Makefiles, autonomy, root tests, or operational
documentation.

## Required Work

- Add the contract-controlled MAVROS launch/configuration, `mavros`,
  `mavros-extras`, `mavros_msgs`, GeographicLib tools, and dataset installation
  to the Simulation Adapter image.
- Own `FCU_URL` at the Adapter boundary and retain `udp://:14552@` for SITL.
- Start MAVROS and all required Gazebo/camera bridges through one supervised
  bringup whose failure is visible if a required child exits.
- Move FCU connection evidence into Adapter diagnostics.
- Remap public camera outputs to `/sensors/camera_0/...`; normalize public
  frames to `camera_0_link` and `camera_0_optical_frame` while private Gazebo
  identifiers may remain unchanged.
- Verify color, registered depth, and `CameraInfo` compatibility and publish the
  configured `base_link -> camera_0_link -> camera_0_optical_frame` transforms.
- Implement the approved clock, `use_sim_time`, timestamp, staleness, and
  mismatch diagnostics from Task 02.
- Move sensor and command-capable smoke clients out of Adapter runtime. Remove
  OpenCV/ArUco, manifest, and truth-consumer dependencies unless a remaining
  runtime producer demonstrably requires one.
- Create a simulation-only evaluation package or image under `Simulation/tests/`
  with the ROS, OpenCV/ArUco, MAVROS message, manifest, and truth-consumer
  dependencies needed to run the moved clients. Give it an explicit command and
  hardware-exclusion guard; Task 09 will wire it into Compose and Make targets.
- Replace fixed truth bridges with a solution driven by Task 05's entity roster.
  Key evaluator data by entity identity and keep truth exclusively under
  `/blueboat/ground_truth/...`.

## Acceptance

- A clean image inspection proves MAVROS and GeographicLib datasets are in the
  Adapter and evaluator-only dependencies are absent from runtime.
- Static launch checks show exactly one MAVROS process and one source for each
  public camera/TF interface.
- Normal bringup launches no evaluator and no command-capable smoke client.
- The dedicated evaluation environment builds independently and its explicit
  help or dry-run command resolves both moved evaluator entry points.
- Focused Adapter tests verify generic topics/frames, registered RGB-D and
  calibration consistency, stale/missing-source diagnostics, scalable truth
  bridging, and child-failure propagation.
- Moved `mavros_smoke.py` retains bounded neutral-command and disarm cleanup and
  is explicitly guarded against hardware execution.

## Handoff

Provide Task 09 with exact Adapter and evaluation image entrypoints,
health/readiness commands, mounts, environment variables, exposed ROS
interfaces, and required Compose/Make wiring.
Provide Task 10 with assertions for truth isolation and evaluator safeguards.
