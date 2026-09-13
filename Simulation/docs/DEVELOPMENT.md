# Design and maintenance

## Runtime chain

```text
make run
  -> scripts/run.sh
  -> Docker Compose
  -> tini -> container/start-sim.sh
  -> Gazebo world + BlueBoat + wave/hydrodynamics plugins
  -> ArduPilot Rover SITL (JSON backend)
  -> MAVProxy -> QGC 14550 and student API 14551
```

`scripts/run.sh` owns host concerns: Docker access, UID/GID mapping, image selection,
GPU selection, display validation, and a temporary Xauthority file.
`container/start-sim.sh` owns container process order, logs, readiness, and shutdown.

## Reproducible sources

The Docker build pins and verifies:

| Source | Revision |
|---|---|
| ArduPilot Rover 4.7.0 | `1511f27194f1dcc3728270883047bdf022b3fd53` |
| ArduPilot Gazebo | `082a0fe231f6e63bc8d1598f1cba461d9e2ea7f5` |
| ArduPilot SITL Models | `25bc38ed8c6c0345840159a8cbc0b02781d52f3c` |
| ASV Wave Sim | `ca8629df4e191235753dfae92ef725d30b923364` |

Do not replace these with a floating branch. For an upgrade, resolve a complete
SHA, update both `container/Dockerfile` and `container/compose.yaml`, rebuild without cache, reset
SITL parameters once, and repeat the full smoke test.

## Environment interface

| Variable | Default | Purpose |
|---|---|---|
| `WORLD` | `blueboat_waves.sdf` | World available through Gazebo's resource path; also supports `blueboat_calm.sdf` and `blueboat_harbor.sdf` |
| `MAVLINK_QGC` | `udp:127.0.0.1:14550` | Host QGroundControl output |
| `MAVLINK_API` | `udp:127.0.0.1:14551` | Independent student/test output |
| `SOFTWARE_RENDERING` | `0` | Use Mesa CPU rendering when set to `1` |
| `WIPE_PARAMS` | `0` | Reset virtual EEPROM when set to `1` |
| `GAZEBO_STARTUP_TIMEOUT` | `90` | Gazebo/BlueBoat readiness deadline |
| `SIM_IMAGE` | `ardupilot-blueboat:4.7.0` | Local Docker image tag |

## Water profiles

Both worlds instantiate the same WavesModel system. The mild world uses a
single 0.08 m, 3 s sinusoid. The calm world uses zero amplitude. Keeping the
wavefield present in both worlds is essential: BlueBoat's hydrodynamics system
looks up the wavefield to calculate buoyancy and drag.

## Health versus acceptance

The Compose healthcheck proves Gazebo, ArduRover, and MAVProxy processes exist
and that a world-clock message can be received. It does not prove navigation.
`make smoke` is the semantic acceptance test for controller identity, parameter
configuration, movement, Hold, RTL, and disarm.

## Deferred work

Do not add ROS 2 or competition-specific behavior to this baseline incidentally.
Future AIMM work should add a separate autonomy layer and course assets while
preserving this known-good ArduPilot/Gazebo foundation.
# RGB-D extension invariants

- Never edit the fetched upstream BlueBoat model. The image build verifies its
  SHA-256 and inserts only `zed2i_camera_visual` and `zed2i_rgbd_camera` into
  the existing `base_link`.
- Keep the camera visual free of collision and inertial elements. Changes to
  hull, mass, thrusters, hydrodynamics, joints, ArduPilot plugin XML, or
  `config/blueboat.parm` are outside this extension.
- Scenario JSON is source; rendered SDF and manifests are disposable output.
- Keep `ros_gz_bridge` directions `GZ_TO_ROS`. MAVROS is the only ROS-side FCU
  command path.
- Maintain bridges and simulation-only evaluations in `Adapter/ros_ws/`; maintain
  MAVROS and onboard packages in `autonomy/ros_ws/`. The latter must build without
  Gazebo dependencies or scenario manifests. Use the shared service definition in
  `deployment/compose.base.yaml` for both simulation and independent startup.
- Keep perfect motion TF on `/blueboat/ground_truth/tf` and its evaluation-only
  static companion. Do not feed it into the shared navigation TF tree.
- OpenCV ArUco logic belongs only in `sensor_smoke.py`, never in bringup.
- Run `make validate` before building and `make verify-rgbd` after changes that
  affect models, scenarios, bridges, frames, or MAVROS.
