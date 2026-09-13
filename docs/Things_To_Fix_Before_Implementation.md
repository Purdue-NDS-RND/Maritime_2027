# Things to Fix Before Implementation

This checklist tracks migrations required to bring the current repository into
line with the [Low-Level Design](Low_Level_Design.md). It is ordered by
dependency: settle the shared contracts first, move runtime ownership second,
then replace tests and run end-to-end acceptance. None of the items below is
implemented merely because it appears in the design.

## 1. Freeze the Adapter Contracts

### Common MAVROS Contract

- [ ] Define one versioned MAVROS contract used by both the Simulation and
  Hardware Adapters: ROS distribution and MAVROS version, public `/mavros/...`
  namespace, enabled/disabled plugin lists, MAVLink protocol, source system ID,
  target system/component IDs, frame conventions, and time/timesync settings.
- [ ] Put the shared values in one canonical configuration source, with only
  transport and environment-specific device settings overridden per Adapter.
- [ ] Preserve or deliberately migrate the currently tested source system ID
  `255`, target `1/1`, MAVLink v2, root namespace, and disabled/selected TF
  behavior; do not let Simulation and Hardware defaults drift independently.
- [ ] Define the public telemetry, command, service, acknowledgment, and
  connection-diagnostic surface that autonomy and the GCS may depend on.
- [ ] Pin or otherwise control dependency changes closely enough that a rebuild
  cannot silently change MAVROS namespace or plugin behavior.

Required before moving MAVROS or writing consumers against its interface. The
current settings are embedded in
`autonomy/ros_ws/src/maritime_bringup/launch/vehicle.launch.py`, and the current
ROS packages are installed without an exact MAVROS package version.

### Common Camera Contract

- [ ] Make each Adapter expose configured camera sources as
  `/sensors/camera_N/color/image_raw`,
  `/sensors/camera_N/depth/image_rect_raw`, and
  `/sensors/camera_N/color/camera_info`, with `camera_N_link` and
  `camera_N_optical_frame` frames. Internal Gazebo and vendor-driver names may
  remain private to their Adapter.
- [ ] Specify accepted color encoding(s) and a canonical registered-depth
  encoding and unit. Evaluate and document `32FC1` metres as the initial common
  depth representation, including invalid-value semantics and any conversion
  required by a hardware driver.
- [ ] Require depth to be registered to the color image and define which
  calibration, distortion model, dimensions, and optical frame apply to the
  pair. Preserve acquisition timestamps and define the RGB/depth timestamp
  matching tolerance.
- [ ] Make the enabled camera roster explicit deployment configuration:
  `camera_0` in current simulation and `camera_0` plus `camera_1` on hardware.
  Autonomy launch must enumerate configured cameras rather than infer a fixed
  count or model name.
- [ ] Make image consumers and acceptance tests derive dimensions and
  intrinsics from `CameraInfo`; retain 1280x720 only as the current simulated
  calibration, not as a shared autonomy constant.
- [ ] Define Adapter startup behavior and diagnostics for missing images,
  missing/stale calibration, frame mismatches, unregistered depth, and
  incompatible timestamps.

Required before depth-based positioning and before adding the second physical
camera. Initial 2D perception may proceed only if it consumes the generic color
topic and preserves the incoming header.

### Scenario Entity and Category Contract

- [ ] Give every scenario buoy an immutable, unique entity identity independent
  of `marker_id` and category; keep the ArUco mapping category-level:
  `0 = white`, `1 = red`, `2 = green`, `3 = blue`.
- [ ] Define manifest fields and evaluation-topic naming from that entity
  identity so two physical buoys may use the same marker/category without
  colliding.
- [ ] Replace comma-separated `ACTIVE_BUOY_IDS` and any other marker-ID roster
  where it is being used as an entity roster with an identity-preserving
  manifest or equivalent configuration.

Required before changing the renderer and truth bridge, because their generated
names and evaluator subscriptions must follow the same contract.

## 2. Move MAVROS Into the Selected Adapter

### Simulation Adapter

