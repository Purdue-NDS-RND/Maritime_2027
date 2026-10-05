# Things to Fix Before Implementation

This checklist tracks migrations required to bring the current repository into
line with the [Low-Level Design](Low_Level_Design.md). It is ordered by
dependency: settle the shared contracts first, move runtime ownership second,
then replace tests and run end-to-end acceptance. None of the items below is
implemented merely because it appears in the design.

## Status reconciliation: 2026-10-04

The simulation foundation is reconciled against the
[final verification report](../Simulation/docs/PRE_IMPLEMENTATION_FINAL_VERIFICATION.md),
which separates source tests, clean dependency builds, live acceptance, and
lifecycle failure injection. The
[original integration report](../Simulation/docs/PRE_IMPLEMENTATION_MIGRATION_VERIFICATION.md),
[velocity benchmark report](../Simulation/docs/MAVROS_VELOCITY_BENCHMARK_VERIFICATION.md),
and [RGB-D transport report](../Simulation/docs/RGBD_TRANSPORT_VERIFICATION.md)
remain historical evidence; their earlier failures are not current acceptance
claims.

Checks apply to the Simulation Adapter, explicit evaluators, and approved
simulation-only bootstrap exception. MAVROS contract `2.0.0` replaces unsupported
parameter aliases with the actual pinned implementation's settings; the public
namespace, vehicle IDs, ports, and camera contract `1.0.0` remain unchanged.

Unchecked items below are deliberately deferred hardware or real application
work. The bootstrap publishes false mission readiness and has no command
capability. Receiving camera data and FCU diagnostics in that container does not
implement perception, vessel-state interpolation, mapping, or navigation.
Multifaceted items have been split so completed preparation is distinguishable
from those future consumers and deployment requirements.

## 1. Freeze the Adapter Contracts

### Common MAVROS Contract

- [x] Define one versioned MAVROS contract used by both the Simulation and
  Hardware Adapters: ROS distribution and MAVROS version, public `/mavros/...`
  namespace, enabled/disabled plugin lists, MAVLink protocol, source system ID,
  target system/component IDs, frame conventions, and time/timesync settings.
- [x] Put the shared values in one canonical configuration source, with only
  transport and environment-specific device settings overridden per Adapter.
- [x] Preserve or deliberately migrate the currently tested source system ID
  `255`, target `1/1`, MAVLink v2, root namespace, and disabled/selected TF
  behavior; do not let Simulation and Hardware defaults drift independently.
- [x] Define the public telemetry, command, service, acknowledgment, and
  connection-diagnostic surface that autonomy and the GCS may depend on.
- [x] Pin or otherwise control dependency changes closely enough that a rebuild
  cannot silently change MAVROS namespace or plugin behavior.

Required before moving MAVROS or writing consumers against its interface.
The versioned contract is [mavros_adapter_contract.md](contracts/mavros_adapter_contract.md);
canonical runtime settings now live in
`Adapter/simulation/ros_ws/src/blueboat_sim_bringup/config/mavros.yaml`.
The Simulation Adapter image pins exact MAVROS and MAVROS Extras versions.

### Common Camera Contract

- [x] Make each Adapter expose configured camera sources as
  `/sensors/camera_N/color/image_raw`,
  `/sensors/camera_N/depth/image_rect_raw`, and
  `/sensors/camera_N/color/camera_info`, with `camera_N_link` and
  `camera_N_optical_frame` frames. Internal Gazebo and vendor-driver names may
  remain private to their Adapter.
- [x] Specify accepted color encoding(s) and a canonical registered-depth
  encoding and unit. Evaluate and document `32FC1` metres as the initial common
  depth representation, including invalid-value semantics and any conversion
  required by a hardware driver.
- [x] Require depth to be registered to the color image and define which
  calibration, distortion model, dimensions, and optical frame apply to the
  pair. Preserve acquisition timestamps and define the RGB/depth timestamp
  matching tolerance.
- [x] Make the enabled camera roster explicit deployment configuration:
  `camera_0` in current simulation and `camera_0` plus `camera_1` on hardware.
  The hardware roster is a contract, not an implemented camera deployment.
