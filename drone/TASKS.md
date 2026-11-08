# Sensing and perception tasks

Last updated: 2026-11-08. Status: standalone synthetic milestone and portable IMU integration implemented; hardware,
ROS/Docker/Jetson and physical acceptance tasks remain open. See the portable results below.
Owners below identify responsibility areas, not assigned teammates. Numerical acceptance
limits must be set with boat/GCS owners before declaring deployment readiness.

## Completed foundation

- [x] Review the provided CUASC vision pipeline and Maritime integration boundaries.
- [x] Review historical mission documents, buoy imagery and current official rules.
- [x] Record ENU architecture, measurement risks, proposed data semantics and staged plan.
- [x] Reproduce the legacy centre-ray frame failure with the extracted function under
  the standard ROS attitude contract. No hardware conclusion is implied.
- [x] Establish these maintained context and task references.
- [x] Research ROS 2 IPM, image_geometry, tf2, timing/geodesy tools and YOLO26 wrapper
  options; inspect upstream source and record compatibility limits.
- [x] Review the forwarded Gemini proposal, distinguish new targets from assumptions,
  check the mathematics and document uncertainty/tracking corrections.

## P0: establish frames, measurements and reproducible inputs

| ID | Task | Done when | Depends on |
| --- | --- | --- | --- |
| SP-01 | Inventory flight controller/firmware, JetPack, ROS, Arducam lens/mode/focus, ordinary GNSS receiver/antenna and telemetry link, camera serials and storage | Hardware table has observed versions, interfaces and unresolved fields; target runtime matrix is recorded | Hardware access |
| SP-02 | Define ENU origin, global datum, vertical datum, body reference, quaternion direction/order, heading convention and reset policy | A frame contract names every transform, units, source and authority; camera/antenna lever arms are measured | SP-01 |
| SP-03 | Agree location/coverage/freshness requirements from boat geometry and course clearances | Numeric limits for horizontal p95, bias, map completeness, false objects, age and latency are recorded with rationale | Boat/GCS input |
| SP-04 | Build a recording/replay specification and first dataset | Frames, capture times, raw pose/attitude samples, GNSS/estimator health, origins, calibration and versions can be replayed deterministically | SP-01, SP-02 |
| SP-05 | Establish camera intrinsics/extrinsics and water elevation | Held-out reprojection/ground-target residuals are measured across the image; calibrated mode/focus is fixed; water and camera use one vertical reference | SP-01, SP-02 |
| SP-06 | Measure camera-FCU clock relationship and capture delay | Offset, drift, jitter, timestamp meaning and allowed interpolation gaps are quantified; invalid timing is observable | SP-04 |
| SP-07 | Obtain surveyed object ground truth | Repeated reference measurements have uncertainty; stationary targets and buoy water-centres are distinguishable | Independent measured reference; RTK is not a deployment dependency |

These proceed alongside model dataset collection. Do not wait for a final trained model
to test geolocation: measured pixels or manual annotations isolate geometry first.

## P1: hardware-independent ENU geolocation core

- [x] SP-08: Implement a thin geometry adapter around an evaluated library, returning
  ENU hit + quality/rejection reason. Prefer IPM after SP-34; use image_geometry/tf2
  with a narrow analytic intersection fallback if a concrete mismatch warrants it.
  Acceptance: known centre/edge pixels, 90-degree headings, roll/pitch, lever arms,
  synthetic round trips and nonintersecting rays give analytically correct results.
- [ ] SP-09: Use tf2 pose history/interpolation at the exposure timestamp, adding clock,
  source-gap and quality checks rather than rewriting SLERP/history arithmetic.
  Acceptance: missing brackets, excessive gaps, origin resets and invalid quaternions
  produce explicit invalid/degraded results; no silent latest-pose substitution.
- [x] SP-10: Implement WGS84 geodetic/ECEF/ENU conversion at the export boundary.
  Acceptance: independent reference and round-trip tests across the course extent;
  quantify disagreement with existing simulator/GCS projection.
- [ ] SP-11: Add quality propagation and sensitivity analysis for pixel, position,
  attitude, mount, time and water-height errors.
  Acceptance: report random uncertainty and possible common bias separately; compare
  predicted uncertainty coverage with held-out reference measurements.
  Include the covariance/bias treatment in [uncertainty and tracking](../docs/uncertainty_tracking.md).
