# BlueBoat simulation

Preserved Gazebo Harmonic / ArduPilot Rover 4.7.0 simulator: BlueBoat dynamics,
water worlds, buoy scenarios, optional camera assets, SITL and direct MAVLink.
It runs as one application container.

From this directory:

```bash
make validate
make run                         # Calm, cameras off, slalom; terminal setup menu
WORLD=blueboat_calm.sdf make run # Direct world, no camera by default
SCENARIO=gate make run           # Existing Gazebo buoy scene
make smoke                       # Running boat: movement, HOLD, RTL, disarm
make teleop                      # Optional manual keyboard control
make sensor-smoke                # Gazebo RGB-D check in a camera scene
make buoy-tracking-smoke          # Standalone buoy plugin regression
make down                        # Retains logs and SITL state
```

`container/` holds the image and single-service Compose project. `scripts/`
holds launch/control/rendering helpers; `tests/` holds simulator checks. Assets
live in `config/`, `worlds/`, `models/`, `plugins/`, and `scenarios/`. Ignored
`logs/` contains run output, existing recordings, and persistent virtual EEPROM.

Read [setup](docs/SETUP.md), [operation](docs/USING_THE_SIM.md),
[maintenance](docs/DEVELOPMENT.md), [troubleshooting](docs/TROUBLESHOOTING.md),
[camera assets](docs/DUAL_CAMERA.md), and [scenario layouts](scenarios/README.md).
The approximate BlueBoat model does not establish real-boat dynamics or clearance.
