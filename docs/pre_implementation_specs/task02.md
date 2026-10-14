# Task 02: Freeze the Common Camera Contract

**Goal:** Define the camera-neutral public interface used by simulation,
hardware, autonomy consumers, and acceptance tests.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 1, "Common Camera
Contract."

**Prerequisites:** None. May run in parallel with Tasks 01 and 03.

**Exclusive write scope:** Create
`docs/contracts/camera_adapter_contract.md`. Do not modify bridge YAML, camera
drivers, autonomy packages, tests, or the checklist.

## Required Work

- Specify `/sensors/camera_N/color/image_raw`,
  `/sensors/camera_N/depth/image_rect_raw`, and
  `/sensors/camera_N/color/camera_info`, plus `camera_N_link` and
  `camera_N_optical_frame`.
- Define accepted color encodings and the canonical registered-depth encoding,
  unit, invalid values, and conversion behavior. Evaluate `32FC1` metres as the
  baseline and record the chosen result.
- Define registration, calibration, distortion, dimensions, optical-frame,
  acquisition timestamp, RGB/depth matching, and `CameraInfo` requirements.
- Define the explicit enabled-camera roster: simulation `camera_0`; hardware
  `camera_0` and `camera_1`. Consumers must enumerate configuration and derive
  dimensions and intrinsics from `CameraInfo`.
- Define startup and runtime diagnostics for absent images, absent or stale
  calibration, frame mismatch, unregistered depth, stale sources, and timestamp
  incompatibility.

## Acceptance

- The contract contains exact message types, encodings, units, frame rules,
  roster representation, timing rule, and failure behavior.
- Nothing in the public contract uses ZED model names or hard-codes 1280x720.
- It explicitly permits initial 2D perception to use generic color input while
  preserving the incoming header.
- `rg -n "TBD|TODO|to be decided" docs/contracts/camera_adapter_contract.md`
  returns no matches.

## Handoff

Return measured evidence for any numerical timestamp or freshness limit. If no
representative measurement exists, identify and run the required measurement
before approval rather than inventing a threshold. The task remains blocked
until an exact tolerance and freshness rule can be frozen.