- [ ] SP-12: Build deterministic replay comparison against the retained CUASC baseline.
  Acceptance: same observations generate per-target residuals and rejection counts;
  held-out data, calibration IDs and the baseline version are recorded.

Dependencies: SP-08 can start now with explicit synthetic frames; physical acceptance of
SP-09 through SP-12 requires SP-02, SP-04 through SP-07.

## P2: water-object detector and onboard runtime

- [ ] SP-13: Define annotation policy for actual buoy bodies, floating case and launch
  target as prioritized; mark glare/reflections/boat/dock/debris as negatives or ignore.
  Initial aerial buoy class may ignore color. No claim of arbitrary object detection.
- [ ] SP-14: Collect aerial imagery at intended heights and views: multiple days,
  lighting, water states, headings, edge positions, occlusion and minimum object sizes.
  Split by recording/flight/day/location, not adjacent frames.
- [ ] SP-15: Train and evaluate the user's YOLO26n baseline; retain training config,
  dataset versions, class map and portable weights. Recover old training assets if useful.
  Report precision/recall and per-object survey recall, not only mAP.
- [ ] SP-16: Evaluate full-frame resize versus tiles at the real operating geometry.
  Report missed small objects, localization pixel error, duplicate boxes and runtime.
  Validate inverse crop/resize/letterbox transforms back to calibrated pixels.
- [ ] SP-17: Evaluate bounding-box centre versus waterline/keypoint/mask/elevation-aware
  location references. Start with the simplest method meeting the measured error budget.
- [ ] SP-18: Compare a thin Ultralytics/TensorRT adapter with a pinned yolo_ros wrapper
  on the actual aarch64 GPU stack, then integrate capture/detection in a ROS 2
  drone app. Declare dependencies; build TensorRT for the actual deployment stack;
  bound queues and separate logging from acquisition.
  Acceptance: sustained measured end-to-end latency/rate, RAM, GPU use, power/thermal
  behavior, frame drops and timestamps under simultaneous recording.
- [ ] SP-19: Add startup/configuration diagnostics and observable health states.
  Acceptance: missing weights, bad intrinsics/resolution, stale pose/GNSS fixes,
  failed writes, full disk, camera stalls and overload are reported without plausible
  fabricated locations. Explicit policies determine whether degraded observations remain usable.

Dependencies: SP-13 -> SP-14 -> SP-15; SP-16/SP-17 require representative data;
SP-18 uses SP-06/SP-09 and can initially replay images rather than fly.

## P3: instance association, survey map and GCS boundary

- [ ] SP-20: Preserve raw observations and fuse repeated ENU hits into object instances.
  Use spatial/time/uncertainty gates; distinguish two nearby buoys of the same class.
  Acceptance: measured merge/split/false-track rates, stable IDs within a survey,
  retained outliers/rejection reasons and no artificial confidence from correlated frames.
  Evaluate linear-KF baselines and gated assignment with explicit unmatched/ambiguous
  alternatives; a class ID or overlapping gate does not establish physical identity.
- [ ] SP-21: Add survey coverage, observation-age and motion/drift evaluation.
  Acceptance: missed regions, insufficient views and stale tracks are visible;
  map freshness is tied to observed movement and course margin.
- [ ] SP-22: Agree the versioned JSON contract with the GCS owner using
  [the draft](../docs/perception_contract.md).
  Acceptance: unknown color is accepted; observations, maps and boat routes stay separate;
  coordinate origin, quality, IDs, timestamps and revision semantics are explicit.
- [ ] SP-23: Implement a deliberate GCS importer or compatibility exporter.
  Acceptance: actual GCS can load unlabeled surveyed instances, preserve raw estimates
  and provenance, and invalidate route approval when relevant map edits occur.
  Validate format and UI behavior; permissive validation alone is insufficient.
- [ ] SP-24: Implement map transfer/retry/acknowledgement for the selected radio/network.
  Start with local file import, then measured real link. No transport is selected here.
  Acceptance: duplicate, partial, out-of-order and stale revisions cannot replace a newer
  survey silently; confirmed receipt and survey identity are visible.