- [ ] **Deferred real application:** autonomy launch must enumerate configured
  cameras rather than infer a fixed count or model name.
- [x] Make image consumers and acceptance tests derive dimensions and
  intrinsics from `CameraInfo`; retain 1280x720 only as the current simulated
  calibration, not as a shared autonomy constant.
- [x] Define Adapter startup behavior and diagnostics for missing images,
  missing/stale calibration, frame mismatches, unregistered depth, and
  incompatible timestamps.

Required before depth-based positioning and before adding the second physical
camera. Initial 2D perception may proceed only if it consumes the generic color
topic and preserves the incoming header.

### Scenario Entity and Category Contract

- [x] Give every scenario buoy an immutable, unique entity identity independent
  of `marker_id` and category; keep the ArUco mapping category-level:
  `0 = white`, `1 = red`, `2 = green`, `3 = blue`.
- [x] Define manifest fields and evaluation-topic naming from that entity
  identity so two physical buoys may use the same marker/category without
  colliding.
- [x] Replace comma-separated `ACTIVE_BUOY_IDS` and any other marker-ID roster
  where it is being used as an entity roster with an identity-preserving
  manifest or equivalent configuration.

Required before changing the renderer and truth bridge, because their generated
names and evaluator subscriptions must follow the same contract.

## 2. Move MAVROS Into the Selected Adapter

### Simulation Adapter

- [x] Move the current flat `Adapter/` simulation project to the target
  `Adapter/simulation/` layout before adding `Adapter/hardware/`. Update Docker
  build contexts, Compose extension paths, validation paths, Make targets, and
  documentation as one relocation; do not leave two active path conventions.
- [x] Move the MAVROS launch and shared configuration out of
  `autonomy/ros_ws/src/maritime_bringup/` and into Simulation Adapter bringup.
- [x] Install `mavros`, `mavros-extras`, `mavros_msgs`, GeographicLib tools, and
  required GeographicLib datasets in the Simulation Adapter image; verify the
  dataset-install step in a clean image build.
- [x] Move `FCU_URL` ownership from the autonomy service and `Simulation/scripts/run.sh`
  handoff to the Simulation Adapter. Keep SITL's dedicated output on UDP 14552
  and configure the Adapter endpoint as `udp://:14552@` unless the shared
  contract intentionally changes it.
- [x] Start camera/Gazebo bridges and MAVROS through one Simulation Adapter
  bringup chain, and make its process supervision fail visibly if either
  required child exits.
- [x] Move FCU connection checks into Adapter diagnostics and update Compose
  dependency/readiness ordering so autonomy starts against the selected Adapter,
  not directly against the simulator's health.

Required before removing MAVROS from autonomy. During the migration, ensure
only one MAVROS instance binds the SITL endpoint.

### Hardware Adapter

**Deferred from the pre-implementation simulation-foundation milestone (2026-09-15).**
The following items remain unchecked and are not a claim of vessel readiness.
Do not create placeholder hardware packages, transports, camera settings, or
evidence merely to satisfy this checklist. Resume this section only after the
target platform, capture topology, real FCU transport, and supportable signed
camera evidence have been selected.

- [ ] Create the Hardware Adapter workspace/container and implement the same
  MAVROS contract there, including MAVROS packages, GeographicLib datasets,
  launch/configuration, and FCU diagnostics.
- [ ] Supply the real FCU transport through Hardware Adapter configuration,
  covering the chosen serial or network URL, device mapping, permissions,
  reconnect behavior, and deployment-specific overrides without leaking those
  settings into autonomy.
- [ ] Integrate the two ZED X Mini sources and their calibrated mounting
  transforms behind the common camera contract; keep vendor packages and device
  access out of the shared autonomy image.
- [ ] Add deployment composition that selects exactly one Adapter and prevents
  Simulation and Hardware Adapters from publishing the same public interfaces
  simultaneously.

Required before claiming vessel deployment support. A standalone autonomy
Compose file with `FCU_URL` is not a Hardware Adapter implementation.

### Shared Autonomy Cleanup and Real Bringup

