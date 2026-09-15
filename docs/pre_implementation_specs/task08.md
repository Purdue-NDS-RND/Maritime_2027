# Task 08: Cut Over Shared Autonomy Ownership

**Goal:** Remove environment-facing runtime ownership from autonomy and replace
the MAVROS-only container process with a real, environment-neutral autonomy
application launch.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 2, "Shared Autonomy
Cleanup and Real Bringup."

**Prerequisites:** Task 06 approved. A real environment-neutral perception,
state, or mapping application launch must exist and run useful work. If it does
not exist, this task is blocked by design. Task 07 is deferred outside the
simulation-foundation milestone and is not a prerequisite for this cutover.

**Exclusive write scope:** `autonomy/**`. Do not edit Adapter, Simulation,
deployment YAML, root tests, or operational documentation.

## Required Work

- Remove MAVROS runtime packages, GeographicLib installation, `FCU_URL`, the
  vehicle launch wrapper, and the MAVROS connection healthcheck from autonomy.
- Retain only public message dependencies such as `mavros_msgs` that actual
  autonomy code consumes.
- Add automated dependency checks excluding Gazebo, simulation truth/manifests,
  camera drivers, MAVROS launch/runtime packages, and environment-specific FCU
  transport.
- Make `maritime_bringup` launch only environment-neutral autonomy nodes and
  configuration.
- Replace the current MAVROS-only container command with the real application
  launch and a meaningful process-level liveness check.
- Ensure no `sleep`, `tail`, inert placeholder node, or fake health status is
  used to keep the service alive.

## Acceptance

- Image and package inspection proves all prohibited dependencies and settings
  are absent.
- The application process runs against the Simulation Adapter's public ROS
  interfaces without importing environment-specific packages. Future hardware
  compatibility remains a contract goal, not tested deployment evidence.
- Stopping the application process makes liveness fail.
- The container does not exit immediately and does not claim health merely
  because a placeholder process is running.

## Handoff

Give Task 09 the exact command, liveness probe, required public interfaces, and
startup timeout. This commit must merge atomically with Task 09's Adapter
selection and readiness changes.