- [ ] SP-25: Run held-out complete survey -> review -> route -> boat integration trials.
  Acceptance: quantitative map error, completeness, clearance and map age meet SP-03;
  preserve boat-only testability. Simulator truth is used only in evaluation/export tools.

Dependencies: SP-20 uses SP-08/SP-09 and detections; SP-22 can start during P0;
SP-23 requires SP-22; SP-25 requires measured boat navigation limits too.

## Uncertainty and live-tracking extension

The forwarded research brief adds the following targets. They do not implement a live
transport or change the approved boat workflow. See [the design](../docs/uncertainty_tracking.md).

- [ ] SP-35: Agree live report rate, latency, state epoch, maximum age, required probability
  level and whether operation is survey-only or concurrent with boat execution.
  Acceptance: documented target and scope; continuous flights/replanning are not assumed.
- [ ] SP-36: Implement per-observation covariance with position/attitude, pixel/reference,
  water-height, timing and calibration terms, plus a defensible shared-bias treatment.
  Acceptance: analytic/numerical Jacobian and Monte Carlo comparisons; correlated
  repeated observations do not create unsupported absolute precision.
- [ ] SP-37: Compare static/random-walk, constant-velocity KF and appropriate constrained
  motion models against measured buoy attachment/motion and floating-object data.
  Acceptance: correct state/Q ordering and units, irregular time steps, initialized velocity
  uncertainty, long-gap predictions and delayed-measurement handling.
- [ ] SP-38: Evaluate gated global assignment, initiation/confirmation/coasting/staleness
  and cross-pass identity. Acceptance: false/duplicate/missed measurements and overlapping
  gates allow unmatched/ambiguous outcomes; record ID switches and label preservation.
- [ ] SP-39: Define and implement covariance/ellipse reports with state_at, last observation,
  publication time, estimate/association status, frame/units and bias/coverage metadata.
  Acceptance: sorted eigenvalues, correct 95% scale, isotropic/invalid covariance handling,
  prediction at the stated epoch and independently checked GCS display orientation.
- [ ] SP-40: Validate uncertainty and identity on held-out surveyed water trials.
  Acceptance: empirical coverage and ellipse area/sharpness, position error, bias, ID
  switches, freshness and latency meet agreed criteria; synthetic Gaussian tests alone
  do not establish 95% real-world coverage.

SP-35 can proceed immediately; SP-36 follows valid geometry/timing; SP-37/SP-38 require
representative recordings; SP-39 depends on agreed semantics; SP-40 requires independent truth.

## P4: boat perception and mission-specific extensions

- [ ] SP-26: Confirm whether cameras are ZED Mini or ZED X Mini; verify two-camera
  compatibility, interfaces, synchronized capture, calibration and complete Jetson load.
- [ ] SP-27: Collect boat-view data and validate body-frame bearing/range on real buoy
  surfaces. Reject unreliable depth from water/reflections; use robust object-region
  measurements and transform each camera into a common boat frame.
- [ ] SP-28: Implement local color/striped-buoy/target identification for prioritized
  missions. Preserve confidence, invalid depth and temporal association.
- [ ] SP-29: Define mechanism-frame target pose, range and alignment outputs for
  launch/deploy/recover with each mechanism owner. Verify the actual target location,
  not merely the nearby marker buoy; validate mechanism offsets and boat motion.

These do not block the first aerial object-map deliverable. They require separate boat
camera acceptance, not assumed transfer from aerial detector metrics.

## Team integration and rules

- [ ] SP-30: Confirm organizer interpretation of manual labeling/route planning,
  UAV deployment/recovery, mandatory tasks and current scoring. Record dated answers.
- [ ] SP-31: Agree survey start/stop, coverage completion, map-ready/failed states and
  boat launch/recovery coordination. Perception does not take over flight control.
- [x] SP-32: Verify the GitHub connection and target feature branch, and publish the
  maintained context in this documentation change. Allowed write target is exclusively
  `Purdue-NDS-RND/Maritime_2027:feature/cv-raycast`; no alternate branch or merge is authorized.
