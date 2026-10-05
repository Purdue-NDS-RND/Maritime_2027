# Using the simulator

## Start and stop

Start QGroundControl on the host, then run:

```bash
make run
```

Gazebo starts first. The launcher waits for an advancing world clock and the
BlueBoat odometry topic before starting Rover SITL. QGroundControl receives
MAVLink on UDP `14550`; student software independently receives it on `14551`.

Stop the attached simulation with `Ctrl+C`. If the terminal was closed or the
Compose display was detached, use `make down`.

## Prove autonomous movement

Keep `make run` active and open a second terminal in the project directory:

```bash
make smoke
```

The test runs inside the simulator container and:

1. confirms an ArduPilot surface-boat heartbeat;
2. confirms the official BlueBoat parameters;
3. switches to Guided and arms;
4. commands a target about 12 m north;
5. verifies meaningful motion and arrival;
6. verifies Hold settles the boat;
7. commands RTL, returns to the starting area, and disarms.

The test prints the stage and live distances. A timeout is a failure, not a
pass. On failure it attempts to enter Hold and disarm before returning.

## Manual control with QGroundControl

QGroundControl should show a surface boat rather than an aircraft. Use its Fly
view to inspect position, heading, speed, arming state, and mode. The simulated
vehicle supports normal Rover/Boat modes such as Manual, Guided, Hold, Auto,
and RTL.

Use the same safety habit as a physical platform: begin disarmed, verify the
selected mode, and keep a clear stop or Hold action available before arming.

## Calm-water troubleshooting

The default world uses a regular 0.08 m wave. To remove wave motion without
removing buoyancy or hydrodynamic forces:

```bash
WORLD=blueboat_calm.sdf make run
```

## Rough-water dock practice

Start the optional harbor world with:

```bash
WORLD=blueboat_harbor.sdf make run
```

This world increases wave amplitude from 0.08 m to 0.25 m and starts BlueBoat
roughly 11 m north of a fixed 18 m dock. The wooden deck and its three pilings
have collision geometry. Yellow edge strips make the dock easier to
distinguish in the Gazebo camera.

Use this world for manual docking, Guided targets near the dock, controller
tuning, or future vision work. Run the automated acceptance test in the
default mild-wave world because its timing and distance thresholds were tuned
for that baseline.

## Logs and state

Every run writes:

- `gazebo-<timestamp>.log` for physics, rendering, and plugins;
- `sim-vehicle-<timestamp>.log` for SITL/MAVProxy startup;
- `ardurover-<timestamp>.log` for raw Rover controller output;
- `mavlink-<timestamp>.tlog` for MAVLink telemetry;
- `last-run.txt` identifying the active run's files.

`logs/state/eeprom.bin` preserves parameters between containers. Reset it on a
single start with `WIPE_PARAMS=1 make run`.
# RGB-D scenarios and MAVROS

Start a complete ROS-enabled gate:

```bash
SCENARIO=gate make run
```

This is still a foreground command. Wait for the simulator, Adapter, and
bootstrap to become healthy, then use another terminal for `make sensor-smoke` or
`make mavros-smoke`. `Ctrl+C` stops Gazebo, SITL, MAVROS, and the ROS bridges.
The launcher waits for simulator health and semantic Adapter source readiness
before starting the bootstrap. Failed startup or a running service failure
stops the complete stack. `make down` also removes the recorded temporary
display authorization file while retaining logs and SITL parameters. Run
identity and resolved configuration are saved under `logs/runs/`; see the
[maintenance guide](DEVELOPMENT.md) for the detailed lifecycle.

Use `SCENARIO=one`, `SCENARIO=gate`, or `SCENARIO=multi`. For reproducible
randomization, add an integer such as `BUOY_SEED=42`. Supplying both `WORLD`
and `SCENARIO` is rejected so the launched environment is never ambiguous.

MAVROS connects to SITL on UDP 14552. Ports 14550 and 14551 retain their
existing QGroundControl and program/test roles. MAVROS does not start a GCS.
