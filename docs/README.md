# Project documentation

- [Milestone 1](milestone1.md): current development scope, implementation order,
  and acceptance criteria for camera-free slalom through the web GCS.
- [Milestone 1 handoff](milestone1_handoff.md): implementation, exact runtime
  evidence, failures and remaining acceptance work.
- [Working system design](design.md): agreed workflow, provisional choices,
  first development milestone, and remaining design questions.
- [Boat execution](boat_execution.md): first implementation slice, local mission
  interfaces, execution behavior and validation limits.
- [GCS live position](gcs_live_position.md): passive MAVLink telemetry, UDP/serial
  configuration, oriented map marker, freshness and validation limits.
- [Live tracking test](../simulation/docs/GCS_LIVE_POSITION.md): simulator,
  browser and keyboard-control test, telemetry-loss check and shutdown.
- [Simulator setup](../simulation/docs/SETUP.md): prerequisites and build instructions.
- [Hardware knowledge](hardware.md): retained configuration and prior hardware notes.
- [Simulator documentation](../simulation/README.md): operation and verification.
- [Competition course](<competition_docs/AIMM-ICC Competition Course Details 12-13 2025.pdf>)
  and [rules](<competition_docs/Rules and Regulations _ AIMM ICC.pdf>): source documents.

Boat execution, the minimal GCS and simulator export/evaluation are implemented.
Milestone 1 passed its selected simulator acceptance; physical-boat performance
remains unverified. Drone remains a scaffold.

Historical records: [repository migration](archive/migration_plan.md) and
[migration validation](archive/validation.md). These describe the cleanup, not
the current design or current simulator acceptance.
