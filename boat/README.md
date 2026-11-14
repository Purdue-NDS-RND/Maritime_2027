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
make test      # protocol/lifecycle, virtual serial port and ROS construction tests
```

Docker, Compose, Make and Python are required on the host. ROS and
`pymavlink==2.4.50` plus `pyserial==3.5` for serial connections are installed
in the image. Jetson deployment is untested.
`make build` builds natively for the computer running it: x86-64 on the desktop,
ARM64 on the Jetson. The same Dockerfile is used for both.

## Everyday commands

Run these from `boat/`:

```bash
make build    # build the image; repeat after application/dependency changes
make sim      # connect using sim.env (make run remains an alias)
make field    # connect to physical hardware using field.env
make status   # watch status; Ctrl-C exits the viewer
make stop     # request and confirm HOLD
make down     # shut down the container
```

Choose either `sim` or `field`; both run in the foreground and neither uploads,
arms or starts a mission. Startup refuses to replace a running boat container.
Use a second terminal for status/control. All control commands and `down` address
the same `maritime-boat` project regardless of how it was launched; no remembered
target selection or environment flags are needed. `make down` shuts down the
application; use `make stop` and inspect the confirmed outcome before shutdown
when controlling a vehicle. Shutdown cannot guarantee a physical stop.
`make help` lists the short commands. Local mission `upload`, `start` and `disarm`
commands remain explicit.

Both starts use the same launcher and application command; only the selected
env file changes. Edit `sim.env` for simulation and `field.env` for hardware.
`sim.env` ships with the existing simulator defaults. `field.env` is also tracked
and ships with required hardware values blank; `field.env.example` is a reset
template. Neither settings
file is copied into the image. Changes take effect on the next launch.

## Jetson field connections

On the Jetson, from `boat/`, do this once:

```bash
ls -l /dev/serial/by-id/
stat -Lc %g /dev/serial/by-id/YOUR_PIXHAWK
nano field.env
```

Fill in the actual serial device path, its numeric group ID and the Pixhawk baud.
The template deliberately leaves these required hardware settings blank;
`make field` rejects missing settings. A USB/UART device
is exposed as `/dev/boat-fcu` with the selected device group. Configure the actual
Pixhawk port for MAVLink and match its baud; verify fresh heartbeat, position,
velocity and GPS messages rather than assuming the simulator's stream settings.
Direct Jetson UART wiring also needs the correct electrical interface and host
UART setup. USB is the simplest initial bench connection. Recreate the container
after USB reconnect/device changes; device hotplug is not guaranteed.

Then use `make build`, `make test`, and `make field`. No ROS installation on the
host or GPU access is required by this boat application. Edit `field.env` for
hardware changes, then shut down/relaunch to apply them; no image rebuild is
needed for those settings. The file is tracked in Git and excluded from the image build.
`compose.yaml` holds the common application command and mounts. `COMPOSE_FILE`
in each env selects that YAML; the serial template also selects the small
`compose.serial.yaml` device/group overlay. There is no separate field application
command. This overlay is needed because simulation has no serial device to map.
Simulator commands load `sim.env`, not `field.env` or a local `.env`.
Exported shell overrides still follow normal Compose precedence.
For an existing network MAVLink connection, a field env can select only the base
YAML and set `BOAT_CONNECTION` to the appropriate network endpoint instead.
Paths in `MISSION_DIR` are relative to `boat/container/`, or may be absolute;
`COMPOSE_FILE` paths are relative to `boat/`. Build/status/control/shutdown use
the base configuration and `sim.env` to locate the shared project, without
applying simulator settings to a running field container. Inspect and shut down
the existing container before launching with changed settings.

Field HTTP defaults to `BOAT_HTTP_HOST=0.0.0.0`, listening on all host IPv4
interfaces at port 8091. In the shore GCS's **Connections**, set its mission URL
to `http://JETSON_WIFI_IP:8091`, or `http://JETSON_TAILSCALE_IP:8091` when using
Tailscale/Headscale. Do not enter `0.0.0.0` as the GCS destination. A specific
Jetson interface address can be configured instead to limit the listener.
The API has no application authentication or TLS: any client that can reach
the listener can submit requests, subject to existing vehicle-state checks.
Network/firewall policy controls reachability. Tailscale/Headscale may supply
the private network and access policy; they are not installed/configured by
`make field`. Tailscale traffic uses its encrypted network transport while
direct Wi-Fi HTTP retains the existing unencrypted application protocol.
See [Tailscale device connections](https://tailscale.com/docs/how-to/connect-to-devices)
and [Headscale policy](https://headscale.net/stable/ref/acls/).
RFD map telemetry is a separate shore connection,
as described in the [GCS field guide](../gcs/README.md#field-connections-rfd-telemetry-and-jetson-mission-api).
For a read-only check from shore:

```bash
curl --fail http://JETSON_WIFI_OR_TAILSCALE_IP:8091/status
```

Field mode does not mount the simulator example mission. For local-file testing,
place a physically appropriate `mission.json` under
`simulation/logs/boat/field-missions/`, or set `MISSION_DIR` to an absolute
mission directory in `field.env`. GCS uploads need no local mission file. Logs
and journals retain the existing `simulation/logs/boat/` location. Neither launch
adds boot startup or an automatic restart policy.

Configuration and synthetic tests do not establish Jetson, USB/serial, radio,
RC takeover, firmware failsafe or physical motion acceptance. Verify the ARM64
build and disarmed connection/upload/readback before controlled movement tests.
Total MAVLink loss can leave the Pixhawk executing AUTO; inspect/configure its
physical failsafes independently of this application.

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
make sim
```

From `boat/`, in a third terminal:

```bash
make status   # wait for ready, fresh position and GPS fix >= 3; Ctrl-C to exit
make upload   # requires disarmed outside AUTO or armed LOITER; does not arm/start
make start    # explicitly arms and starts the accepted mission
make status   # observe executing -> stopping -> complete in LOITER, or failure
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

`sim.env` sets `BOAT_CONNECTION=udpin:127.0.0.1:14551`.
`BOAT_ROS_DOMAIN_ID` defaults to 27 with local discovery. These are local
development interfaces. Simulator HTTP defaults to localhost:8091; field mode
uses the explicitly configured Jetson address. Physical networking remains
unverified. See [HTTP command ownership](../docs/boat_execution.md#milestone-1-http-and-command-ownership).

Mission snapshots and the operation journal live under ignored
`simulation/logs/boat/`, with progress/events under individual session folders; ROS logs under `simulation/logs/boat/ros/`.
Client disconnection does not affect execution. Application or MAVLink loss
has different fault semantics, detailed in the [execution reference](../docs/boat_execution.md).

ArduPilot ground-rover and surface-boat heartbeats are supported. See the
[Gazebo rover workflow](../simulation/docs/USING_THE_SIM.md#gazebo-ground-rover-compatibility-environment)
for the isolated Wild Thumper test environment. Physical vehicle firmware and
performance remain unverified.

The planner GCS header reads `available_modes` from boat status and sends
`POST /mode` with `{"mode":"LOITER"}` (or another advertised non-AUTO mode).
The sole boat command worker applies the change and confirms it through a
heartbeat; a different mode consumes previous start authorization. AUTO remains
behind reviewed mission Start. Status includes recent operation receipts so
browser reconnection can reconcile commands without repeating them.

Normal builds record their source commit, branch and dirty status in image
labels. See [image identity checks](../simulation/docs/USING_THE_SIM.md#verify-which-source-an-image-runs)
before assuming that an existing `latest` container matches this checkout.
