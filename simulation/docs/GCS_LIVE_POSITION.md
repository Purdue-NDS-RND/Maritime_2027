# Test live boat tracking in the web GCS

This checks simulator → MAVLink → GCS backend → browser movement and heading.
It uses keyboard driving, so it does not require a calibrated mission profile,
change route approvals or repeat full autonomous slalom acceptance.

## Start the simulator

Run from `simulation/` in a desktop terminal:

```bash
CAMERAS=off WATER=calm SCENARIO=slalom make run
```

Use the canonical `maritime-sim:latest` image built from this checkout.
See [setup](SETUP.md) to
build the simulator on another machine. Wait for Gazebo and ArduPilot readiness.

Leave the boat application stopped during keyboard driving: both use UDP 14551.
The GCS reader uses UDP 14550. Close another ground station on 14550 or configure
separate forwarded outputs. No simulator port changes are needed for this test.

## Start the GCS

In a second terminal, from the repository root:

```bash
make -C gcs build
make -C gcs run
```

If the canonical GCS image is already built, only `make -C gcs run` is needed.
Open <http://localhost:8080>. The saved workspace loads if present. On a fresh
checkout, an imported course map/route must be prepared separately; the live
boat marker itself does not require a map import. Manual panning/zooming may be
needed if the boat is outside the current view.

Expect **Live boat position**, an amber boat symbol with an obvious bow/forward
arrow, and a permanent compass/degrees label. The symbol has a fixed screen
size and does not represent a measured hull footprint or clearance margin.
**Boat mission API stale / unavailable** is expected with the boat app stopped.

Before starting keyboard control, check the backend if needed:

```bash
curl -s http://localhost:8080/api/telemetry | python3 -m json.tool
```

Expect `connection_state: live`, `stale: false`, current coordinates, and fresh
heartbeat/position ages. `/api/telemetry/events` is the 5 Hz browser stream.

## Drive and observe

In a third terminal, from `simulation/`:

```bash
make teleop
```

Set `SIM_IMAGE` to the same simulator image if you selected one above. Keep the
teleop terminal focused; its host keyboard reader can receive keys even while
another window is focused. Exit with Q before typing in other terminals.

- R selects ACRO and requests arming. Wait for confirmation; resolve reported
  pre-arm failures rather than bypassing them.
- Hold W/S for forward/reverse and A/D to steer. Release movement keys for neutral.
- H requests HOLD; Q exits, requests HOLD/disarm and reports confirmation.

Watch Gazebo and the browser side by side. The marker should move with the
reported boat position, and its bow/arrow and numeric label should follow
heading. It is not snapped to the planned route. Unknown heading displays a
question-mark circle instead of an invented direction.

## Test loss and recovery

Exit teleop with Q and confirm disarm first. From `simulation/`:

```bash
make down
```

Within roughly 3 s without heartbeat/position, the GCS should mark telemetry
stale and grey the last known position. Restart the simulator using the same
launch configuration. Fresh telemetry should recover without a movement
command. A reconnect can clear cached position briefly until a new sample.

## Stop the GCS

From the repository root:

```bash
make -C gcs down
```

Autonomous Upload/Start is a separate test through the boat app. The retained
2 m/s slalom approval requires its measured gains, geometry identity, telemetry
rate and correct scene; merely starting the boat service does not stage those
settings. See the [milestone handoff](../../docs/milestone1_handoff.md) for the
recorded autonomous workflow and validation limits. Radio setup is in the
[GCS README](../../gcs/README.md); physical radio tests remain outstanding.
