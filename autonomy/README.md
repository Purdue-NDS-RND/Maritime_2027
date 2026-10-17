# Onboard Autonomy

Persistent RGB-only mapping is available through `pipeline.launch.py method:=bearing_ekf`.
See [RGB mapping operation and design](../Simulation/docs/RGB_BUOY_MAPPING.md).
It uses acquisition-time vessel poses, robust bearing initialization, and per-buoy EKFs.

For live teleop observation, leave Simulation bringup unchanged and run
`make -C autonomy mapping-build`, then `make -C autonomy mapping` from the repository
root. This optional foreground session launches detection/mapping plus a top-down
popup with estimated means, covariance ellipses, history and a provisional truth
overlay. It also adds estimates to the existing `make -C Monitor rviz-sim` view.
See [live RGB mapping](docs/LIVE_RGB_MAPPING.md) for commands, timing assumptions,
headless operation and validation.

This image contains no MAVROS runtime, GeographicLib datasets, FCU transport,
Gazebo bridge, camera driver, scenario manifest, or simulation evaluator.

Start navigation here, after starting Simulation and its Adapter:

```bash
make navigation-build
make run ARGS=--evaluate
# For the standalone gate scenario:
make run TASK=gate ARGS=--evaluate
```

`make run` (also named `make navigation`) launches the dual RGB navigator and
its explicit simulation command session. Ctrl-C stops navigation and invokes
HOLD/disarm; Simulation stays up. See [gate and slalom navigation](../docs/GATE_SLALOM_NAVIGATION.md).
Simulation never starts this application or the legacy bootstrap automatically.
The legacy `maritime_bringup` bootstrap remains available only for explicit
preimplementation diagnostics and requires its simulation opt-in flags.

`maritime_perception` adds an explicitly launched RGB-to-ArUco-box detector.
`maritime_localization` supplies Bearing EKF Buoy Mapping: robust multi-view
bearing initialization, a persistent world-track manager, and an independent XY
EKF per buoy. See its [package README](ros_ws/src/maritime_localization/README.md)
for every file, input/output topic, parameter and filter equation.
`maritime_interfaces` defines the shared position/status, map and bearing messages. These packages
have no simulator, truth, or vehicle-transport dependency. The detector is not
added to the default simulation startup. See the
[benchmark development guide](../Simulation/docs/BUOY_BENCHMARKS.md) for build,
ROS replay benchmarks, live-topic launching, and optional offline inspection.

The Simulation Adapter owns `/mavros/...`, MAVLink v2, source system 255,
target 1/1, and UDP 14552. The navigation ROS package has no vehicle transport
or simulator dependency; the host launcher explicitly pairs it with the
simulation-only command bridge. Hardware startup is not supported by this runner.