- [ ] Move the current flat `Adapter/` simulation project to the target
  `Adapter/simulation/` layout before adding `Adapter/hardware/`. Update Docker
  build contexts, Compose extension paths, validation paths, Make targets, and
  documentation as one relocation; do not leave two active path conventions.
- [ ] Move the MAVROS launch and shared configuration out of
  `autonomy/ros_ws/src/maritime_bringup/` and into Simulation Adapter bringup.
- [ ] Install `mavros`, `mavros-extras`, `mavros_msgs`, GeographicLib tools, and
  required GeographicLib datasets in the Simulation Adapter image; verify the
  dataset-install step in a clean image build.
- [ ] Move `FCU_URL` ownership from the autonomy service and `Simulation/scripts/run.sh`
  handoff to the Simulation Adapter. Keep SITL's dedicated output on UDP 14552
  and configure the Adapter endpoint as `udp://:14552@` unless the shared
  contract intentionally changes it.
- [ ] Start camera/Gazebo bridges and MAVROS through one Simulation Adapter
  bringup chain, and make its process supervision fail visibly if either
  required child exits.
- [ ] Move FCU connection checks into Adapter diagnostics and update Compose
  dependency/readiness ordering so autonomy starts against the selected Adapter,
  not directly against the simulator's health.

Required before removing MAVROS from autonomy. During the migration, ensure
only one MAVROS instance binds the SITL endpoint.

### Hardware Adapter

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

- [ ] Remove the MAVROS runtime packages, GeographicLib installation, `FCU_URL`,
  vehicle launch wrapper, and MAVROS connection healthcheck from the autonomy
  image/package/Compose definition after the Adapter path is working. Retain
  `mavros_msgs` wherever autonomy code needs the public `/mavros/...` message or
  service definitions.
- [ ] Keep autonomy dependent only on the public ROS message packages and
  interfaces it actually consumes; add automated checks excluding Gazebo,
  camera-driver, simulator-truth, and flight-controller-transport dependencies.
- [ ] Give the autonomy container a real application process after removing its
  current MAVROS-only `CMD`. Prefer coordinating this cutover with the first
  perception/state/system launch so the service has meaningful work and a
  meaningful liveness check; do not add `sleep`, `tail`, or a fake keepalive.
- [ ] Keep shared `maritime_bringup` responsible for autonomy nodes and
  environment-neutral configuration only. Adapter startup must remain outside
  that launch tree.

Required as one coordinated cutover. Do not merge a state in which the autonomy
container immediately exits or appears healthy while running no autonomy work.

## 3. Isolate Evaluation From Runtime Adapters

- [ ] Move `sensor_smoke.py` and the boat-commanding `mavros_smoke.py` out of
  `blueboat_sim_bringup` into `Simulation/tests/` or a dedicated
  simulation-evaluation package/image.
- [ ] Remove OpenCV/ArUco, scenario-manifest, and truth-consumer dependencies
  from the Adapter runtime image unless a separate non-evaluation runtime
  function demonstrably needs them. The Adapter still needs the MAVROS runtime
  and its message definitions to expose the agreed vehicle interface.
- [ ] Keep the Adapter limited to producing camera, clock, transform, MAVROS,
  and availability interfaces. Evaluators may subscribe to those outputs and
  `/blueboat/ground_truth/...`, but must not be launched as Adapter runtime
  responsibilities.
- [ ] Ensure command-capable evaluators are invoked only by explicit simulation
  test commands, never by normal Adapter startup and never against hardware.
- [ ] Preserve truth on evaluation-only topics and ensure no autonomy launch,
  package, parameter, manifest mount, or shared TF source consumes perfect boat
  or buoy pose.

Required before treating the Adapter as the production environment boundary
and before reusing its shape for hardware.

## 4. Normalize the Current Simulated Camera Boundary

- [ ] Remap the current `/blueboat/camera/...` ROS outputs to the common
  `/sensors/camera_0/...` topics at the Simulation Adapter boundary. Gazebo may
  continue publishing `/blueboat/rgbd_camera/...` internally.
- [ ] Replace public `zed2i_camera_link` and
  `zed2i_left_camera_optical_frame` headers/transforms with `camera_0_link` and
  `camera_0_optical_frame` while leaving any private Gazebo asset identifiers
  unchanged where renaming provides no interface benefit.
