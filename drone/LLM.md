# Maritime sensing and perception: working context

Last updated: 2026-11-04. Owner: Samuel Yoon, Sensing and Perception Lead.
Status: a runnable standalone pixel/state-to-GPS core and deterministic synthetic survey
are implemented on `feature/cv-raycast`. Sensor, ROS/Docker/Jetson integration and physical
accuracy remain unverified. [README.md](README.md) contains exact setup/demo/test commands.

## Read this first

Read root `AGENTS.md`, this file, and [TASKS.md](TASKS.md) before sensing/perception work.
The user authorizes writes only to `feature/cv-raycast` in
`Purdue-NDS-RND/Maritime_2027`; see [drone instructions](AGENTS.md).
Then read only the maintained topic needed:

| Topic | Reference |
| --- | --- |
| Responsibilities, CV, runtime, boat perception | [Sensing and perception](../docs/sensing_perception.md) |
| Frames, raycasting, calibration, error budget, experiments | [Geolocation](../docs/geolocation.md) |
| Existing ROS 2 projection packages and reuse decision | [Package research](../docs/ros2_geolocation_packages.md) |
| Live covariance/ellipses, motion models and cross-pass association | [Uncertainty and tracking](../docs/uncertainty_tracking.md) |
| JSON semantics and existing GCS compatibility | [Perception contract](../docs/perception_contract.md) |
| Reusable CUASC code and concrete problems | [Legacy vision review](../docs/legacy_vision_review.md) |
| Missions, document versions, rules questions | [Competition sensing](../docs/competition_sensing.md) |
| Branch workflow and GitHub access | [Repository access](../docs/repository_access.md) |
| Existing system and completed boat simulation milestone | [Design](../docs/design.md), [Milestone 1](../docs/milestone1.md) |

These are living references. Update the applicable topic and task status when decisions,
implementation, hardware or measurements change. Preserve source/evidence links and
distinguish proposals from accepted decisions and measured results. Do not create a new
handoff report for each chat. New chats should read this index rather than the full ZIPs.
The current GitHub feature branch is the canonical shared context. The earlier exported
Markdown pack is a historical starting point; use current repository files for future work.

## Readable reports and first bench test

