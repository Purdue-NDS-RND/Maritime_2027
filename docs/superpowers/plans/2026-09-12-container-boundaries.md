# Simulation Adapter Separation Implementation Plan

> Execute inline using the executing-plans workflow; review the resulting diff
> and run the existing semantic regression suite before claiming completion.

**Goal:** Separate simulation-only ROS adapters from reusable onboard autonomy.

**Architecture:** `Simulation/` owns Gazebo and SITL. `Adapter/` owns Gazebo-to-ROS
translation and simulation evaluation. `autonomy/` owns MAVROS and future autonomy
packages. GCS remains planned. Shared deployment configuration must allow autonomy
to start without any simulator service.

**Tech stack:** Existing ROS 2 Jazzy, Docker Compose, Python launch files, Gazebo,
ArduPilot SITL. Jetson/ZED build integration is outside this extraction.

**Spec:** [High-Level Design](../../High_Level_Design.md), updated with this split.

## Constraints

- Preserve upstream pins, boat dynamics, camera calibration, and MAVLink ports.
- Preserve `Simulation/` Make targets and simulation-only evaluation behavior.
- Do not ship Gazebo packages or evaluation/control smoke tests in autonomy.
- Keep truth TF off the shared navigation TF topics.
- Do not launch tests against physical hardware or claim Jetson readiness.

## Tasks

- [x] Add `tests/test_container_boundaries.py`: resolve real Compose configurations
  and assert independent autonomy deployment, three simulation-profile services,
  no manifest mounts on autonomy, and valid independent Docker build contexts.
  Run `python3 -m unittest discover -s tests -v` and observe failure before edits.
- [x] Move the existing ROS workspace and Dockerfile into `Adapter/`; remove the
  MAVROS server from its launch and dependencies, retaining MAVROS message types
  for the simulation-only acceptance test. Split adapter/FCU health checks.
- [x] Add `autonomy/ros_ws/src/maritime_bringup/` with a parameterized MAVROS launch
  and connection health check, plus `autonomy/container/Dockerfile`. Require an
  explicit FCU URL in standalone deployment; preserve the SITL default in sim.
- [x] Add independent `deployment/compose.autonomy.yaml` and have it and simulation
  extend `compose.base.yaml`. Update build discovery, Make targets, verifier health waiting, and static
  validation paths. Use new image names to avoid reusing the old combined image.
- [x] Move truth transforms to evaluation-only topics, remap the existing sensor
  evaluator to those topics, and leave camera extrinsics available separately.
- [x] Update HLD, contributor guidance, simulator operational docs, and component
  READMEs. Clearly distinguish implemented MAVROS plumbing from future autonomy.
- [x] Run unit checks and `make validate`, build ROS-profile services, run
  `make verify-rgbd`, inspect logs and the final diff, and confirm cleanup. Record
  any build/runtime limitation explicitly rather than treating static checks as
  end-to-end success.

## Verification Outcome

Implementation and checks are recorded in
[the verification report](../../../Simulation/docs/CONTAINER_SPLIT_VERIFICATION.md).
The full RGB-D suite remains failing on intermittent evaluator throughput;
thresholds were not relaxed. Build, static, cross-container boundary, MAVROS
control, and independent original boat-control checks passed. Jetson/ZED
integration and evaluator performance follow-up are not claimed complete.
