# Onboard Autonomy

This image contains no MAVROS runtime, GeographicLib datasets, FCU transport,
Gazebo bridge, camera driver, scenario manifest, or simulation evaluator.

For this pre-implementation milestone, `maritime_bringup` runs only the named
simulation bootstrap placeholder. It starts only with both
`ADAPTER_ENVIRONMENT=simulation` and
`MARITIME_PREIMPLEMENTATION_PLACEHOLDER=1`; otherwise it fails closed. Its
diagnostic is intentionally warning-level, publishes no vehicle commands, and
reports mission readiness false.

Run it only through the Simulation profile:

```bash
cd ../Simulation
SCENARIO=gate make run
```

The Simulation Adapter owns `/mavros/...`, MAVLink v2, source system 255,
target 1/1, and UDP 14552. There is no standalone autonomy Compose profile and
no supported hardware startup. A real environment-neutral autonomy application
must replace the placeholder before any perception, mapping, navigation, or
vessel-readiness claim.
