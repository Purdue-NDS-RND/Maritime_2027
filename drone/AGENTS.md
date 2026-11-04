# Drone sensing and perception instructions

Read root `AGENTS.md`, `docs/design.md`, `drone/LLM.md` and `drone/TASKS.md`
before work here. Read `docs/ros2_geolocation_packages.md` before choosing or
reimplementing camera projection, transforms, interpolation or geodesy.

## Authorized Git scope

The user authorizes modifications only on `feature/cv-raycast` in
`Purdue-NDS-RND/Maritime_2027` for this workstream. Verify repository and branch
before writes/pushes. Do not modify `main`, the archive or any other branch,
create an alternate branch, force push, merge, or change repository permissions.
For an API-based commit, explicitly target this ref and use the observed head
as the expected SHA; if it changes, reread and preserve concurrent edits.

## Component contract

- This area owns aerial capture, YOLO26n water-object detection, ENU geolocation,
  physical-instance mapping and the object-map export. It does not own boat routes.
- Planned sensors are fixed Arducam IMX519, IMU/vehicle attitude and ordinary GNSS
  on an Orin Nano 8GB. The user explicitly removed RTK on 2026-11-04; it is not a
  deployment dependency. Exact camera/pose/timing/vertical-datum contracts remain unverified.
- Keep a fixed ENU origin; convert to WGS84 at export. Preserve calibration,
  source-image timestamps, GNSS/pose quality and uncertainty/provenance.
- Unknown aerial color is valid; operator labels and course roles belong to GCS review.
- Evaluate IPM and reuse tf2/image_geometry/geodesy where suitable. Keep a thin adapter.
  Package research is not a claim that dependencies are installed or accepted.
- Preserve independently testable boat/GCS routes and existing simulator acceptance.
  Boat ZED perception is a later, separate integration.

## Evidence and maintenance

Current state includes a runnable, synthetically tested standalone processing/replay
core. Do not claim real sensor mapping, ROS/Docker/Jetson integration or physical
accuracy acceptance. Synthetic adapters/scenarios/evaluation live in
`perception_synthetic/`; production processing must not import scene truth.
Keep adapter selection explicit and never substitute synthetic calibration or inputs
after a hardware failure. Update the relevant living reference and task IDs when
behavior or decisions change. Avoid per-chat handoff reports. Keep recordings,
weights, generated engines and scratch results out of source commits.