- [x] SP-33: Complete source-backed ROS 2 package research and record pin candidates,
  APIs, limitations and a library-first recommendation in
  [the package reference](../docs/ros2_geolocation_packages.md).
- [ ] SP-34: Evaluate a compatible pinned IPM revision in the selected ROS/Jetson stack.
  Acceptance: synthetic frame/plane tests, raw/rectified equivalence, image-coordinate
  transforms, missing/stale TF, nonfinite/horizon rejection and replay comparison pass
  agreed tolerances. Upstream NumPy kernel checks alone do not complete this task.

## Ordinary-GNSS design follow-up (2026-11-04)

The user removed RTK. A receiver/base/correction link for RTK is not a deployment
requirement. The [class and ROS proposal](../docs/sensing_perception.md#proposed-end-to-end-class-contracts)
is for discussion; no runtime code or physical accuracy is accepted by this work.

- [x] Record ordinary-GNSS requirement and end-to-end class/interface proposal.
- [ ] SP-41: Establish ordinary-GNSS error and temporal correlation on the actual receiver.
  Acceptance: stationary/moving residuals against independent quantified reference,
  covariance/HDOP semantics, dropout/reacquisition, resets and cross-pass drift recorded;
  uncertainty is not inferred from scatter or detector score alone.
- [ ] SP-42: Verify earth-referenced heading and camera height above water without RTK.
  Acceptance: FCU source/frame/covariance contracts, compass interference under flight
  power, deck/water/camera offsets and height drift meet SP-03; optional range/VIO inputs
  pass separate over-water validity tests.
- [ ] SP-43: Evaluate shared anchor/correlation treatment and local versus absolute maps.
  Acceptance: common GNSS/heading/height errors do not vanish under repeated updates;
  a conservative batch/floor baseline or joint estimator passes held-out coverage checks.
  Shared components and cross-object provenance export without double counting.
- [ ] SP-44: Agree and implement small class contracts, ROS adapters and report envelope.
  Acceptance: annotated frame + time-aligned pose/plane yields validated ENU distribution
  and WGS84 report on replay; unknown covariance, resets, missing heading/height, delayed
  measurements, ambiguity and stale/reordered reports have explicit outcomes.
  Set numerical rate/gap/accuracy limits through SP-03/SP-35 rather than guessing.

SP-41/SP-42 refine SP-01..SP-07; SP-43 extends SP-11/SP-36/SP-40; SP-44 decomposes
SP-08..SP-10/SP-18/SP-20/SP-22/SP-39 rather than creating a competing architecture.

## Completed standalone synthetic milestone (2026-11-04)

The user explicitly authorized runnable implementation. SP-08 uses the narrow OpenCV
analytic-plane fallback; SP-10 uses PROJ. Their checkmarks describe portable numerical
acceptance, not calibration, ROS/IPM or physical acceptance. GCS projection remains
unchanged; its discrepancy is quantified in geolocation.md and reconciliation is SP-23.

- [x] Implement real clock/pose/pixel/geolocation/uncertainty/association/static-tracking/
  WGS84/report algorithms behind common source-neutral input records.
- [x] Separate seeded forward-model sources/scenarios and withheld evaluator from production.
- [x] Demonstrate three analytic targets and a noisy moving-camera survey with shared GNSS
  offset, temporary misses, ambiguity, invalid inputs and stable same-class identities.
- [x] Record/replay config and measurement events; verify byte-identical outputs in another
  process without truth. Preserve checksums and runtime versions; raw evidence is ignored.
- [x] Add meaningful core tests, structural ROS conversion tests and packaged JSON Schema.
- [x] Add optional local-weights detector adapter, recorded ROS node/launch, and Docker
  build candidates. This checkmark means source/config exists, not integration acceptance.

SP-09/SP-34 still require tf2/IPM on a selected ROS/Jetson stack. SP-04/SP-11/SP-20/
SP-36/SP-38/SP-39/SP-43/SP-44 have implemented portable portions; their real recording,
calibrated uncertainty, GCS/display and deployment acceptance is not completed by synthetic
tests. SP-15/SP-18/SP-19 remain open for trained inference/full onboard runtime and diagnostics.
SP-41/SP-42/SP-40 require actual sensors/reference trials. No camera, FCU or radio is assumed.

## Recommended next development slice

The [completion plan](../docs/perception_reports/Maritime_Pipeline_Completion_Plan.docx)
is a source-pinned explanatory snapshot; acceptance remains with the task IDs here.
The [first-test guide](README.md#first-tests-with-manual-pixels-and-real-recordings)
provides a replayable manual-pixel example and an inventory/flat-grid recording checklist.
Prioritize SP-01/SP-02/SP-04/SP-05/SP-06: observed interfaces, source clocks, measured
camera calibration/mount/height and annotated planar targets. Relative bench geometry
can be tested without an accurate WGS84 anchor; absolute GPS acceptance cannot.
The documented manual-pixel replay was executed with four reports, one confirmed track
at the analytical `(0,-0.4)` m EN point, and no replay errors. Both existing demos and
all 74 drone tests passed again. These checks do not complete the hardware tasks or
select an unverified runtime.

Run the README demonstration first. Then establish SP-01/SP-02/SP-04 and SP-41/SP-42
hardware/frame/clock/covariance contracts, replace synthetic sources with annotated real
recordings and evaluate SP-34. Collect SP-14 in parallel. Keep the deterministic replay
suite while adding calibration, real detector references and actual ROS/Jetson integration.

## Python tooling maintenance

Use uv exclusively for setup, installs and Python commands, per the user. README demo,
manual-pixel replay, test and static-check commands use the explicitly selected uv
virtual environment. Requirements and ROS packaging are retained; a project lockfile
migration is not part of this command conversion. A fresh uv environment passed both
demos, manual-pixel replay, identical recorded replay, 74 drone tests, 11 GCS workspace
tests and static checks. Dockerfiles use uv but still require
actual image builds and ROS/Jetson execution before integration acceptance.

## IMU integration progress (2026-11-08)

- [x] Review the five IMU logger commits after `53ef249`; preserve their separation
  while installing the implementation in the drone package and retaining `log/` imports.
- [x] Retain quaternion, nanosecond stamp, frame and covariance availability in replayable
  records; reject malformed readings and protect existing recordings from overwrite.
- [x] Implement `imu_state` processing, a callback sink and an offline exact-time join
  through the existing pose/projection/tracking/report pipeline. Retain joint sample/
  shared covariance and reject unknown heading/height, clock/frame assumptions or noise.
- [x] Run 104 drone tests, including 30 new IMU cases and an end-to-end 90-degree-heading
  replay with retained common GNSS error. ROS lifecycle/QoS tests use doubles.

SP-04/SP-19/SP-44 now have these additional portable portions. SP-01/SP-02/SP-06/SP-41/
SP-42 remain uncompleted: no actual FCU/ROS/Jetson trial or sensor-model validation occurred.
The exact join does not resolve asynchronous real streams; measured alignment, origin/reset,
joint-correlation and deployment contracts remain necessary before a physical GPS claim.

## Camera integration progress (2026-11-08)

- [x] Review CUASC image acquisition and intrinsic files at `e50d6e2`; preserve both
  equivalent calibration YAMLs with full provenance as historical M12/mode candidates.
- [x] Implement configurable Argus/GStreamer image capture, optional ROS publication,
  stride-aware bounded acquisition and PNG/JPEG recording with source timing/checksums.
- [x] Keep raw/rectified/resize/preview CameraInfo consistent; require explicit mode
  geometry on a calibration-size mismatch, and pair detections with exact source metadata.
- [x] Pass 147 drone tests, including 43 camera cases for controls, undistortion/rays,
  resizing, buffer layout, recording, timestamps, failure/cleanup and ROS publication.

SP-04/SP-18/SP-19/SP-44 have additional portable implementations. SP-01/SP-05/SP-06
still require observed Jetson/driver/GI/ROS versions, actual M12 calibration, verified
exposure timestamps, rolling-shutter and measured settings/rates. These test results use
doubles and do not complete hardware, optical, end-to-end timing or onboard acceptance.

## Status maintenance

Use the IDs in commits and discussions. Check a task only when its acceptance evidence
exists; describe important limits in its owning topic. Record unresolved numerical
thresholds explicitly rather than inventing successful accuracy or performance figures.


