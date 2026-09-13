# Things to Fix Before Implementation

This checklist tracks existing-system changes needed to support the
[Low-Level Design](Low_Level_Design.md). Items are recorded for later work;
none are marked complete. Each item states when it becomes necessary so design
work on other sections can continue.

## Simulator Buoy Categories

- [ ] Change the appearance and description of marker 0's buoy from orange to
  white in `Simulation/models/aruco_buoy_id0/`.
- [ ] Change the appearance and description of marker 3's buoy from yellow to
  blue in `Simulation/models/aruco_buoy_id3/`.
- [ ] Check scenario documentation and visual expectations against the agreed
  mapping: 0 = white, 1 = red, 2 = green, 3 = blue.

Required before validating category labels against simulator buoy appearances.
ArUco classification will use marker IDs, not the visible buoy color.

## Repeated Buoy Categories in Simulation

- [ ] Update `Simulation/scripts/render_scenario.py` to allow different buoys
  to share a marker ID while retaining unique simulation entity names.
- [ ] Remove the requirement that an entity name equal `buoy_<marker_id>`;
  keep physical entity identity separate from category-level marker IDs.
- [ ] Audit scenario manifests, launch scripts, and Adapter evaluation clients
  for assumptions that a marker ID uniquely identifies a physical buoy.
- [ ] Add a scenario with multiple buoys of the same category and verify that
  evaluation references distinguish the entities without exposing their
  identities or positions to autonomy.

Required before live simulation acceptance of repeated-category detections
and later mapping association tests. Repeated-category image-fixture tests can
be developed independently.

## Camera Frame Naming

- [ ] Resolve the Adapter's historical `zed2i_*` frame names into the
  camera-neutral convention selected during interface design.
- [ ] Update affected bridge headers, transforms, and evaluation expectations
  together, preserving the separation between navigation and evaluation frames.

Required before autonomy depends on named camera transforms for depth-based
positioning. Initial 2D detection can preserve incoming image headers without
hard-coding those frame names. The replacement naming convention is still open.

## Camera and Vessel-State Timing

- [ ] Inspect and verify the clock behavior of camera observations and MAVROS
  vessel-state messages, including simulation pause and reset behavior.
- [ ] Resolve any timing mismatch under the synchronization policy chosen
  during state-estimation and mapping design.

Required before combining detections, depth, and vessel state. This is a known
verification gap, not a confirmed runtime defect; enabling simulation time on
the detector alone does not establish synchronized inputs.

## Verification After Fixes

- [ ] Run `make validate` from `Simulation/` before building changed images.
- [ ] Run `make verify-rgbd` for changes to models, scenarios, bridges, frames,
  or MAVROS, along with the relevant control and perception acceptance checks.
- [ ] Record semantic results and visual evidence where applicable before
  marking the corresponding fixes complete.

## Scope of This Checklist

Unresolved design choices, including confidence-score semantics, QoS review,
timeouts, and performance targets, remain in the Low-Level Design's
**Open Design Decisions** section. They are not existing-system defects.
Add further integration fixes here as other design sections are developed.
