# Pre-Implementation Migration Orchestration

## Mission

Complete only the repository migrations listed in
[`Things_To_Fix_Before_Implementation.md`](../Things_To_Fix_Before_Implementation.md).
The outcome is a stable simulation foundation on which perception, state, and
mapping can be implemented: the Simulation Adapter exposes the agreed MAVROS
and camera contracts, simulation truth and evaluators remain outside runtime
autonomy, repeated buoy categories work, and startup and shutdown have
semantic verification. This is preparation for later implementation work, not
a final vessel-deployment or autonomy milestone.

This work does **not** implement perception, mapping, YOLO, navigation, mission
management, autonomous control, or the GCS. Task 08 may use the bounded
simulation bootstrap exception below; it is not an autonomy application and
does not make any of those capabilities implemented.

## Milestone Scope Decision: Hardware Adapter Deferred

As of 2026-09-15, Task 07 is deliberately deferred outside this
pre-implementation simulation-foundation milestone. No `Adapter/hardware/`
scaffold, assumed FCU transport, camera-driver selection, or invented evidence
is an acceptable substitute for it. The MAVROS and camera contracts remain the
future Hardware Adapter's binding interface, but this milestone makes no
hardware or vessel-readiness claim.

Deferral removes Task 07 from the simulation-only Task 08–12 dependency path.

## Temporary Simulation Bootstrap Exception

For this pre-implementation milestone, Task 08 may replace the MAVROS-only
autonomy process with a deliberately named simulation bootstrap placeholder.
It must start only when both `ADAPTER_ENVIRONMENT=simulation` and
`MARITIME_PREIMPLEMENTATION_PLACEHOLDER=1` are set; it must fail closed for any
other environment. It may provide process liveness and an explicit diagnostic
reason such as `preimplementation_placeholder`, but it must publish no vehicle
commands, invoke no command-capable MAVROS service, and report mission
readiness as false. Liveness of this process is never application, perception,
mapping, navigation, or vessel-readiness evidence.

Task 09 must wire the explicit opt-in only for the Simulation Adapter profile;
Task 10 must test the opt-in and fail-closed behavior; Task 12 must record the
placeholder as a limitation. A real environment-neutral application replaces
this exception before any autonomy or vessel capability claim.

## How to Use These Specs

Each `taskNN.md` is a bounded subagent assignment. Give an agent its task file,
the repository `AGENTS.md`, the source documents named by the task, every
approved prerequisite contract, and the handoff blocks from prerequisite
tasks. Require the agent to return its commit, changed-file list, verification
results, and unresolved risks.

Agents may run concurrently whenever all of their individual prerequisites are
approved and their write scopes do not overlap. Use separate Git worktrees or
branches when available. Do not merge a leaf task merely because its local
checks pass; the orchestrator must respect the dependency gates and run Task 12
on the integrated tree.

## Dependency-Driven Ready Queue

```text
Start:   task01  task02  task03                 contracts, parallel
                      ├─ task05 after task03
After 01–03:        task04                    Adapter relocation
                         └─ task06 after task04 + task05
Deferred:            task07                    hardware boundary, future milestone
After 06:           task08                    staged simulation-only autonomy bootstrap cutover
After 04–06 + 08:   task09                    simulation integration and lifecycle
After 09:           task10                    boundary/acceptance tests
After 10:           task11                    current operational docs
After 11:           task12                    clean builds + live verification
```

Task 05 should start as soon as Task 03 is approved, even if Tasks 01 and 02 are
still running. Task 07 is deferred and has no ready-queue position in this
milestone. This ready-queue rule takes precedence over treating the diagram as
fixed batch waves.

Task 08 may use only the temporary simulation bootstrap exception defined
above. A real environment-neutral autonomy application is still required before
any autonomy capability claim or hardware deployment work.

## Staged Integration Procedure

"Approved prerequisite" means its commit is reviewed and available as a parent
or cherry-pick in the dependent task's worktree; it does not always mean the
commit is already merged to `main`.