- [x] Remove the MAVROS runtime packages, GeographicLib installation, `FCU_URL`,
  vehicle launch wrapper, and MAVROS connection healthcheck from the autonomy
  image/package/Compose definition after the Adapter path is working. Retain
  `mavros_msgs` wherever autonomy code needs the public `/mavros/...` message or
  service definitions.
- [x] Keep autonomy dependent only on the public ROS message packages and
  interfaces it actually consumes; add automated checks excluding Gazebo,
  camera-driver, simulator-truth, and flight-controller-transport dependencies.
- [x] Give the autonomy container a real application process after removing its
  current MAVROS-only `CMD`. Prefer coordinating this cutover with the first
  perception/state/system launch so the service has meaningful work and a
  meaningful liveness check. For the explicitly simulation-only
  pre-implementation bootstrap exception, a named placeholder is permitted
  only with explicit simulation opt-in, no command capability, and mission
  readiness fixed false; do not use `sleep`, `tail`, or an unlabeled fake
  keepalive.
- [x] Keep shared `maritime_bringup` responsible for autonomy nodes and
  environment-neutral configuration only. Adapter startup must remain outside
  that launch tree.

Required as one coordinated cutover. Do not merge a state in which the autonomy
container immediately exits or appears healthy while running no autonomy work.

## 3. Isolate Evaluation From Runtime Adapters

- [x] Move `sensor_smoke.py` and the boat-commanding `mavros_smoke.py` out of
  `blueboat_sim_bringup` into `Simulation/tests/` or a dedicated
  simulation-evaluation package/image.
- [x] Remove OpenCV/ArUco, scenario-manifest, and truth-consumer dependencies
  from the Adapter runtime image unless a separate non-evaluation runtime
  function demonstrably needs them. The Adapter still needs the MAVROS runtime
  and its message definitions to expose the agreed vehicle interface.
- [x] Keep the Adapter limited to producing camera, clock, transform, MAVROS,
  and availability interfaces. Evaluators may subscribe to those outputs and
  `/blueboat/ground_truth/...`, but must not be launched as Adapter runtime
  responsibilities.
- [x] Ensure command-capable evaluators are invoked only by explicit simulation
  test commands, never by normal Adapter startup and never against hardware.
- [x] Preserve truth on evaluation-only topics and ensure no autonomy launch,
  package, parameter, manifest mount, or shared TF source consumes perfect boat
  or buoy pose.

Required before treating the Adapter as the production environment boundary
and before reusing its shape for hardware.

## 4. Normalize the Current Simulated Camera Boundary

- [x] Remap the current `/blueboat/camera/...` ROS outputs to the common
  `/sensors/camera_0/...` topics at the Simulation Adapter boundary. Gazebo may
  continue publishing `/blueboat/rgbd_camera/...` internally.
- [x] Replace public `zed2i_camera_link` and
  `zed2i_left_camera_optical_frame` headers/transforms with `camera_0_link` and
  `camera_0_optical_frame` while leaving any private Gazebo asset identifiers
  unchanged where renaming provides no interface benefit.
- [x] Update bridge YAML, static-transform launch, Adapter health/readiness
  diagnostics, perception remaps, evaluator subscriptions, and boundary tests
  in the same change so there is no mixed old/new public interface.
- [x] Verify RGB, registered depth, and `CameraInfo` carry compatible timestamps,
  dimensions, calibration, encoding, and the normalized optical frame. Verify
  the `base_link -> camera_0_link -> camera_0_optical_frame` transform using the
  configured simulated mount.
- [x] Resolve source camera and MAVROS clock behavior under uninterrupted
  simulation, including `use_sim_time`, timestamp origins, stale-data limits,
  and behavior at supported full launch/shutdown boundaries.
- [ ] **Deferred real state application:** implement and validate vessel-state
  interpolation and explicit camera/FCU clock correlation before combining
  images, depth, and vessel state. Source timesync telemetry is not that proof.

Required before autonomy depends on named camera transforms or combines images,
depth, and vessel state. This is partly a known migration and partly a runtime
verification gap; detector `use_sim_time` alone does not prove synchronization.

## 5. Make Repeated-Category Scenarios Scalable

- [x] Update `Simulation/scripts/render_scenario.py` to require unique entity
  names but allow repeated marker IDs; remove the `buoy_<marker_id>` naming rule
  and marker-ID uniqueness check.
