# RGB-D buoy scenarios

`one.json`, `gate.json`, `multi.json`, `repeated_red.json`, and `slalom.json` are the editable
source of truth for the RGB-D test worlds. Each buoy has a unique, stable entity
name, a category marker ID, a nominal pose, and optional symmetric jitter
limits. Marker IDs may repeat: `repeated_red.json` contains two separate red
entities that both use marker ID 1. Launch the nominal layout with
`SCENARIO=gate make run`, or a reproducible randomized layout with
`SCENARIO=gate BUOY_SEED=42 make run`.
Add `WATER=calm`, `WATER=normal`, or `WATER=harsh` to choose water independently
of the buoy layout, for example `WATER=harsh SCENARIO=gate make run`. Explicit
scenario commands without `WATER` retain their original calm-water default.

## Slalom / Dodge practice

Run `WATER=calm SCENARIO=slalom make run`, or select **Slalom** after choosing
water in the setup menu. RGB-D and ROS/MAVROS are enabled automatically.

The fixed layout is inspired by the supplied Dodge reference, rotated so the
boat starts at `(0, 0)` and travels along +X. Gate A is at X=7 m; Gate B is at
X=37 m. Each gate has green at Y=+2 m and red at Y=-2 m (4 m between centres).
Four centreline turns at X=13, 19, 25 and 31 m alternate red/green/red/green.
An illustrative path passes red on the boat's right and green on its left.
The 30 m course, gate widths and spacing are provisional, not official event
dimensions. Gate names live in entity IDs; no course timing/scoring or autonomous
path controller is added. The same shared marked buoy assets are used throughout.

The JSON intentionally has no jitter: `BUOY_SEED` leaves this reference layout
unchanged. Edit its poses to adjust the spacing. Near buoys may hide distant
markers until the boat moves; seeing all eight markers at once is not expected.
The existing camera also clips at 20 m, so the far end becomes visible as the
boat advances. Camera range and boat dynamics are unchanged.

Verification: 23 menu/rendering/water tests and Gazebo SDF validation passed.
`WATER=calm make verify-rgbd` passed the complete regression, including all eight
slalom entities and 24 exact public RGB-D triples with shared TF/FCU readiness.
Logs are retained under `logs/verify-slalom*.{log,txt}` and the standard suite
logs. This verifies scene integration; an autonomous slalom run is not included.

## Scenario implementation

The renderer validates entity names, marker IDs, test-area bounds, and
separation, then writes the untracked world and versioned entity-roster manifest
under `logs/generated-worlds/`. The fixed marker/category mapping is 0=white,
1=red, 2=green, and 3=blue.

Every shared buoy model turns around its vertical axis to face `blueboat` as
the boat moves. Its center stays fixed. This behavior also applies when the
same models are inserted into calm, waves, harbor, or custom worlds at runtime;
those worlds do not acquire additional buoys automatically. Use the marked
`model://aruco_buoy_id0` through `model://aruco_buoy_id3` assets for all buoy
spawns, choosing the ID by color rather than by entity instance.

Scenario yaw and marker-plane fields in the generated manifest describe the
initial pose. Runtime evaluation uses live buoy odometry to locate the rotating
marker. Markers stay upright; visibility still depends on camera view, distance,
and occlusion.

Run `make buoy-tracking-smoke` after building to exercise the real Gazebo
plugin through a full circle for all colors, late boat and buoy insertion, and
coincident target positions. It uses an isolated Gazebo partition and no ROS or
FCU. `make verify-rgbd` includes this test plus camera detection, depth, MAVROS,
and control regressions.