- [ ] Update bridge YAML, static-transform launch, Adapter health/readiness
  diagnostics, perception remaps, evaluator subscriptions, and boundary tests
  in the same change so there is no mixed old/new public interface.
- [ ] Verify RGB, registered depth, and `CameraInfo` carry compatible timestamps,
  dimensions, calibration, encoding, and the normalized optical frame. Verify
  the `base_link -> camera_0_link -> camera_0_optical_frame` transform using the
  configured simulated mount.
- [ ] Resolve camera and MAVROS clock behavior under uninterrupted simulation,
  including `use_sim_time`, timestamp origins, state interpolation, stale-data
  limits, and behavior at supported launch/shutdown boundaries.

Required before autonomy depends on named camera transforms or combines images,
depth, and vessel state. This is partly a known migration and partly a runtime
verification gap; detector `use_sim_time` alone does not prove synchronization.

## 5. Make Repeated-Category Scenarios Scalable

- [ ] Update `Simulation/scripts/render_scenario.py` to require unique entity
  names but allow repeated marker IDs; remove the `buoy_<marker_id>` naming rule
  and marker-ID uniqueness check.
- [ ] Add a committed scenario containing at least two distinct buoys of the
  same category and verify the rendered SDF and manifest preserve both entities.
- [ ] Replace the four hard-coded `buoy_0` through `buoy_3` truth bridges in
  `blueboat_sim_bringup/config/bridge.yaml` with generated/dynamic bridging or
  another approach that scales to the manifest's entity roster.
- [ ] Update truth subscriptions and evaluation storage to key by entity
  identity. Do not store detections in a dictionary keyed only by marker ID,
  because that collapses simultaneous same-category observations.
- [ ] Verify evaluation can compare each simulated entity independently while
  perception and autonomy receive only category observations, never entity IDs
  or truth positions.

Required before repeated-category mapping association and the agreed integrated
mapping acceptance run.

## 6. Align Simulator Category Assets

- [ ] Align marker 0's model materials and `model.config` description with the
  white category in `Simulation/models/aruco_buoy_id0/`.
- [ ] Align marker 3's model materials and `model.config` description with the
  blue category in `Simulation/models/aruco_buoy_id3/`.
- [ ] Update scenario documentation, fixtures, screenshots, and visual
  expectations to the agreed marker/category mapping.

Required before validating category labels against simulator buoy appearances.
ArUco classification still uses marker IDs, not sampled visible color.

## 7. Complete Bringup, Readiness, Persistence, and Shutdown

- [ ] Define and implement the complete simulation launch chain: render a fresh
  scenario/manifest, start Gazebo and SITL, confirm advancing simulation time
  and the vehicle, expose SITL MAVLink on UDP 14552, start the Simulation
  Adapter and MAVROS, then start autonomy and its configured perception/state/
  mapping processes.
- [ ] Make ordering depend on explicit readiness evidence at each handoff, with
  bounded timeouts, actionable failure messages, and relevant log collection.
  Container creation or process existence alone is insufficient readiness.
- [ ] Separate liveness from source and mission readiness. Container health may
  prove required processes are alive; diagnostics must separately report camera
  delivery/calibration, MAVROS transport connection, required telemetry and
  state freshness, transform availability, and whether the sensing/mapping
  application is ready for the current milestone.
- [ ] Define failure propagation and graceful shutdown for every service and
  child process. `make down`, Ctrl-C, failed startup, and verification cleanup
  must stop autonomy, Adapter/MAVROS, SITL/MAVProxy, and Gazebo without orphaned
  publishers or occupied ports.
- [ ] Preserve runtime logs and SITL EEPROM/parameter state across ordinary
  `down`/restart, retain the explicit `WIPE_PARAMS` path for a clean FCU state,
  and ensure each fresh application launch creates empty mapping/observation
  state rather than reloading a prior map.
- [ ] Record run/scenario/configuration identity with logs so persisted vehicle
  state is not confused with fresh mapping-session state.

Required before the first integrated perception/state/mapping run. Pause/resume
and partial-stack restart recovery may remain unsupported, but ordinary full
startup and shutdown must be deterministic.

