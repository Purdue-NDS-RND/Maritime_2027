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
`container/start-sim.sh` owns simulator process order, logs, readiness, and shutdown.

For ROS runs the host launcher starts the simulator, waits for its healthcheck,
then starts the Adapter and waits for semantic health before starting the
bootstrap. Each handoff has a `STACK_STARTUP_TIMEOUT` deadline (180 seconds by
default). Adapter health requires fresh OK camera source diagnostics when the
camera is enabled, plus MAVROS source and FCU readiness; node presence alone is
insufficient. Bootstrap health remains a process-liveness check and never
implies mission readiness.

The launcher monitors service exits and sustained unhealthy status throughout
the run. A failed handoff or runtime service failure stops the complete stack.
`Ctrl+C`, termination, and `make down` also stop the stack and remove its
recorded temporary Xauthority file. Ordinary logs and SITL state are retained.
`WIPE_PARAMS=1` remains the explicit way to reset virtual EEPROM for a launch.

Each launch exports a unique `RUN_ID` and a `RUN_CONFIG_SHA256` identifying its
saved resolved Compose configuration. `logs/runs/$RUN_ID/` contains
`compose.yaml`, `identity.txt`, `services.log`, and failure evidence when
applicable; ROS launches also save `scenario.manifest.json`. The simulator's
`logs/last-run.txt` records the run ID and configuration hash. The resolved
configuration can contain environment values: keep these generated artifacts
out of Git. Direct `WORLD` launches generate a fresh empty truth roster rather
than reuse a previous scenario's manifest.

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
| `STACK_STARTUP_TIMEOUT` | `180` | Positive integer seconds per simulator/Adapter/bootstrap startup handoff |
| `SIM_IMAGE` | `ardupilot-blueboat:4.7.0` | Local Docker image tag |

## Water profiles

Both worlds instantiate the same WavesModel system. The mild world uses a
single 0.08 m, 3 s sinusoid. The calm world uses zero amplitude. Keeping the
wavefield present in both worlds is essential: BlueBoat's hydrodynamics system
looks up the wavefield to calculate buoyancy and drag.

## Health versus acceptance

The Compose healthcheck proves Gazebo, ArduRover, and MAVProxy processes exist
and that two live world-clock samples show advancing simulation time. It does
not prove navigation.
`make smoke` is the semantic acceptance test for controller identity, parameter
configuration, movement, Hold, RTL, and disarm.

Run `make lifecycle-smoke` explicitly from `Simulation/` with the simulator
stopped. It invokes `tests/lifecycle_acceptance.py`; this acceptance harness is
never part of runtime startup. It launches separate simulation runs to exercise
bounded failed Gazebo/Adapter startup, required-child exit, camera/FCU silence,
SIGINT/SIGTERM cleanup, and parameter persistence. Test-only injections include
a wrong SITL MAVROS output port (14559), stopping the camera boundary or MAVROS
node, and an incompatible direct-world readiness case. Startup and silence
waits are bounded; production readiness retries and data thresholds are unchanged.

The parameter case changes only the benign `LOG_DISARMED` setting, verifies
retention across a normal restart and reset with `WIPE_PARAMS=1`, then restores
the original stopped SITL EEPROM on exit (or removes test-created EEPROM if
none originally existed). Results and launcher logs are saved under
`logs/lifecycle-<UTC>/`; a passing outcome requires clean containers, ports, and
temporary display credentials. These are simulation lifecycle tests, not
hardware or application-readiness evidence.

## Deferred work

The current ROS extension provides simulation bridges, camera normalization,
MAVROS, diagnostics, explicit evaluators, and the non-commanding bootstrap.
Perception, state integration, mapping, navigation, missions, and the Hardware
Adapter remain later work. Preserve the ArduPilot/Gazebo foundation and the
implemented Adapter boundary when adding those application layers.
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
- Maintain bridges, MAVROS, and Adapter diagnostics in
  `Adapter/simulation/ros_ws/`; maintain explicit evaluators in
  `Simulation/tests/evaluation/`. `autonomy/ros_ws/` must build without Gazebo,
  MAVROS, FCU transport, scenario manifests, or evaluation dependencies. The
  current bootstrap is simulation-only and not an independent startup service.
- Keep perfect motion TF on `/blueboat/ground_truth/tf` and its evaluation-only
  static companion. Do not feed it into the shared navigation TF tree.
- OpenCV ArUco logic belongs only in `sensor_smoke.py`, never in bringup.
- Run `make validate` before building and `make verify-rgbd` after changes that
  affect models, scenarios, bridges, frames, or MAVROS.
