# Task 07: Implement the Hardware Adapter Boundary

**Goal:** Create the vessel-side Adapter that exposes the same MAVROS and camera
contracts without simulation dependencies.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 2, "Hardware
Adapter."

**Prerequisites:** Tasks 01–04 approved. Requires access to the selected ZED X
Mini driver/version and the real FCU transport configuration. May run in
parallel with Task 06.

**Exclusive write scope:** `Adapter/hardware/**`. Do not edit shared deployment
YAML, autonomy, simulation files, root tests, or current operational docs.

## Required Work

- Create the Hardware Adapter ROS workspace and container with the controlled
  MAVROS packages, GeographicLib tools/datasets, launch configuration, and FCU
  diagnostics from Task 01.
- Accept real FCU serial or network transport only through deployment
  configuration; document device mapping, permissions, reconnect behavior, and
  override validation inside the hardware subtree.
- Integrate two configured ZED X Mini sources behind Task 02's generic camera
  topics, calibration rules, and mounting transforms.
- Keep ZED drivers, device access, serial/network transport, and hardware
  permissions out of the autonomy image.
- Supply a deployment-fragment example inside `Adapter/hardware/` for Task 09;
  do not modify shared Compose directly.
- Add hardware-local configuration and contract tests that do not move, arm, or
  command a real vessel.

## Acceptance

- Dependency inspection proves the image contains no Gazebo, simulator
  scenario, manifest, or truth packages.
- Launch/configuration checks prove two explicit camera sources and only one
  Hardware Adapter MAVROS instance.
- With hardware available, both cameras publish valid generic color, registered
  depth, `CameraInfo`, and TF, and FCU connection diagnostics reflect the real
  transport. Without hardware, report the exact unverified checks; do not claim
  vessel readiness.
- Invalid device paths, permissions, transport URLs, or missing calibration fail
  visibly.

## Handoff

Return exact device mounts, privileges, environment variables, health commands,
and platform constraints for Task 09. A standalone autonomy Compose file with
`FCU_URL` is not acceptable evidence for this task.

