# RGB-D buoy scenarios

`one.json`, `gate.json`, `multi.json`, and `repeated_red.json` are the editable
source of truth for the RGB-D test worlds. Each buoy has a unique, stable entity
name, a category marker ID, a nominal pose, and optional symmetric jitter
limits. Marker IDs may repeat: `repeated_red.json` contains two separate red
entities that both use marker ID 1. Launch the nominal layout with
`SCENARIO=gate make run`, or a reproducible randomized layout with
`SCENARIO=gate BUOY_SEED=42 make run`.

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
