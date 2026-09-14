# Task 01: Freeze the Common MAVROS Contract

**Goal:** Define the single versioned MAVROS interface that both environment
Adapters must implement before any MAVROS ownership migration begins.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 1, "Common MAVROS
Contract."

**Prerequisites:** None. May run in parallel with Tasks 02 and 03.

**Exclusive write scope:** Create
`docs/contracts/mavros_adapter_contract.md`. Do not edit runtime code,
deployment YAML, tests, or the source checklist.

## Required Work

- Record the ROS distribution and controlled MAVROS/MAVROS Extras versions and
  the mechanism that prevents silent rebuild drift.
- Freeze the public root `/mavros/...` namespace, enabled and disabled plugin
  sets, MAVLink v2, source system `255`, target system/component `1/1`, frame
  conventions, and timesync settings unless a reviewed decision explicitly
  migrates a value.
- Enumerate the public telemetry topics, command topics/services, command
  acknowledgments, connection state, and diagnostics that autonomy and a future
  GCS may consume.
- Identify one canonical shared configuration source and list the only allowed
  per-Adapter overrides: transport, physical device access, and
  environment-specific timing.
- Define compatibility and versioning rules, including how an incompatible
  contract change is detected by tests.

## Acceptance

- Every value requested by checklist lines 11–25 has one unambiguous owner and
  value or explicit allowed override.
- Simulation and hardware implementers can configure MAVROS without consulting
  the current autonomy launch file.
- The document names exact observable checks for namespace, plugins, IDs,
  protocol, connection, telemetry, command acknowledgment, and TF behavior.
- `rg -n "TBD|TODO|to be decided" docs/contracts/mavros_adapter_contract.md`
  returns no matches.

## Handoff

Report any current value that could not be verified from repository sources as
an unresolved blocker. Do not silently choose a hardware transport.

