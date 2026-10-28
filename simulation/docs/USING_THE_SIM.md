# Using the simulator

## Start and stop

Run from the host terminal (QGroundControl is optional):

```bash
make run
```

The terminal menu first asks for water: **calm** (default), **normal waves**, or
**harsh waves**. Then choose the scene: open water, harbor/dock, single
buoy, red/green gate, multiple buoys, repeated red buoys, slalom (default), or camera only. Type
`q` at any prompt to cancel before startup. Invalid answers are re-prompted.
The water choice applies independently to every scene, including buoy scenes.
Presets reuse the existing regular-wave settings: calm amplitude 0 m / period
6 s; normal 0.08 m / 3 s; harsh 0.25 m / 3 s. These are simulation presets,
not calibrated sea-state classifications. Both physics and surface rendering
use the selected parameters. Source world files are never overwritten.

For buoy scenarios, enter an optional integer seed to randomize buoy poses
reproducibly, or leave it blank for the fixed layout. Cameras default to off;
choose on to select single or dual camera layout. The menu also selects telemetry
at 4 (default), 10 or 20 Hz. Environment values skip their corresponding prompts.
The launcher prints all resolved settings before Docker startup. `SIM_GPU` and
`CAMERA_FPS` remain environment controls documented by `scripts/run.sh --help`.
An explicit `BOAT_MODEL=single|dual` enables cameras unless `CAMERAS` is supplied.
See [camera boat selection](DUAL_CAMERA.md).

Commands with an explicit `WORLD` or `SCENARIO` skip the menu. Non-terminal
launches (redirected input or output) use calm water, cameras off and slalom and never
prompt. Use `./scripts/run.sh --non-interactive` for default startup without a
menu in a terminal. Builds and `make down` also never prompt.

For explicit launches, combine water with a scene:

```bash
CAMERAS=on BOAT_MODEL=dual WATER=calm SCENARIO=gate make run
WATER=normal SCENARIO=multi make run
WATER=calm SCENARIO=slalom make run
WATER=harsh WORLD=blueboat_harbor.sdf make run
```

Without `WATER`, all launches use calm water. Setting only `WATER` in an interactive terminal
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

The source waves world uses a regular 0.08 m wave; launches default to calm. To remove wave motion without
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

## Test live GCS tracking

This checks simulator → MAVLink → GCS backend → browser movement/heading using
keyboard control. It needs no measured mission profile or route approval.

1. From `simulation/`, run
   `CAMERAS=off WATER=calm SCENARIO=slalom make run` and wait for readiness.
   Use the canonical image built from this checkout; see [setup](SETUP.md).
   Leave the boat app stopped: teleop owns UDP 14551. Close QGC on UDP 14550
   or give it a separate forwarded output; that port belongs to GCS telemetry.
2. From the repository root, run `make -C gcs build` (if needed), then
   `make -C gcs run`. Open <http://localhost:8080>. The boat marker needs no
   imported course map, though manual panning/zooming may be necessary.
   Expect **Live boat position**, an amber boat with bow/arrow and heading label.
   **Boat mission API stale / unavailable** is expected with the boat stopped.
   The symbol has fixed screen size and does not represent hull clearance.
3. Check `curl -s http://localhost:8080/api/telemetry | python3 -m json.tool`
   if needed. Expect `connection_state: live`, `stale: false`, current
   coordinates and fresh heartbeat/position ages. Events stream at 5 Hz from
   `/api/telemetry/events`.
4. From `simulation/`, run `make teleop`. R selects ACRO and requests arming;
   wait for confirmation, then W/S moves and A/D steers. Release for neutral.
   H requests HOLD. Observe position and heading in Gazebo and the browser.
   Unknown heading uses a question-mark circle. The host keyboard reader can
   receive keys with other windows focused: exit with Q before typing elsewhere.
5. Q exits teleop and requests HOLD/disarm; confirm disarm. Run `make down`
   from `simulation/`. Within roughly 3 s the marker should grey at its last
   known position. Restart with the same launch settings; fresh telemetry should
   recover without movement commands, possibly briefly clearing cached position.
6. Stop with confirmed disarm and `make down` in `simulation/`, then
   `make -C gcs down` from the repository root.

Autonomous Upload/Start is a separate boat-app test requiring explicit measured
profile staging, geometry identity, telemetry rate and scene verification; see
[milestone reproduction](../../docs/milestone1.md#implementation-and-reproduction).
Radio setup is in the [GCS guide](../../gcs/README.md#live-map-telemetry);
physical radio operation remains unverified.
