# Onboard Autonomy

One ROS 2 workspace (`ros_ws/`) and one autonomy service are shared between
simulation and the vessel. Currently only `maritime_bringup` exists: it launches
MAVROS and provides a read-only flight-controller connectivity health check.
Perception, mapping, navigation, mission management, and ZED drivers are not yet
implemented here. The image has no Gazebo bridge or simulation evaluation tools.

## Simulation

Run `SCENARIO=gate make run` from `../Simulation/`. Its Compose configuration
starts Gazebo/SITL, the adapter, and autonomy. MAVROS keeps the existing `/mavros`
namespace, source ID 255, target 1/1, and UDP 14552 connection. It does not arm
or move the vessel just by starting.

## Independent startup

From the repository root, with the intended flight controller already reachable:

```bash
FCU_URL='udp://:14552@' docker compose -f deployment/compose.autonomy.yaml up --build
```

This URL is the existing simulation listener example, not a prescribed physical
boat connection. Set `FCU_URL` explicitly for the actual transport. For a serial
FCU, device mapping and permissions also need a hardware-specific Compose override;
none is assumed or enabled here. Do not run this alongside the simulation-managed
autonomy service: they use the same container name and would compete for the FCU.

Stop using `Ctrl+C`, then remove the stopped service with the same Compose file
and `FCU_URL` setting followed by `down`. The independent service has no dependency
on Gazebo, the adapter, `/clock`, or a scenario manifest.

`AUTONOMY_IMAGE` overrides the default `maritime-autonomy:jazzy` image name.
The current Dockerfile is a ROS Jazzy integration baseline, not a validated Jetson
Orin Nano/ZED image. JetPack, capture-card drivers, ZED SDK, GPU access, and physical
camera integration need separate verification. Shared source does not require
identical desktop and Jetson binary images.

MAVROS retains the pre-extraction time and disabled local-position TF settings.
The fresh extraction build uses MAVROS 2.15.1 (the prior cached image had 2.14.0).
Its root launch namespace accounts for the newer topic naming behavior so public
interfaces remain `/mavros/...`. ROS apt packages are not pinned in this baseline;
rebuilds require the regression suite, especially when MAVROS changes.
Future state integration must own the estimated navigation transforms and align
sensor/state timestamps; perfect simulator motion must never fill that gap.
