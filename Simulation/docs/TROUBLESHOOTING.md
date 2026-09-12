# Troubleshooting

## Docker permission denied

If `docker info` cannot access `/var/run/docker.sock`, your current login does
not have active Docker-group access. Complete the Docker step in `SETUP.md`,
then log out and back in. Do not work around this by running the whole project
with `sudo`; that creates root-owned logs and breaks display authorization.

## Gazebo does not open

Confirm this is the graphical desktop shell:

```bash
printf '%s\n' "$DISPLAY"
xauth nlist "$DISPLAY"
ls -l /tmp/.X11-unix
```

If GPU initialization fails, retry with:

```bash
SOFTWARE_RENDERING=1 make run
```

## BlueBoat appears but SITL never becomes ready

Inspect the current files in this order:

```bash
cat logs/last-run.txt
tail -n 100 logs/gazebo-*.log
tail -n 100 logs/sim-vehicle-*.log
tail -n 100 logs/ardurover-*.log
```

The Gazebo log should show the WavesModel, Hydrodynamics, ArduPilotPlugin, and
BlueBoat odometry. The SITL logs should show the JSON backend connecting.

## QGroundControl does not connect

Verify QGroundControl is running on the host and that another simulator is not
already sending or binding the same ports:

```bash
pgrep -af QGroundControl
ss -lunp | grep -E '14550|14551|9002'
```

Stop stale project containers with `make down`. The drone and boat simulators
must not run simultaneously with their default MAVLink ports.

## Smoke test cannot connect

`make smoke` expects `make run` to remain active in another terminal. Check:

```bash
docker compose -f compose.yaml ps
make logs
```

If the heartbeat arrives but arming or navigation fails, read the ArduRover
log instead of disabling arming checks. For a clean parameter baseline:

```bash
make down
WIPE_PARAMS=1 make run
```

## The boat is too difficult to tune in waves

The harbor world is intentionally much rougher than the default. Return to the
mild baseline or use calm water to distinguish controller problems from wave
disturbance:

```bash
WORLD=blueboat_waves.sdf make run
```

or:

```bash
WORLD=blueboat_calm.sdf make run
```

Warnings from graphics drivers are not automatically fatal. Readiness requires
advancing simulation time, BlueBoat odometry, the JSON connection, Rover
heartbeat, and meaningful MAVLink behavior.
# RGB-D / ROS 2 checks

- If `maritime-sim-adapter` is unhealthy, run
  `docker compose -f compose.yaml --profile ros logs adapter` and confirm
  `/clock` and camera topics appear.
- If `maritime-autonomy` is unhealthy, inspect
  `docker compose -f compose.yaml --profile ros logs autonomy` and confirm
  `/mavros/state` reports a connected flight controller. These are separate
  health checks; neither alone proves end-to-end control.
- If MAVROS never connects, ensure no stale process owns UDP 14552 and confirm
  the simulator log lists the third MAVLink output.
- If topics appear but cross-container messages never arrive, confirm the adapter
  and autonomy both retain `ipc: host` alongside host networking. Run
  `make boundary-smoke` in a scenario to test actual delivery, not just discovery.
- If camera topics are absent, inspect `gz topic -l` in the simulator and make
  sure an RGB-D scenario—not a legacy world—was selected.
- A lower camera rate under `SOFTWARE_RENDERING=1` is a rendering-performance
  limitation. `make verify-rgbd` measures Gazebo message timestamps and accepts
  27–33 Hz in simulated time for the configured 30 Hz GPU path. Wall-clock and
  Python/OpenCV exact-pair throughput are reported separately and are not the
  sensor cadence when real-time factor is below one.
- Generated worlds and their exact pose manifests are under
  `logs/generated-worlds/`; delete neither while a scenario is running.
