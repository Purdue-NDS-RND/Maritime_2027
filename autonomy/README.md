# Onboard Autonomy

Persistent RGB-only mapping is available through `pipeline.launch.py method:=rgb_mapping`.
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

The default service still runs only the named `maritime_bringup`
simulation bootstrap placeholder. It starts only with both
`ADAPTER_ENVIRONMENT=simulation` and
`MARITIME_PREIMPLEMENTATION_PLACEHOLDER=1`; otherwise it fails closed. Its
diagnostic is intentionally warning-level, publishes no vehicle commands, and
reports mission readiness false.

`maritime_perception` adds an explicitly launched RGB-to-ArUco-box detector.
`maritime_localization` supplies a shared ROS wrapper and launch file for depth
and temporal RGB triangulation methods. Both produce map XY estimates;
triangulation waits for sufficient translation and parallax.
`maritime_interfaces` defines the shared XY position/status output. These packages
have no simulator, truth, or vehicle-transport dependency. The detector is not
added to the default simulation startup. See the
[benchmark development guide](../Simulation/docs/BUOY_BENCHMARKS.md) for build,
ROS replay benchmarks, live-topic launching, and optional offline inspection.

Run the default bootstrap only through the Simulation profile:

```bash
cd ../Simulation
SCENARIO=gate make run
```

The Simulation Adapter owns `/mavros/...`, MAVLink v2, source system 255,
target 1/1, and UDP 14552. There is no standalone autonomy Compose profile and
no supported hardware startup. A real environment-neutral autonomy application
must replace the placeholder before integrated autonomy or vessel-readiness
claims. Explicit detector tests do not establish mission readiness.
