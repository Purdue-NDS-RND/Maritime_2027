# Task 12: Run Final Integration Verification

**Goal:** Produce reproducible evidence that the complete pre-implementation
migration works end to end without overstating unsupported hardware or mapping
capability.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 10.

**Prerequisites:** Tasks 01–11 integrated and reviewed. Requires Docker daemon,
display/Gazebo support where applicable, and permission to run the local stack.

**Exclusive write scope:** Runtime output under ignored `Simulation/logs/`, a
new `Simulation/docs/PRE_IMPLEMENTATION_MIGRATION_VERIFICATION.md`, and checkbox
status in `docs/Things_To_Fix_Before_Implementation.md` supported by evidence
from this run. Do not change production code or weaken tests. Any defect returns
to its owning task.

## Required Work

1. Record Git revision, image/package versions, selected scenario, Adapter,
   configuration, ports, and test environment.
2. From `Simulation/`, run `make validate` before building.
3. Build the Simulation Adapter and autonomy from clean layers; inspect
   dependency placement and GeographicLib installation. Record the Hardware
   Adapter as deferred, not built or verified.
4. Start the ROS simulation profile and exercise UDP `14552` through the
   Simulation Adapter.
5. Record separate evidence for process liveness, RGB/depth/`CameraInfo`, generic
   frames/topics, MAVROS connection and required telemetry, autonomy boundary,
   and truth isolation.
6. Run `make verify-rgbd` and focused Simulation Adapter contract tests. Record
   Hardware Adapter contract tests as deferred.
7. Run the simulation-only neutral command smoke and verify disarm cleanup.
8. Run `make down`, then inspect containers, relevant processes, publishers,
   ports, logs, and retained SITL state.
9. If perception/state/mapping now exist, run the agreed manually piloted mapping
   scenario with all four categories and two same-category buoys. Otherwise mark
   that checklist item blocked by its stated prerequisite rather than failed or
   passed.
10. Update checklist boxes only when the report links them to passing evidence;
    leave failed, blocked, and unverified items unchecked with a concise status
    note.

## Acceptance

- The report includes each command, timestamped result, semantic observation,
  relevant log/artifact path, and cleanup result.
- Clean builds prove ownership rather than inheriting old image layers.
- A healthy container, resolved Compose file, source inspection, or single image
  is never reported as end-to-end success.
- Intermittent RGB-D throughput below the existing 8.00 synchronized-pairs/sec
  threshold remains a failure and is recorded; the threshold is not lowered.
- Hardware checks not run on actual hardware are labeled unverified.
- Final `git status --short` and `git diff --check` are recorded, with generated
  logs and ROS cache/build output excluded from commits.

## Handoff

Return a pass/fail/blocked matrix for every section of the source checklist and
link each claim to its evidence. Do not mark the whole migration complete while
any required, prerequisite-satisfied item remains failed.
