# Boat

The first boat application executes a supplied GPS mission through ArduPilot.
One ROS 2 Jazzy node owns a direct `pymavlink` connection inside a separate
container. ArduPilot controls motion. Cameras, simulator truth, MAVROS, Nav2,
the drone and GCS are not dependencies.

The local-file example below tests supplied-route execution; full simulator
slalom acceptance is recorded in [Milestone 1](../docs/milestone1.md). See the
[execution reference](../docs/boat_execution.md) for behavior and limits.

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
make upload   # armed LOITER or disarmed outside AUTO; does not arm/start
make start    # starts accepted mission; arms only if needed
make status   # observe executing -> stopping -> complete, or failure
make stop     # selects HOLD before disarming after completion in LOITER
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
Local file tests do not check map/obstacle clearance. GCS approval uses the
shared conservative validator before mission transfer. Use a new mission ID for
each deliberate new attempt; identical IDs are idempotent.

`BOAT_CONNECTION` defaults to `udpin:127.0.0.1:14551` and `BOAT_BAUD` to
115200 (pymavlink's previous default; irrelevant for UDP).
`BOAT_ROS_DOMAIN_ID` defaults to 27 with local discovery. The HTTP API defaults
to localhost:8091. See [HTTP command ownership](../docs/boat_execution.md#milestone-1-http-and-command-ownership).

## Jetson field connections

The selected field arrangement keeps the boat app on the Jetson. A local
USB/serial link connects it to the Pixhawk; a separate Pixhawk telemetry port
can feed the RFD pair for shore map telemetry. Actual port assignments, wiring,
radio power and serial settings must be checked against the specific hardware.
The RFD link does not transport the boat app HTTP API. See
[shore setup](../gcs/README.md#field-connections-rfd-telemetry-and-jetson-mission-api).

On the **Jetson**, from `boat/`:

```bash
cp field.env.example field.env
ip -4 address
ls -l /dev/serial/by-id/
stat -Lc %g /dev/serial/by-id/YOUR_PIXHAWK
```

Edit `field.env` with the Jetson's private Wi-Fi/Ethernet IPv4 address in
`BOAT_HTTP_HOST`, selected HTTP port, stable Pixhawk device path, its numeric
group and matching serial baud. Use the same address/port in shore
`GCS_BOAT_URL` for first initialization, or edit the shore GCS **Connections**
profile once saved settings exist. The example address/device are placeholders. For USB access:

```bash
make ENV_FILE=field.env SERIAL=1 build
make ENV_FILE=field.env SERIAL=1 run
```

The override maps only the selected device to `/dev/boat-pixhawk` and grants
its group to the non-root container. Host drivers remain outside the image.
After USB replugging, recreate the container to update the mapped device.
Rebuilding from source on the target Jetson may require platform-specific
dependencies; this workflow has not yet been qualified on Jetson hardware.

For a local MAVLink forwarder, omit `SERIAL=1` and set `BOAT_CONNECTION` in
the environment file to its own UDP input. The Jetson app and shore radio
reader need separate serial devices/forwarded outputs. Do not share a serial
device or UDP consumer port between processes.

`BOAT_HTTP_HOST` defaults to `127.0.0.1`; selecting a LAN interface explicitly
enables remote mission commands. This API has no authentication or encryption:
use an isolated trusted control LAN. Browser-origin requests are rejected, but
that is not authentication. Stop with the same settings:

```bash
make ENV_FILE=field.env SERIAL=1 down
```

Changing settings requires container recreation, not just Docker restart.
Reconfiguring/restarting the boat app is an execution interruption; do it while
disarmed and stopped, then review a fresh run. Radio telemetry and network
availability are separate from vehicle positioning/failsafe behavior. Physical
link-loss behavior, STOP reachability and whole-boat performance remain unverified.

Mission snapshots and the operation journal live under ignored
`simulation/logs/boat/`, with progress/events under individual session folders; ROS logs under `simulation/logs/boat/ros/`.
Client disconnection does not affect execution. Application or MAVLink loss
has different fault semantics, detailed in the [execution reference](../docs/boat_execution.md).

The HTTP status response includes a read-only operation summary: all unfinished
receipts plus the last 32 operations. The shore connection manager uses it to
reconcile lost command receipts, including after a GCS restart, before switching
mission targets. It adds no command or retry. Explicitly resolving an unknown
outcome requires fresh disarmed/stopped/non-AUTO status with no queued/running
commands; older boat images without the summary cannot satisfy that check.
Boat-only supplied-route execution and the local MAVLink owner are unchanged.
