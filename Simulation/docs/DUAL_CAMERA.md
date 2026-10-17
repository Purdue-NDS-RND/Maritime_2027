# Selectable camera boats

Development branch: `feature/dual-camera-boat`.

Assumptions: keep the existing forward camera as `single` (default). `dual`
replaces that view with two identical RGB-D cameras: camera_0 yaw -45 degrees
(starboard), camera_1 yaw +45 degrees (port), in ROS body coordinates (x forward,
y port, z up). Both sit at x=0.35 m, z=0.40 m, with y=-0.10/+0.10 m to separate
the visual housings. The upstream boat dynamics, sensor calibration, resolution,
update rate, source pins, and MAVLink ports stay unchanged.

From `Simulation/`, use `BOAT_MODEL=dual SCENARIO=gate make run`; use
`BOAT_MODEL=single` for the forward camera. Interactive setup offers the same
choice. Explicit WORLD/SCENARIO still bypasses the menu. An explicit boat model
equips direct worlds too and enables ROS; water selection remains independent.

Each camera has `/sensors/camera_N/{color/image_raw,depth/image_rect_raw,color/camera_info}`
and `base_link -> camera_N_link -> camera_N_optical_frame` transforms. Simulation
truth stays evaluation-only. Mapping uses RGB, calibration, TF, and vessel motion;
depth and truth are not mapper inputs.

Use the same Monitor command for both layouts: `make -C Monitor rviz-sim` from
repository root. It discovers public camera image/calibration topics and copies
only camera static transforms into its private truth display. Each camera has
its own calibrated image plane/frustum; the second RGB panel waits for data in
single mode.

Use `make -C autonomy mapping` (or `VIEW=none`) for either layout. The shared
pipeline reads the durable `/sensors/camera_roster` metadata during startup;
start it after the Adapter is ready. For an explicit layout in a sourced ROS
shell use `ros2 launch maritime_localization pipeline.launch.py camera_layout:=dual`
(or `single`). The existing `camera` / `second_camera` arguments still work.
Changing layout requires restarting the mapping session, because changing camera
mounts invalidates an existing map. Both detectors feed one mapper and one map;
unknown positions still require enough vessel motion/parallax.

`make record NAME=...` saves the model in the scenario manifest, captures both
RGB-D streams for dual runs, and checks each camera's exact-triple rate against
the unchanged 8 Hz gate. Old recordings without a model field remain single
camera. `make benchmark RECORDING=...` selects both RGB/calibration streams for
dual recordings, starts the shared mapper with that layout, and records both
detection outputs. Depth/truth remain excluded from the benchmark inputs.

A recording made while mapping, both RViz views, and control testing were all
active failed the second-camera 8 Hz gate. An isolated record-only trial passed
both cameras (20.26/13.01 Hz). Use the intended capture-then-replay workflow for
recording; every saved run is still independently checked. Optional live viewers
can add enough load to cause transport loss, and a healthy stack does not
certify recording quality.

With a dual gate run active, use `make dual-camera-smoke` from `Simulation/`
to check both exact RGB-D rates (at least 8 Hz), per-camera frames/calibration,
the -45/+45 degree mounts, and marker visibility on each side. In a world
without buoys use `make dual-camera-smoke ARGS=--camera-only`. The existing
`make verify-rgbd` remains the complete forward-camera scenario regression;
run it with `BOAT_MODEL=single`.

Both layouts, the common RViz launch, live/replay mapping, control behavior,
and all 11 lifecycle cases have passing evidence. See the
[verification record](DUAL_CAMERA_VERIFICATION.md) for commands, results,
build provenance, the initial boundary-probe retry, and recording-load limits.