## 8. Replace Boundary and Acceptance Tests

- [ ] Rewrite `tests/test_container_boundaries.py` to assert that the selected
  Adapter owns `FCU_URL`, MAVROS packages/configuration/launch, GeographicLib,
  and FCU health while autonomy owns none of them.
- [ ] Replace the standalone-autonomy-with-`FCU_URL` contract with Simulation
  and Hardware deployment tests that select one Adapter and share the common
  MAVROS and camera contracts.
- [ ] Update `tests/ros_boundary_smoke.py` to consume the generic camera topic
  and frames, verify MAVROS and actual camera data delivery into autonomy, and
  assert that truth frames/data do not enter the shared navigation interfaces.
- [ ] Add package/image dependency tests proving autonomy excludes Gazebo,
  simulator manifests/truth, ZED drivers, MAVROS launch/runtime packages, and
  environment-specific transport configuration.
- [ ] Update camera/evaluator tests to cover configured camera rosters,
  calibration-driven dimensions, agreed encodings and depth units,
  registered-depth timing/frame compatibility, stale inputs, and missing-source
  diagnostics.
- [ ] Add repeated-category regression coverage for two visible instances with
  one marker/category and separately identified truth entities.
- [ ] Split liveness, source-readiness, FCU-readiness, and mission-readiness
  assertions so a healthy container cannot be reported as semantic success.
- [ ] Keep `make mavros-smoke` explicitly simulation-only, move its execution to
  the evaluation location, and retain bounded neutral-command/disarm cleanup.

Required alongside each migration above; remove obsolete assertions rather than
keeping dual ownership or old topic names as permanent compatibility behavior.

## 9. Update Operational Guidance

- [ ] Update `AGENTS.md`, `Adapter/README.md`, `autonomy/README.md`,
  `Simulation/README.md`, and `Simulation/docs/DEVELOPMENT.md` when ownership
  migrates so contributor instructions no longer assign MAVROS to autonomy or
  evaluation clients to Adapter runtime.
- [ ] Update `Simulation/docs/SETUP.md` and
  `Simulation/docs/RGBD_AND_BUOY_SCENARIOS.md` with the final image contents,
  startup handoffs, generic topics/frames, and Adapter-owned MAVROS behavior.
- [ ] Scan all current Markdown for old `Adapter/` paths, legacy public camera
  names, autonomy-owned `FCU_URL`, and autonomy-owned MAVROS instructions.
- [ ] Preserve completed implementation plans and verification reports as
  historical records. Add a clear superseded reference where necessary rather
  than rewriting past verification as if it tested the new architecture.

Required as part of the ownership and path migration so new contributors and
agents do not reintroduce the superseded boundary.

## 10. Final Integration Verification

- [ ] Run `make validate` from `Simulation/` before building changed images.
- [ ] Perform clean Adapter and autonomy image builds so dependency placement,
  GeographicLib installation, and launch ownership are tested rather than
  inherited from old image layers.
- [ ] Run `make verify-rgbd` after changes to models, scenarios, bridges, frames,
  MAVROS, Compose, or evaluation tools, plus focused contract tests for both
  Adapter configurations.
- [ ] Exercise the live simulation path through UDP 14552 and record separate
  evidence for process liveness, camera delivery, MAVROS connection/telemetry,
  common frames/topics, truth isolation, and safe command cleanup.
- [ ] Run the agreed manually piloted mapping acceptance scenario with all four
  categories and two same-category buoys only after perception, state, mapping,
  and lifecycle work exists; confirm the sensing/mapping stack emits no motion
  commands.
- [ ] Record semantic results, versions, configuration, logs, and visual evidence
  before marking corresponding items complete. Do not treat Compose resolution,
  a healthy container, source inspection, or a single delivered image as
  end-to-end acceptance.

## Scope of This Checklist

This file records current-system migration work. Algorithm choices and numerical
tuning still listed under the Low-Level Design's **Open Design Decisions** are
not defects unless implementation has already hard-coded a conflicting choice.
When an open decision is resolved, update the contract first and then add any
new migration required by existing code here.
