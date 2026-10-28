# Using the simulator

## Start and stop

Run from the host terminal (QGroundControl is optional):

```bash
make run
```

The terminal menu first asks for water: **calm**, **normal waves** (default), or
**harsh waves**. Then choose the scene: open water (default), harbor/dock, single
buoy, red/green gate, multiple buoys, repeated red buoys, slalom, or camera only. Type
`q` at any prompt to cancel before startup. Invalid answers are re-prompted.
The water choice applies independently to every scene, including buoy scenes.
Presets reuse the existing regular-wave settings: calm amplitude 0 m / period
6 s; normal 0.08 m / 3 s; harsh 0.25 m / 3 s. These are simulation presets,
not calibrated sea-state classifications. Both physics and surface rendering
use the selected parameters. Source world files are never overwritten.

For buoy scenarios, enter an optional integer seed to randomize buoy poses
reproducibly, or leave it blank for the fixed layout. Then select the boat:
**single camera** (forward, default) or **dual camera** (-45/+45 degrees).
An explicit
`BOAT_MODEL=single|dual` selects the same layout without a model prompt; old
explicit world launches without this variable preserve their existing behavior.
See [camera boat selection](DUAL_CAMERA.md).

Commands with an explicit `WORLD` or `SCENARIO` skip the menu. Non-terminal
launches (redirected input or output) keep the existing defaults and never
prompt. Use `./scripts/run.sh --non-interactive` for default startup without a
menu in a terminal. Builds and `make down` also never prompt.

For explicit launches, combine water with a scene:

```bash
BOAT_MODEL=dual WATER=calm SCENARIO=gate make run
WATER=normal SCENARIO=multi make run
WATER=calm SCENARIO=slalom make run
WATER=harsh WORLD=blueboat_harbor.sdf make run
```

Without `WATER`, explicit and noninteractive launches retain their original
world-specific water defaults. Setting only `WATER` in an interactive terminal
skips the water question and opens scene selection. Generated water worlds live
under `logs/generated-worlds/`; each run records the chosen preset in its separate
`water.json`.
Water rendering and menu behavior are covered by retained simulator tests.

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

## Keyboard control through pymavlink

Keep `make run` active and run `make teleop` in another host terminal. It uses
UDP `14551` directly and selects ACRO from any starting mode. QGroundControl
is optional; mode changes and arming are handled by the script.

| Key | Action |
| --- | --- |
| R | Select ACRO and request arming, or resume if already armed |
| W / S | Hold to move forward / reverse |
| A / D | Hold to steer left / right; combine with W or S |
| Shift | Hold for higher speed and turn rate |
| H | Enter HOLD and stop keyboard movement; keep the current arming state |
| M | Select ACRO to resume keyboard control; does not arm |
| X | Request HOLD and disarm |
| Q / Ctrl+C | Exit, request HOLD and disarm, then release RC overrides |

Begin with R, wait for the printed armed/ACRO confirmation, then press movement
keys. Release and press movement keys again after a mode or arming change.
Releasing all movement keys sends neutral throttle and steering. The script
confirms mode and arming through FCU heartbeats and prints arming rejections and
FCU status messages. Pre-arm checks remain enabled; resolve a rejection and
press R to retry.

WASD drives in ACRO, where steering controls turn rate and throttle controls
speed. An external mode change or disarm pauses keyboard movement; use R or M
to take control again. Losing the FCU heartbeat ends teleop and attempts the
same HOLD/disarm cleanup; the script reports if it cannot confirm that state.
Only one program should use the student UDP endpoint at a time, so exit teleop
before running `make smoke`.

The current keyboard reader uses Linux `/dev/input/event*` devices passed into
the teleop container by the Makefile. Run it on the simulator host with a
connected keyboard.

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

Existing recordings are retained in `logs/recordings/`; the old Monitor-dependent
record/replay tooling was removed during migration.

Every run writes:

- `gazebo-<timestamp>.log` for physics, rendering, and plugins;
- `sim-vehicle-<timestamp>.log` for SITL/MAVProxy startup;
- `ardurover-<timestamp>.log` for raw Rover controller output;
- `mavlink-<timestamp>.tlog` for MAVLink telemetry;
- `last-run.txt` identifying the active run's files.

`logs/state/eeprom.bin` preserves parameters between containers. Reset it on a
single start with `WIPE_PARAMS=1 make run`.

### Development telemetry rate

The retained MAVProxy default is 4 Hz. For the measured higher-speed milestone
profiles, explicitly select the matching telemetry rate:

```bash
MAVLINK_STREAMRATE=20 CAMERAS=off WATER=calm SCENARIO=slalom make run
```

Allowed values are 4, 10 and 20 Hz. This changes telemetry delivery, not model
dynamics or controller gains. MAVProxy periodically enforces its launcher rate;
a client message-interval ACK alone does not prove sustained delivery at another
rate. Boat profiles verify observed source frame spacing at upload/start. Record
the selected rate with the run and use the profile's measured rate. Physical
vehicle networking and bandwidth acceptance remain outside this simulation test.
