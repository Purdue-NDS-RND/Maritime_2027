# Task 08: Cut Over Shared Autonomy Ownership

**Goal:** Remove environment-facing runtime ownership from autonomy and replace
the MAVROS-only container process with the bounded simulation bootstrap
placeholder authorized for this milestone.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 2, "Shared Autonomy
Cleanup and Real Bringup."

**Prerequisites:** Task 06 approved. Task 07 is deferred outside the
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
  configuration, except for the explicitly named simulation bootstrap.
- Replace the current MAVROS-only container command with a
  `preimplementation_placeholder` bootstrap node and a process-level liveness
  check. It must require both `ADAPTER_ENVIRONMENT=simulation` and
  `MARITIME_PREIMPLEMENTATION_PLACEHOLDER=1`, and exit non-zero for any other
  environment or a missing opt-in.
- The placeholder must publish no vehicle command and invoke no command-capable
  MAVROS service. Its diagnostics must identify the placeholder and keep mission
  readiness false; liveness must not be presented as application readiness.
- Do not use `sleep`, `tail`, or an unlabeled inert process to keep the
  container alive.

## Acceptance

- Image and package inspection proves all prohibited dependencies and settings
  are absent.
- The named placeholder starts only with the two explicit simulation opt-ins and
  fails closed otherwise. It has no vehicle-command publisher or
  command-capable MAVROS client, and its diagnostic mission readiness is false.
- Stopping the application process makes liveness fail.
- The container does not claim placeholder liveness as application, perception,
  mapping, navigation, or vessel readiness.

## Handoff

Give Task 09 the exact command, liveness probe, opt-in variables, diagnostic
reason, and startup timeout. This commit must merge atomically with Task 09's
Adapter selection and readiness changes.
