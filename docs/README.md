# Project documentation

- [System design](design.md): workflow, application boundaries and open decisions.
- [Milestone 1](milestone1.md): scope, acceptance criteria, reproduction settings,
  measured simulator results and evidence locations. Selected simulator acceptance
  is complete; physical-boat performance remains unverified.
- [Boat execution](boat_execution.md): mission protocol, command ownership,
  completion and fault behavior; [boat guide](../boat/README.md) for commands.
- [GCS guide](../gcs/README.md): editing/approval, telemetry configuration,
  UDP/serial setup, filtering and validation limits.
- [Simulator guide](../simulation/README.md): setup, operation, manual GCS tracking,
  performance, optional cameras, troubleshooting and maintenance.
- [Hardware knowledge](hardware.md): retained configuration and hardware notes.
- [Competition course](<competition_docs/AIMM-ICC Competition Course Details 12-13 2025.pdf>)
  and [rules](<competition_docs/Rules and Regulations _ AIMM ICC.pdf>): source documents.

## Maintaining documentation

Update the relevant guide when behavior changes. Keep scope and acceptance
results in the milestone, interfaces in the component references, and commands
in application/simulator guides. Create a new document only for a distinct topic
that needs its own maintained reference. Do not add per-task handoff, completion,
cleanup or validation reports. Keep detailed run artifacts under ignored
`simulation/logs/`; link important evidence and summarize its limits in the
existing reference. Git history preserves superseded plans and reports.

## Repository history

The 2026-10-27 migration retained the simulator, renamed `Simulation/` to
`simulation/`, removed the adapter/legacy autonomy, mapping, Nav2 and monitoring
stack, and introduced independent boat/drone/GCS/shared areas. Local data was
retained under `simulation/logs/`, including `pre-revamp-monitor/`. The original
baseline was `b1851a097f9715c9b0362cc2d3449f9ea681e33b`; migration documentation
was committed in `5e2bdba`. The historical archive branch was left unchanged.

Migration static validation passed (34 tests, one sandbox GPU skip; four GPU
tests passed with host visibility); no final live rebuild/control acceptance was
claimed at that checkpoint. Evidence: `simulation/logs/revamp-final-validate.log`
and `revamp-verify-rgbd*.log`. Later milestone results supersede that checkpoint;
drone remains a scaffold. Removed migration reports remain in Git history.