- Task 04 produces a staging commit. Task 06 branches from that commit.
- Task 08 produces a reviewed autonomy-only staging commit.
- Task 09 creates the integration branch, applies the reviewed Task 04/06,
  Task 05, and Task 08 commits, then adds the shared-file cutover. It does not
  add a Hardware Adapter selection or hardware deployment profile.
- Only the complete Task 09 integration result is eligible to merge to `main`.

This preserves the checklist's atomic relocation and autonomy cutover while
still allowing dependent agents to work from reviewed staging commits.

## Exclusive Ownership

| Task | Exclusive write scope while active |
|---|---|
| 01 | `docs/contracts/mavros_adapter_contract.md` |
| 02 | `docs/contracts/camera_adapter_contract.md` |
| 03 | `docs/contracts/scenario_entity_contract.md` |
| 04 | Adapter directory relocation only |
| 05 | Scenario renderer, scenario fixtures, buoy model assets |
| 06 | `Adapter/simulation/**` and a runnable evaluation environment under `Simulation/tests/**` |
| 07 | Reserved for future `Adapter/hardware/**`; deferred in this milestone |
| 08 | `autonomy/**` |
| 09 | Compose, root simulation orchestration, Make targets, shared startup wiring |
| 10 | `tests/**` and test-only files under `Simulation/tests/**` |
| 11 | Current contributor and operational Markdown |
| 12 | Verification report, runtime evidence, and evidence-backed final checklist status |

Tasks 01–11 must not mark final checklist verification items complete. Task 11
may update current explanatory text but Task 12 owns evidence-backed final
checkbox status. Historical plans and verification reports must not be
rewritten.

## Integration-Owner Files

Only Task 09 may change these after Wave 2 begins:

- `Simulation/Makefile`
- `Simulation/container/compose.yaml`
- `Simulation/container/compose.gpu.yaml`
- `Simulation/scripts/run.sh`
- `Simulation/scripts/validate.sh`
- `Simulation/scripts/verify-rgbd.sh`
- `deployment/compose.base.yaml`
- `deployment/compose.autonomy.yaml`

Task 10 alone owns `tests/test_container_boundaries.py` and
`tests/ros_boundary_smoke.py`. Feature agents must describe required assertions
in their handoff instead of modifying those files.

## Orchestration Rules

1. Begin every task from the same reviewed base revision and record it.
2. Before dispatch, verify that every prerequisite commit is reviewed and
   reachable in the task's worktree. Require a merge to `main` only when the
   staged integration procedure says so.
3. Reject changes outside the task's write scope unless the orchestrator
   explicitly reassigns the file before work begins.
4. Preserve UDP `14552`, MAVLink v2, source system `255`, target `1/1`, root
   `/mavros/...`, boat dynamics, and pinned upstream revisions unless an
   approved contract deliberately changes one.
5. Never expose `/blueboat/ground_truth/...` to autonomy or hardware.
6. Never run command-capable simulation evaluators during normal startup or
   against hardware.
7. Treat container liveness, source readiness, FCU readiness, and mission
   readiness as different results.
8. Run task-local checks before handoff. The orchestrator reviews each diff and
   runs the full ladder only in Task 12.
9. Preserve logs and SITL parameter state on ordinary shutdown, while every new
   autonomy application run starts with empty observation and map state.
10. Do not lower the existing RGB-D evaluator throughput threshold to obtain a
    pass.

## Required Handoff Format

Every subagent returns:

```text
Task: taskNN
Base revision: <commit>
Commit(s): <commit list>
Changed files: <exact paths>
Checks run: <command and result for each>
Interfaces produced or consumed: <exact names>
Known limitations: <concrete items or "none">
Integration notes: <actions reserved for a later task>
```

The orchestrator checks `git diff --check`, scope compliance, contract
compatibility, and semantic test evidence before accepting a handoff.
