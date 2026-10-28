# Boat

The first boat application executes a supplied GPS mission through ArduPilot.
One ROS 2 Jazzy node owns a direct `pymavlink` connection inside a separate
container. ArduPilot controls motion. Cameras, simulator truth, MAVROS, Nav2,
the drone and GCS are not dependencies.

This is the first implementation slice of [Milestone 1](../docs/milestone1.md),
not slalom or whole-hull-clearance acceptance. See the
[implementation handoff](../docs/boat_execution.md) for behavior and limits.

## Build and check

From `boat/`:

```bash
make validate  # host input tests, syntax and Compose configuration
make build
make test      # protocol/lifecycle tests and ROS node construction
```

Docker, Compose, Make and Python are required on the host. ROS and
`pymavlink==2.4.50` are installed in the image. Jetson deployment is untested.

## Boat-only simulation

From `simulation/`, start a fresh open-water simulator in another terminal:

```bash
WORLD=blueboat_calm.sdf WATER=calm make run
```

Verify that an existing simulator image matches this checkout's startup scripts,
configuration and world. The example waypoint is approximately 12 m north of
the simulator's nominal starting position. Use it in open water, not as a
gate/slalom route. Its numbers are experimental settings, not agreed margins.

From `boat/`, in a second terminal:

```bash
make run
```

From `boat/`, in a third terminal:

```bash
make status   # wait for ready, fresh position and GPS fix >= 3; Ctrl-C to exit
make upload   # requires disarmed vehicle outside AUTO; does not arm/start
make start    # explicitly arms and starts the accepted mission
make status   # observe executing -> stopping -> complete, or failure
make disarm   # requires HOLD and speed <= 0.2 m/s; no force-disarm
make down
```

`make stop` explicitly requests and confirms HOLD. It does not guarantee an
immediate physical stop or station keeping. Stop the boat app before simulator
smoke tests or teleop: they use the same UDP API port. Keep QGC and other command
producers from changing missions during a boat test. Physical RC acceptance is
still open.

For another manually authored mission, place `mission.json` in a directory and
run `MISSION_DIR=/absolute/directory make run`. It is mounted read-only;
`make upload` reads it anew. The example documents all required fields. GPS is
WGS84 degrees, speed is m/s, distances are metres and intervals are seconds.
The finish area is centred on the final waypoint. The first waypoint must be
within `max_start_distance_m` of the reported boat position before start.
Input rejects extra/missing fields, non-finite numbers and local coordinates.
No map/obstacle clearance is checked yet.

`BOAT_CONNECTION` defaults to `udpin:127.0.0.1:14551`.
`BOAT_ROS_DOMAIN_ID` defaults to 27 with local discovery. These are local
development interfaces, not the future GCS transfer protocol.

Mission snapshots and progress/events live under ignored
`simulation/logs/boat/<session>/`; ROS logs under `simulation/logs/boat/ros/`.
Client disconnection does not affect execution. Application or MAVLink loss
has different fault semantics, detailed in the handoff.
