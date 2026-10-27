# Optional camera assets

The `single` model has a forward RGB-D camera. `dual` has two cameras at yaw
-45/+45 degrees, x=0.35 m, y=-0.10/+0.10 m, z=0.40 m in body coordinates.
Both preserve the upstream boat dynamics. Camera payload SDF files retain the
simulated optics, resolution (1280 x 720), and mounts. These are not measured
physical-camera calibrations.

Use `BOAT_MODEL=dual SCENARIO=gate make run`, or select a layout in the menu.
An explicit model also equips direct worlds. Cameras publish Gazebo topics;
there is no ROS bridge or normalized ROS camera interface. Capture defaults to
15 simulation Hz; `CAMERA_FPS=30` restores the previous cadence (valid 8..60).

These assets are retained for simulator use and possible future task work.
The new boat route executor has no initial camera dependency.
