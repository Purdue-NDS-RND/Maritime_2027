# ArduPilot BlueBoat Docker Simulator

Launch an autonomous surface boat simulation with one command:

```bash
make run
```

Gazebo Harmonic simulates the official Blue Robotics BlueBoat model, mild
surface waves, buoyancy, hydrodynamic drag, IMU data, and twin-thruster motion.
ArduPilot Rover 4.7.0 runs its real boat-control code in software-in-the-loop
(SITL). QGroundControl runs on the Ubuntu host and connects as if this were a
physical boat.

This is a reusable ArduPilot baseline. Optional RGB-D buoy scenarios add one
generic simulated RGB-D camera, ROS 2 Jazzy, Gazebo-to-ROS bridges, and MAVROS
without changing the boat dynamics. They intentionally do not include a
two-camera model, perception, mapping, navigation, autonomy, a GCS, payload
mechanisms, or a digital twin of the competition LPV.

## What starts

- **Gazebo Harmonic** opens `blueboat_waves.sdf` and displays BlueBoat on an
  8 cm regular wave.
- **ASV Wave Sim** calculates the water surface, buoyancy, and hydrodynamics.
- **ArduPilot Rover SITL** uses boat frame class 2 and skid-steer motor output.
- **MAVProxy** forwards MAVLink to QGroundControl on UDP `14550` and student
  programs on UDP `14551`.
- Timestamped logs and virtual controller state are saved under `logs/`.

With `SCENARIO=one|gate|multi`, a second container also starts ROS 2 Jazzy,
MAVROS on dedicated UDP `14552`, RGB and registered depth bridges, camera info,
TF, simulation clock, and evaluation-only ground truth.

QGroundControl stays outside Docker. On this workstation it is located at:

```text
/home/ppatel/Applications/QGroundControl-v5.1.4-x86_64.AppImage
```

## Start here

1. Complete [the one-time setup](docs/SETUP.md).
2. Start QGroundControl on the host.
3. Open a terminal in `Simulation` and run:

   ```bash
   make run
   ```

4. Wait for Gazebo to show BlueBoat and for QGroundControl to connect.
5. In a second terminal, prove autonomous navigation works:

   ```bash
   make smoke
   ```

6. Stop the terminal running `make run` with `Ctrl+C`.

The first image build downloads and compiles Gazebo plugins and ArduPilot, so
it can take considerable time and disk space. Later starts reuse the image
`ardupilot-blueboat:4.7.0`.

## Main commands

```bash
make run       # Build if needed and start the GUI simulation
make build     # Build/update the image without starting Gazebo
make rebuild   # Build from scratch without Docker's build cache
make validate  # Check scripts, assets, pins, and Compose configuration
make smoke     # Test a running boat through MAVLink UDP 14551
make ros-build # Build the optional ROS 2 Jazzy sidecar
make sensor-smoke # Check RGB-D, ArUco visibility, depth, timing, and TF
make mavros-smoke # Check the FCU control path through MAVROS
make verify-rgbd  # Run the complete scenario and control regression suite
make logs      # Follow the running container's output
make down      # Stop/remove the container; keep logs and controller state
```

For the RGB-D test gate, use one command:

```bash
SCENARIO=gate make run
```

Other layouts are `one` and `multi`. Add `BUOY_SEED=42` for repeatable pose
randomization. See [RGB-D and buoy scenarios](docs/RGBD_AND_BUOY_SCENARIOS.md)
for topics, frames, tests, and boundaries.

For calm water, use:

```bash
WORLD=blueboat_calm.sdf make run
```

For a rougher harbor exercise with a collidable dock, use:

```bash
WORLD=blueboat_harbor.sdf make run
```

The harbor world uses 0.25 m wave amplitude (0.5 m peak-to-trough) and places
BlueBoat about 11 m from an 18 m fixed dock. It is intended for docking,
station-keeping, and later perception experiments; the standard smoke-test
tolerances are calibrated for the default mild-wave world.

For CPU rendering when GPU access is unavailable:

```bash
SOFTWARE_RENDERING=1 make run
```

To discard saved SITL parameters on one start:

```bash
WIPE_PARAMS=1 make run
```

## Project layout

```text
Simulation/
├── Dockerfile                 # Reproducible pinned simulator image
├── compose.yaml               # Container, networking, display, state, health
├── compose.gpu.yaml           # Adds /dev/dri when available
├── run.sh                     # Host checks, image build, display authorization
├── start-sim.sh               # Gazebo-first startup and process supervision
├── smoke-test.py              # Guided/Hold/RTL autonomous acceptance test
├── Makefile                   # Student-facing command surface
├── config/blueboat.parm       # Boat-specific ArduPilot parameters
├── worlds/                    # Mild, calm, and rough harbor worlds
├── models/                    # Opt-in RGB-D BlueBoat and ArUco buoys
├── scenarios/                 # Editable deterministic JSON layouts
├── ros2_ws/                   # ROS bridges, MAVROS bringup, test-only checks
├── docs/                      # Setup, operation, troubleshooting, maintenance
└── logs/                      # Runtime logs and persistent virtual EEPROM
```

## Model limitation

The official BlueBoat model is useful for ArduPilot integration and autonomy
development, but its hull hydrodynamics are approximate. It must not be used to
predict the AIMM LPV's payload capacity, turning radius, trim, stopping distance,
or trolling-motor performance.
