# Sensing and perception tasks

Last updated: 2026-11-01. Status: planned except the completed initial review.
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

## P0: establish frames, measurements and reproducible inputs

| ID | Task | Done when | Depends on |
| --- | --- | --- | --- |
| SP-01 | Inventory flight controller/firmware, JetPack, ROS, Arducam lens/mode/focus, RTK receiver/base/radio, camera serials and storage | Hardware table has observed versions, interfaces and unresolved fields; target runtime matrix is recorded | Hardware access |
| SP-02 | Define ENU origin, global datum, vertical datum, body reference, quaternion direction/order, heading convention and reset policy | A frame contract names every transform, units, source and authority; camera/antenna lever arms are measured | SP-01 |
| SP-03 | Agree location/coverage/freshness requirements from boat geometry and course clearances | Numeric limits for horizontal p95, bias, map completeness, false objects, age and latency are recorded with rationale | Boat/GCS input |
| SP-04 | Build a recording/replay specification and first dataset | Frames, capture times, raw pose/attitude samples, RTK health, origins, calibration and versions can be replayed deterministically | SP-01, SP-02 |
| SP-05 | Establish camera intrinsics/extrinsics and water elevation | Held-out reprojection/ground-target residuals are measured across the image; calibrated mode/focus is fixed; water and camera use one vertical reference | SP-01, SP-02 |
| SP-06 | Measure camera-FCU clock relationship and capture delay | Offset, drift, jitter, timestamp meaning and allowed interpolation gaps are quantified; invalid timing is observable | SP-04 |
| SP-07 | Obtain surveyed object ground truth | Repeated reference measurements have uncertainty; stationary targets and buoy water-centres are distinguishable | RTK/reference setup |

These proceed alongside model dataset collection. Do not wait for a final trained model
to test geolocation: measured pixels or manual annotations isolate geometry first.

## P1: hardware-independent ENU geolocation core

- [ ] SP-08: Implement a thin geometry adapter around an evaluated library, returning
  ENU hit + quality/rejection reason. Prefer IPM after SP-34; use image_geometry/tf2
  with a narrow analytic intersection fallback if a concrete mismatch warrants it.
  Acceptance: known centre/edge pixels, 90-degree headings, roll/pitch, lever arms,
  synthetic round trips and nonintersecting rays give analytically correct results.
- [ ] SP-09: Use tf2 pose history/interpolation at the exposure timestamp, adding clock,
  source-gap and quality checks rather than rewriting SLERP/history arithmetic.
  Acceptance: missing brackets, excessive gaps, origin resets and invalid quaternions
  produce explicit invalid/degraded results; no silent latest-pose substitution.
- [ ] SP-10: Implement WGS84 geodetic/ECEF/ENU conversion at the export boundary.
  Acceptance: independent reference and round-trip tests across the course extent;
  quantify disagreement with existing simulator/GCS projection.
- [ ] SP-11: Add quality propagation and sensitivity analysis for pixel, position,
  attitude, mount, time and water-height errors.
  Acceptance: report random uncertainty and possible common bias separately; compare
  predicted uncertainty coverage with held-out reference measurements.
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
  Acceptance: missing weights, bad intrinsics/resolution, stale pose/RTK corrections,
  failed writes, full disk, camera stalls and overload are reported without plausible
  fabricated locations. Explicit policies determine whether degraded observations remain usable.

Dependencies: SP-13 -> SP-14 -> SP-15; SP-16/SP-17 require representative data;
SP-18 uses SP-06/SP-09 and can initially replay images rather than fly.

## P3: instance association, survey map and GCS boundary

- [ ] SP-20: Preserve raw observations and fuse repeated ENU hits into object instances.
  Use spatial/time/uncertainty gates; distinguish two nearby buoys of the same class.
  Acceptance: measured merge/split/false-track rates, stable IDs within a survey,
  retained outliers/rejection reasons and no artificial confidence from correlated frames.
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

## Recommended next development slice

Start SP-02/SP-04 definitions and SP-34's IPM evaluation, then SP-08's thin ENU adapter
with synthetic frame tests and manually annotated reference pixels. In parallel collect SP-14.
Then add timing, calibrated real data and instance fusion before full GCS/radio integration.
This order isolates detector, geometry and telemetry errors instead of confounding them.

## Status maintenance

Use the IDs in commits and discussions. Check a task only when its acceptance evidence
exists; describe important limits in its owning topic. Record unresolved numerical
thresholds explicitly rather than inventing successful accuracy or performance figures.