The user-requested [pipeline report](../docs/perception_reports/Maritime_Pipeline_Report.docx)
and [completion plan](../docs/perception_reports/Maritime_Pipeline_Completion_Plan.docx)
are explanatory snapshots pinned to source `999f1ac`, not new acceptance evidence.
The [README first-test guide](README.md#first-tests-with-manual-pixels-and-real-recordings)
shows explicit manual-pixel injection through replay and the inventory/recording needed
for a stationary planar-grid experiment. Fake origins exercise software only; target
truth stays outside processing, and unknown physical inputs remain unavailable.

## Implemented portable milestone (2026-11-04)

`maritime_perception/` contains validated source-neutral records, explicit clock mapping,
bounded SciPy SLERP pose resolution, OpenCV camera geometry, analytic horizontal-water
intersection, first-order covariance propagation, named shared-error factors, static/
random-walk association/tracking, PROJ WGS84 geodesy and validated versioned JSON reports.
`perception_synthetic/` separately generates raw pixels and antenna states using a forward
camera model. Only its evaluator reads withheld target truth; pure replay works without it.

The analytic scenario recovers three known points exactly. The seeded noisy survey
includes a moving/turning camera, same-class objects, GNSS offset, misses, ambiguity and
invalid inputs. It retains three identities and the shared GNSS uncertainty. Tests cover
geometry, uncertainty, association, validity, reports and process-independent replay.
Current results and limits are maintained in the topic docs; do not infer real accuracy.

The implementation uses the narrow OpenCV/SciPy fallback because ROS/IPM/tf2 are unavailable
in this environment. Optional ROS conversions/recorded-event node/launch and CPU/desktop-ROS
Dockerfiles are present but not runtime-verified. Local Ultralytics weights are required
for the optional detector adapter; inference/trained water detection were not exercised.
No camera/FCU driver, GCS importer, radio infrastructure or flight control was added.

Do not treat a new covariance source ID as evidence of independence. Input adapters must
establish residual versus common covariance, clock validity and frame/reset contracts.
Current named common sources are constant over their declared session/sample; real drift
models and empirical calibration remain open. Real hardware mode forbids synthetic config.

## User-established direction

1. A drone launches from the boat and surveys buoys/objects in the water.
2. Each vehicle is planned to carry a Jetson Orin Nano 8GB.
3. Drone camera: fixed Arducam IMX519; downward-looking is the working orientation,
   with exact mounting rotation and lens/focus still to be measured.
4. Desired survey altitude: below 5 m above water, subject to coverage and accuracy tests.
5. Ordinary GNSS replaces RTK by explicit user direction on 2026-11-04. Receiver,
   antenna, covariance semantics, vertical datum, heading source, attitude accuracy and
   telemetry interfaces remain unverified. No RTK base/correction link is required.
6. YOLO26n is the user's selected detector baseline. Automatic aerial buoy-color classification is optional;
   object instance locations are the first deliverable.
7. Geometry, association and map fusion operate in a fixed local ENU frame.
   Convert consolidated estimates to WGS84 for external consumers at the boundary.
8. Drone sends an object map to a laptop GCS. An operator labels colors/roles using
   imagery and the rough course map. The GCS prepares the boat route.
9. Boat executes the supplied route. Boat perception with two ZED cameras is a
   separate later workstream for local identification, ranging and mission alignment.
10. Reuse useful CUASC code, but establish the measurement error sources and correct
    geometry/timing instead of assuming the previous implementation is accurate.

## Targets added by the forwarded research brief

The user's Gemini brief adds real-time location/uncertainty reports, dynamically
computed Gaussian position ellipses, persistent identities across passes and prediction
through observation gaps. The portable static baseline now implements these report/state
semantics on synthetic input; real motion, transport and cross-pass performance remain targets.
Clarify report cadence/latency/maximum age and whether updates are only during a survey
or must continue while the boat navigates. The existing survey-then-land workflow and
operator route approval remain until explicitly changed.

Keep fixed Arducam and YOLO26n choices. Generic gimbal encoders and alternate detectors
in the brief are not confirmed hardware/model changes. Confirm whether buoys are moored;
a floating case may need a different motion model. A bottom-centre pixel is not a
universal water-contact reference for an overhead image.

Use a linear KF as the first projected-ENU constant-velocity tracker; nonlinear
projection upstream does not alone justify EKF/UKF downstream. Evaluate static/random-walk
and moored-motion alternatives. Preserve shared camera/clock/GNSS biases rather than
letting repeated frames produce falsely tiny covariances. Association must allow
unmatched and ambiguous cases. Output state epoch, last-observation time, prediction
status, EN covariance and explicitly defined ellipse orientation/coverage.

Gemini's planar projection, CWNA covariance, 99% 2D gate and 95% ellipse scale are
mathematically sound under their assumptions. Its covariance budget is incomplete
and its package conclusion misses IPM. See the maintained tracking topic for the
checked equations, implementation candidates, new tasks and unresolved scope.

## 2026-11-04 end-to-end design discussion

The user explicitly replaces RTK with ordinary GPS and requests small, single-purpose
classes, ROS 2 in Docker, and structured GPS reports with uncertainty. The proposed
[class/interface and deployment design](../docs/sensing_perception.md#proposed-end-to-end-class-contracts)
was the discussion proposal. The portable subset above is now implemented; hardware
accuracy and the remaining deployment/transport choices are not accepted.

Camera + raw IMU alone cannot provide absolute GPS object locations. Timestamped GNSS,
earth-referenced heading and height above water are required. Prefer one validated FCU
fused pose over duplicate fusion of its outputs and raw inputs. Firmware and available
covariance remain unknown. Separate local object geometry from shared map anchoring and
drift uncertainty; repeated frames must not average away a common GNSS offset.

Current source review verified Maritime at
`dd18759df02303f4202804fa330ef0e7d5004587` and CUASC main at
`e50d6e2e42e0e6eeac150e8b7c94be0d0474a42d`. Directly inspected CUASC capture,
detector, logger, launch and parameters. Input-stamp preservation is useful; pose fallback
and frame/calibration risks remain. No ROS, inference, camera or flight trial ran.

## Existing repository reality

- Current `drone/` includes the standalone processing core, synthetic source/evaluator,
  tests, optional ROS adapters and deployment candidates alongside context documents.
- `boat/`, `gcs/` and `shared/` have implementations; Gazebo/SITL tools are retained.
- Existing design describes survey -> GCS review -> approved route -> boat execution.
  Initial survey is consolidated, and the drone lands before boat route execution.
- Milestone 1 records selected camera-free slalom simulator acceptance, including three
  2.0 m/s target runs. This review did not rerun those trials. It is not physical acceptance.
- Existing GCS imports geographic object maps, versions 1 and 2. A new ENU survey
  envelope will require a deliberate import/export boundary; it is not already supported.
- Current shared geographic math approximates ArduPilot's local projection. Preserve
  its simulator compatibility while evaluating a WGS84 ECEF/ENU geodetic path.
- Evaluate ROS Sports ipm_library for pixel-to-water-plane projection with tf2 at image
  time. The fallback is image_geometry + tf2 + a narrow analytic intersection function.
  The current non-ROS core uses OpenCV/SciPy/PROJ. Full ROS projection/history dependencies
  are not installed/evaluated on the target stack; SP-34 remains open.
- Automatic route generation, real radio mission delivery, drone survey implementation
  and boat mission-specific camera behaviors are not established by the supplied code.
- The user's implementation request authorizes this standalone milestone. Historical
  boat milestone deferral preserves boat-only testability and does not block drone development.
- Preserve independently testable boat routes; keep navigation decisions out of geolocation.

## Findings that must not be forgotten

- Legacy `mission_logger._raycast_to_gps` mixes an FRD-like ray with a ROS FLU-to-ENU
  attitude. Extracting the actual function and supplying an identity ROS quaternion,
  zero mount and centre pixel at +5 m returns no intersection. See legacy review.
- Capture stamps are generated after read/remap, not demonstrated exposure timestamps.
- Pose interpolation sometimes falls back to the latest pose without rejecting stale data.
- `compressed_grabber` can publish resized pixels with full-resolution intrinsics.
- CameraInfo mixes rectified K/P with original distortion; exported logs can be ambiguous.
- Legacy hard-distance deduplication prevents useful repeated observations from refining
  a track. Class IDs cannot be object IDs when many buoys share a class.
- GNSS position (including RTK in historical notes) does not establish yaw,
  camera-to-body alignment, water height or timing.
- A bounding-box centre on an elevated buoy is not necessarily its water-plane centre.
- Reflections are prominent in supplied buoy images. Label actual bodies separately.
- A 100-frame 4K BGR ring alone uses about 2.32 GiB, before ROS, model or other copies.
- Shared Jetson memory must cover OS, CPU and GPU workloads, not just model weights.
- Exact boat camera model is unresolved: user said ZED Mini; old repository mentions
  ZED X Mini. Verify before selecting drivers/capture hardware.

## Open inputs with highest value

- Ordinary GNSS model/antenna/covariance and temporal drift; attitude/yaw source; autopilot firmware;
  local/global message contracts, time synchronization and origin-reset behavior.
- Actual Arducam lens, camera mode, focus control, exposure metadata and mount survey.
- Camera optical centre, FCU body reference and GNSS antenna lever arms.
- How water elevation will be measured in the same vertical reference as positioning.
- Required map accuracy/coverage/latency, buoy dimensions and motion, boat clearance budget.
- Which missions are prioritized and whether GCS human labeling affects autonomy scoring.
- Exact ZED hardware and two-camera support on the actual boat carrier/Jetson stack.

## ROS 2 reuse findings

- IPM accepts an arbitrary plane, calibrated image pixels, measurement time and
  plane/output TF frames. Its vectorized Python API matches a batch of detection points.
- Its inspected implementation reads K rather than rectified P; adapt rectified CameraInfo
  explicitly. Water at ENU z=h uses shape_msgs/Plane coefficients [0,0,1,-h].
- tf2 supplies buffered transforms and interpolation. It does not validate clock domains,
  GNSS health or acceptable sample gaps; keep those checks in our adapter.
- Prefer the authoritative FCU fused pose if available; robot_localization is conditional,
  not an additional mandatory estimator.
- yolo_ros currently lists YOLO26 but its prebuilt GPU runtime is x64; Jetson/aarch64 GPU
  needs deployment evaluation. A thin Ultralytics/TensorRT ROS adapter remains an option.
- Six analytic checks passed on the extracted IPM intersection kernel only. Full ROS,
  OpenCV distortion, TF, Jetson and hardware integration have not been tested.

These inputs do not prevent implementing a hardware-independent geometry/replay core.

## Review provenance and limits

Reviewed the supplied repositories' architecture and integration surfaces, the active
`src/vision_pipeline` capture/inference/logger/clustering/offline paths, relevant
archived localizers, all four PDFs in text and rendered form, and the linked official
AIMM information/rules pages on 2026-11-01. Repository-wide review was architectural;
unrelated flight-control and all boat/simulator code were not exhaustively audited.
No Jetson, RTK, camera, flight, model-inference or live competition test ran here.
The initial review used ZIP snapshots. GitHub access was subsequently verified for
`Purdue-NDS-RND/Maritime_2027`, with `feature/cv-raycast` based on commit
`5954eb2dcf34658f67231befe07d62b476397f96` before this documentation change.
Read the current branch head on future visits; that baseline is not a permanent head.

| Input | SHA-256 |
| --- | --- |
| CUASC_2026-main.zip | 255c6741b710d41b6e4ff8f9e46da5207e7f3d47f47930a44589619fde686d0d |
| Maritime_2027-feature-cv-raycast.zip | fba8bb77cb2f4ec24aede7b4ca7a75aec77ba7604f69d2ada017e8c27fa1ef6d |
| 2025 AIMM Challenge Brief.pdf | aa643aa085be232603d7f4ec0c55e791090d366a9640efcde072d3d606cfa7f6 |
| AIMM-ICC Competition Course Details 12-13 2025.pdf | efccf4994c05e544821c49a0288197ca40276fcd3d9cc8be39e17d676baa401a |
| Challenge Competition Scoresheet_4-3-2025.pdf | 0e4b0d62d4296319feae5d590dc7427af706e298a97d5fccf38c82ff45dc0ca1 |
| Buoy Images _ AIMM ICC.pdf | 3060ee39f5f4f0b9a01aec57784de07c5ed27b1f5b9ae4c0ad61d8784c769145 |


