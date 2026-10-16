# Onboard Autonomy

This image contains no MAVROS runtime, GeographicLib datasets, FCU transport,
Gazebo bridge, camera driver, scenario manifest, or simulation evaluator.

The default service still runs only the named `maritime_bringup`
simulation bootstrap placeholder. It starts only with both
`ADAPTER_ENVIRONMENT=simulation` and
`MARITIME_PREIMPLEMENTATION_PLACEHOLDER=1`; otherwise it fails closed. Its
diagnostic is intentionally warning-level, publishes no vehicle commands, and
reports mission readiness false.

`maritime_perception` adds an explicitly launched RGB-to-ArUco-box detector.
`maritime_localization` contains interfaces for future depth and RGB
triangulation methods; neither positioning method is implemented. These packages
have no simulator, truth, or vehicle-transport dependency. The detector is not
added to the default simulation startup. See the
[benchmark development guide](../Simulation/docs/BUOY_BENCHMARKS.md) for build,
replay, and offline processing commands.

Run it only through the Simulation profile:

```bash
cd ../Simulation
SCENARIO=gate make run
```

The Simulation Adapter owns `/mavros/...`, MAVLink v2, source system 255,
target 1/1, and UDP 14552. There is no standalone autonomy Compose profile and
no supported hardware startup. A real environment-neutral autonomy application
must replace the placeholder before integrated autonomy or vessel-readiness
claims. Explicit detector tests do not establish mission readiness.
