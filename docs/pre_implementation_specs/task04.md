# Task 04: Relocate the Simulation Adapter

**Goal:** Move the flat simulation-only Adapter to `Adapter/simulation/` without
leaving two active layouts.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 2, first Simulation
Adapter checklist item.

**Prerequisites:** Tasks 01–03 approved. May run in parallel with Task 05.

**Exclusive write scope:** Move the existing `Adapter/container/`,
`Adapter/ros_ws/`, and Adapter-specific ignore files into
`Adapter/simulation/`. Update only path references contained inside the moved
subtree. Do not edit shared Compose, Simulation scripts, Makefiles, root tests,
or current documentation.

## Required Work

- Preserve executable modes, package identity, build context contents, and Git
  history visibility through a real move.
- Ensure `Adapter/simulation/container/` and
  `Adapter/simulation/ros_ws/src/blueboat_sim_bringup/` are the only active
  simulation Adapter paths.
- Leave `Adapter/README.md` for Task 11; provide its required changes in the
  handoff.
- Produce an exact path-remapping table for Task 09 covering Docker contexts,
  Compose extensions, validation, Make targets, tests, and documentation.

## Acceptance

- No duplicate `Adapter/ros_ws` or `Adapter/container` remains at the old flat
  location.
- `find Adapter -type f | sort` shows the simulation files only beneath
  `Adapter/simulation/`.
- Package syntax/static checks that do not depend on old external build paths
  pass.
- `git diff --check` passes and Git records the relocation without generated
  ROS workspace artifacts.

## Handoff

Do not merge this staging commit directly to the shared integration branch.
Task 09 must apply the shared path updates in the same integration cutover so
the main branch never retains broken build contexts.