- [x] Add a committed scenario containing at least two distinct buoys of the
  same category and verify the rendered SDF and manifest preserve both entities.
- [x] Replace the four hard-coded `buoy_0` through `buoy_3` truth bridges in
  `blueboat_sim_bringup/config/bridge.yaml` with generated/dynamic bridging or
  another approach that scales to the manifest's entity roster.
- [x] Update truth subscriptions and evaluation storage to key by entity
  identity. Do not store detections in a dictionary keyed only by marker ID,
  because that collapses simultaneous same-category observations.
- [x] Verify evaluation compares repeated-category simulated entities
  independently, and the shared bootstrap receives neither entity IDs nor truth
  positions. The `repeated_red` live test distinguishes both visible red buoys.
- [ ] **Deferred real perception/mapping:** verify category observations and
  data association in actual autonomy consumers without leaking simulator IDs
  or truth positions.

Required before repeated-category mapping association and the agreed integrated
mapping acceptance run.

## 6. Align Simulator Category Assets

- [x] Align marker 0's model materials and `model.config` description with the
  white category in `Simulation/models/aruco_buoy_id0/`.
- [x] Align marker 3's model materials and `model.config` description with the
  blue category in `Simulation/models/aruco_buoy_id3/`.
- [x] Update scenario documentation, fixtures, screenshots, and visual
  expectations to the agreed marker/category mapping.

Required before validating category labels against simulator buoy appearances.
ArUco classification still uses marker IDs, not sampled visible color.

## 7. Complete Bringup, Readiness, Persistence, and Shutdown

- [x] Define and implement the current simulation launch chain: render a fresh
  scenario/manifest, start Gazebo and SITL, confirm advancing simulation time
  and the vehicle, expose SITL MAVLink on UDP 14552, start the Simulation
  Adapter and MAVROS, then start the explicitly non-commanding autonomy bootstrap.
- [ ] **Deferred real application:** replace the approved bootstrap with the
  configured perception/state/mapping processes and their readiness policy.
- [x] Make ordering depend on explicit readiness evidence at each handoff, with
  bounded timeouts, actionable failure messages, and relevant log collection.
  Container creation or process existence alone is insufficient readiness.
- [x] Separate liveness from source and mission readiness. Container health may
  prove required processes are alive; diagnostics must separately report camera
  delivery/calibration, MAVROS transport connection, required telemetry and
  state freshness, transform availability, and whether the sensing/mapping
  application is ready for the current milestone.
- [x] Implement failure propagation and shutdown for the current services and
  supervised children. Failed startup, simulator exit, Adapter child exit,
  autonomy exit, camera silence, and `make down` passed live cleanup checks.
- [ ] **Remaining lifecycle acceptance:** inject FCU silence; test Ctrl-C and
  TERM cleanup, duplicate-start rejection, and SITL parameter retention/reset
  across `down`/restart/`WIPE_PARAMS`. The current 11-case run was stopped after
  six cases; see the final verification report for results.
- [ ] Preserve runtime logs and SITL EEPROM/parameter state across ordinary
  `down`/restart, and retain the explicit `WIPE_PARAMS` path for a clean FCU
  state. Implementation exists; persistence/restart acceptance remains unrun.
- [ ] **Deferred real mapping application:** ensure each fresh application
  launch creates empty mapping/observation state rather than reloading a prior
  map. The current bootstrap owns no mapping state.
- [x] Record run/scenario/configuration identity with logs so persisted vehicle
  state is not confused with fresh mapping-session state.

Required before the first integrated perception/state/mapping run. Pause/resume
and partial-stack restart recovery may remain unsupported, but ordinary full
startup and shutdown must be deterministic.

## 8. Replace Boundary and Acceptance Tests

- [x] Rewrite `tests/test_container_boundaries.py` to assert that the selected
  Adapter owns `FCU_URL`, MAVROS packages/configuration/launch, GeographicLib,
  and FCU health while autonomy owns none of them.
- [x] Replace the standalone-autonomy-with-`FCU_URL` contract with Simulation
  deployment tests selecting one Adapter and using the common MAVROS/camera
  contracts.
