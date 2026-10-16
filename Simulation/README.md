# ArduPilot BlueBoat Docker Simulator

Launch an autonomous surface boat simulation with one command:

```bash
make run
```

Choose a world from the terminal menu: mild waves, calm water, harbor/dock,
one buoy, a red/green gate, multiple buoys, repeated red buoys, or camera only.
Press Enter for the mild-wave default, or `q` to cancel. Buoy scenarios ask
for an optional integer randomization seed and automatically enable ROS/MAVROS.
Boat-only worlds offer an optional ROS/MAVROS connection.

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

For ROS replay through ArUco detection/localization nodes and saved results, see
[Buoy benchmark development](docs/BUOY_BENCHMARKS.md). Depth and triangulation
positioning are not implemented yet.

- **Gazebo Harmonic** opens `blueboat_waves.sdf` and displays BlueBoat on an
  8 cm regular wave.
- **ASV Wave Sim** calculates the water surface, buoyancy, and hydrodynamics.
- **ArduPilot Rover SITL** uses boat frame class 2 and skid-steer motor output.
- **MAVProxy** forwards MAVLink to QGroundControl on UDP `14550` and student
  programs on UDP `14551`.
- Timestamped logs and virtual controller state are saved under `logs/`.

With `SCENARIO=one|gate|multi|repeated_red`, the ROS profile starts the Simulation Adapter,
its MAVROS endpoint on UDP `14552`, normalized RGB-D/camera-info interfaces,
TF, simulation clock, the non-mission autonomy bootstrap, and evaluation-only
ground truth.

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

4. Choose a world (Enter for mild waves), then wait for Gazebo to show BlueBoat
   and for QGroundControl to connect.
5. In a second terminal, exercise the simulator control acceptance test:

   ```bash
   make smoke
   ```

6. Stop the terminal running `make run` with `Ctrl+C`.

The first image build downloads and compiles Gazebo plugins and ArduPilot, so
it can take considerable time and disk space. Later starts reuse the image
`ardupilot-blueboat:4.7.0`.

## Main commands

```bash
make run       # Choose a world, build if needed, and start the GUI simulation
make build     # Build/update the image without starting Gazebo
make rebuild   # Build from scratch without Docker's build cache
make validate  # Check scripts, assets, pins, and Compose configuration
make smoke     # Test a running boat through MAVLink UDP 14551
make teleop    # Arm and drive with the keyboard through pymavlink; QGC optional
make record    # Open recording, dataset inspection, replay, and RViz menu
make ros-build # Build simulator, simulation adapter, and autonomy images
make sensor-smoke # Check RGB-D, ArUco visibility, depth, timing, and TF
make mavros-smoke # Check the FCU control path through MAVROS
make verify-rgbd  # Run the complete scenario and control regression suite
make lifecycle-smoke # Explicit startup, failure cleanup, and parameter tests
make logs      # Follow the running container's output
make down      # Stop/remove the container; keep logs and controller state
```

For the RGB-D test gate, use one command:

```bash
SCENARIO=gate make run
```

You can also select it from the `make run` menu. Explicit `WORLD` or `SCENARIO`
values skip the menu, so existing commands still work. Redirected input/output
also skips it; automation can use `./scripts/run.sh --non-interactive` to launch
the defaults even in a terminal. Build-only and shutdown commands never prompt.

Other layouts are `one`, `multi`, and `repeated_red` (two visible red-category
buoys). Add `BUOY_SEED=42` for repeatable pose
randomization. See [RGB-D and buoy scenarios](docs/RGBD_AND_BUOY_SCENARIOS.md)
for topics, frames, tests, and boundaries.

For repeatable inputs while developing buoy-position algorithms, see
[recording and replay](docs/RECORDING_AND_REPLAY.md). Record a manual run once,
then replay its sensor, boat-state, and truth messages in ROS and RViz.
`make record` opens the terminal menu for all of these actions. Explicit
`NAME`/`RECORDING` commands remain available for automation.

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
├── Makefile                   # Student-facing command surface
├── container/                 # Image, Compose, and in-container process files
├── scripts/                   # Host launch, validation, and acceptance helpers
├── config/blueboat.parm       # Boat-specific ArduPilot parameters
├── worlds/                    # Mild, calm, and rough harbor worlds
├── models/                    # Opt-in RGB-D BlueBoat and ArUco buoys
├── scenarios/                 # Editable deterministic JSON layouts
├── docs/                      # Setup, operation, troubleshooting, maintenance
└── logs/                      # Runtime logs and persistent virtual EEPROM
```

Use the root Makefile for normal operation. `scripts/` is for host-side
automation, while `container/` holds Docker and in-container startup files.

ROS responsibilities live in sibling project areas: [`Adapter/`](../Adapter/README.md)
owns the Gazebo bridges, MAVROS, and diagnostics; explicit evaluators live in
`tests/evaluation/`. [`autonomy/`](../autonomy/README.md) contains only the
temporary non-mission bootstrap. The simulation `ros` profile starts both
services alongside the simulator; there is no standalone autonomy profile.

## Model limitation

The official BlueBoat model is useful for ArduPilot integration and autonomy
development, but its hull hydrodynamics are approximate. It must not be used to
predict the AIMM LPV's payload capacity, turning radius, trim, stopping distance,
or trolling-motor performance.