- [ ] **Deferred hardware:** add matching Hardware deployment tests when the
  actual Hardware Adapter and deployment exist.
- [x] Update `tests/ros_boundary_smoke.py` to consume generic camera topics and
  frames, verify actual RGB-D and FCU diagnostic delivery inside autonomy, and
  reject truth frames/data and bootstrap command capability. The evaluator
  additionally decodes live MAVROS State; the autonomy probe checks its graph
  type without adding unused message dependencies.
- [ ] **Deferred real state application:** validate direct MAVROS telemetry
  consumption by the real autonomy state node with its required public message
  dependencies.
- [x] Add package/image dependency tests proving autonomy excludes Gazebo,
  simulator manifests/truth, ZED drivers, MAVROS launch/runtime packages, and
  environment-specific transport configuration.
- [x] Update camera/evaluator tests to cover configured camera rosters,
  calibration-driven dimensions, agreed encodings and depth units,
  registered-depth timing/frame compatibility, stale inputs, and missing-source
  diagnostics.
- [x] Add repeated-category regression coverage for two visible instances with
  one marker/category and separately identified truth entities.
- [x] Split liveness, source-readiness, FCU-readiness, and mission-readiness
  assertions so a healthy container cannot be reported as semantic success.
- [x] Keep `make mavros-smoke` explicitly simulation-only, move its execution to
  the evaluation location, and retain bounded zero-velocity-command/disarm cleanup.

Required alongside each migration above; remove obsolete assertions rather than
keeping dual ownership or old topic names as permanent compatibility behavior.

## 9. Update Operational Guidance

- [x] Update `AGENTS.md`, `Adapter/README.md`, `autonomy/README.md`,
  `Simulation/README.md`, and `Simulation/docs/DEVELOPMENT.md` when ownership
  migrates so contributor instructions no longer assign MAVROS to autonomy or
  evaluation clients to Adapter runtime.
- [x] Update `Simulation/docs/SETUP.md` and
  `Simulation/docs/RGBD_AND_BUOY_SCENARIOS.md` with the final image contents,
  startup handoffs, generic topics/frames, and Adapter-owned MAVROS behavior.
- [x] Scan all current Markdown for old `Adapter/` paths, legacy public camera
  names, autonomy-owned `FCU_URL`, and autonomy-owned MAVROS instructions.
- [x] Preserve completed implementation plans and verification reports as
  historical records. Add a clear superseded reference where necessary rather
  than rewriting past verification as if it tested the new architecture.

Required as part of the ownership and path migration so new contributors and
agents do not reintroduce the superseded boundary.

## 10. Final Integration Verification

- [x] Run `make validate` from `Simulation/` before building changed images.
- [x] Perform clean Adapter and autonomy image builds so dependency placement,
  GeographicLib installation, and launch ownership are tested rather than
  inherited from old image layers.
- [x] Run `make verify-rgbd` after changes to models, scenarios, bridges, frames,
  MAVROS, Compose, or evaluation tools, plus focused contract tests for the
  implemented Simulation Adapter and normative shared configuration.
- [ ] **Deferred hardware:** run focused contract and live acceptance tests for
  the Hardware Adapter after its deployment is implemented.
- [x] Exercise the live simulation path through UDP 14552 and record separate
  evidence for process liveness, camera delivery, MAVROS connection/telemetry,
  common frames/topics, truth isolation, and safe command cleanup.
- [ ] **Deferred real sensing/mapping application:** run the agreed manually
  piloted mapping acceptance scenario with all four
  categories and two same-category buoys only after perception, state, mapping,
  and lifecycle work exists; confirm the sensing/mapping stack emits no motion
  commands.
- [x] Record semantic results, versions, configuration, logs, and visual evidence
  before marking corresponding items complete. Do not treat Compose resolution,
  a healthy container, source inspection, or a single delivered image as
  end-to-end acceptance.

## Scope of This Checklist

This file records current-system migration work. Algorithm choices and numerical
tuning still listed under the Low-Level Design's **Open Design Decisions** are
not defects unless implementation has already hard-coded a conflicting choice.
When an open decision is resolved, update the contract first and then add any
new migration required by existing code here.
