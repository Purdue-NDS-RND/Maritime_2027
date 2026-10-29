# Course GCS

React + Leaflet and FastAPI, served together at <http://localhost:8080>.
Course editing works without internet tiles. Optional OpenStreetMap tiles
include attribution; tile failure leaves the route workspace available.

From `gcs/`:

```bash
make build
make run
make down
```

Runtime data lives under ignored `simulation/logs/gcs/`. Boat/GCS startup and
mission execution require no navigation profiles, geometry hashes or controller
gain staging. ArduPilot tuning belongs to the simulator/vehicle setup.

Import the JSON produced by `simulation/scripts/export_active.py`. Click to add
GPS waypoints, drag them, edit coordinates, reorder or delete them. Explicitly
select the finish centre using the last waypoint and choose ordered gate/turn
roles. `left`/`right` mean the boat passes on that side of the buoy when travelling
along the fixed course's +X direction. This validator supports that course
orientation; it rejects other gate orientations.

Save the draft, then use **Validate**, **Approve**, **Upload**, and **Start** as
separate actions. Every edit revokes approval. Immutable approved JSON files
include the imported map, mission settings, validation and transfer envelope.
Reload restores saved drafts and approvals. Unsaved edits are identified in the UI.

Set **Target speed** and **Total clearance buffer** in the GCS. Speed must be
finite and positive; there is no calibrated-speed list or application speed cap.
ArduPilot still accepts/rejects the speed command and controls actual motion.
The default buffer for new routes is 1.8 m, an editable starting value rather
than a measured guarantee. It is the total distance from the reported boat
reference point to each buoy's surface: include hull size, positioning error,
tracking error and desired extra room yourself. No hull model or hidden margin
is added. The buffer must be finite and nonnegative. Validation checks straight
route segments, ordered passages and the entire finish region; it does not
predict actual turns or establish tracking performance at the chosen speed.

The backend checks both the planned start connection and the actual boat position
at upload and start. The boat also requires the first waypoint to be within
100 m. Existing profile-based workspaces are backed up automatically, retain
their map/waypoints, and lose approval. Their old hull-only clearance is cleared:
choose a total buffer, then Validate and Approve again. Saved historical approval
files and operation journals are retained.

The browser talks only to the GCS backend. Mission commands use the boat's
loopback HTTP API on port 8091. A 202 response means
receipt; query the returned operation ID for confirmation. After an ambiguous
start timeout, inspect operation and vehicle status instead of issuing a new
mission. Reconnecting never starts a mission automatically. STOP remains
available independently of draft/approval; disarm is checked by the boat.

## Live map telemetry

Live map position comes from a separate, passive backend MAVLink reader. By
default it listens on `udpin:127.0.0.1:14550`, the simulator's existing ground
station output. UDP 14551 remains owned by the boat application. Close QGC or
give it a separate MAVProxy output: two clients must not share a consumer port.
The marker updates from a 5 Hz server-sent event stream. A large boat silhouette
with a pointed bow, forward arrow and permanent compass/degrees label makes
heading visible without hovering. It greys out at the last known position when
telemetry becomes stale; unknown heading uses a question-mark circle. The reader
does not send heartbeats, control commands or message-rate requests. Map
telemetry can work while the boat mission HTTP API is unavailable.

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `GCS_MAVLINK_CONNECTION` | `udpin:127.0.0.1:14550` | UDP input or Linux serial device path |
| `GCS_MAVLINK_BAUD` | `57600` | Serial baud; match the radio's configured host baud |
| `GCS_MAVLINK_SYSTEM_ID` | `1` | Selected ArduPilot vehicle |
| `GCS_MAVLINK_COMPONENT_ID` | `1` | Selected autopilot component |
| `GCS_IMAGE` | `maritime-gcs:latest` | Image for build/run |

For example, `GCS_MAVLINK_CONNECTION=udpin:127.0.0.1:14552 make run` selects a
different MAVProxy output, which must already be configured to forward there.
Restart the GCS to apply connection settings. The backend retries device-open
and read errors once per second; freshness expires after 3 s without heartbeat
or position. GPS fix/age is reported separately from position freshness.

For an RFD900, normally have a host MAVLink forwarder own the USB radio and send
UDP to the GCS. This requires no USB access inside the container. Alternatively,
direct serial access is available through the optional Compose override:

```bash
# From gcs/, after building the image. Example host baud: verify your radio.
export GCS_SERIAL_DEVICE=/dev/serial/by-id/your-radio
export GCS_SERIAL_GID=$(stat -Lc %g "$GCS_SERIAL_DEVICE")
export GCS_MAVLINK_BAUD=57600
HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose \
  -f container/compose.yaml -f container/compose.serial.yaml up --no-build
```

Use the same two Compose files with `down` to stop that setup. The override maps
the selected host device to `/dev/gcs-radio` and passes its numeric group to the
non-root app. After physically replugging a directly mapped USB radio, recreate
the container if the host device identity changes. Host forwarding avoids that
container device-remapping issue. For running the backend outside Docker, set
`GCS_MAVLINK_CONNECTION=/dev/serial/by-id/your-radio` and the matching baud.

Radio telemetry does not prove mission identity or completion; `/api/status`
retains boat-owned mission status. Snapshot and stream semantics are detailed
below.
Use the [simulator tracking test](../simulation/docs/USING_THE_SIM.md#test-live-gcs-tracking) for a
manual end-to-end check without changing route approvals or controller settings.

## Development checks

Tests: `PYTHONPATH=.. python3 -m unittest discover -s tests -v` and
`cd frontend && npm ci && npm run build`. Container builds use the committed
npm lockfile. These are development loopback interfaces, not a selected
physical vehicle networking or authentication design.

## Telemetry filtering and recovery

- `GET /api/telemetry` returns a thread-safe latest snapshot.
- `GET /api/telemetry/events` emits that snapshot every 200 ms (5 Hz), including
  advancing freshness ages. Each client samples current state; there is no
  accumulating per-client history queue. Disconnecting a client leaves the
  shared reader running.
- `GET /api/status` and mission commands retain their existing boat HTTP path.
- Application lifespan starts/stops the reader. Missing serial devices, occupied
  ports and read errors are reported in snapshots and retried after one second.
  Direct USB remapping after replug can require container recreation.

Only the configured system/component is accepted. A matching ArduPilot
surface-boat heartbeat is required before using its position or GPS messages.
`GLOBAL_POSITION_INT` supplies estimated WGS84 latitude/longitude (1e7 scale),
heading (100 scale) and horizontal speed from velocities (100 scale). Invalid
coordinates are rejected. Unavailable heading/velocity becomes null without
inventing values or discarding an otherwise valid position. `GPS_RAW_INT`
supplies fix quality independently.

Snapshots include position, heading, speed, mode/armed state, GPS fix, vehicle
IDs, source boot timestamp, session ID and independent heartbeat/position/GPS
ages. Position is stale when heartbeat or position is missing or older than
3 s, or the transport is in error. A fresh position is still an autopilot
estimate: GPS fix/age remains visible through the API and does not establish
position accuracy or whole-hull clearance.

Duplicate/backwards position timestamps cannot replace newer samples while
position is fresh; unsigned timestamp wrap is supported. After a stale position,
a backwards clock can begin a new session to recover an autopilot reboot. A
heartbeat returning after a gap also clears cached state and begins a new
session. This deliberately permits a short stale interval during reboot
recovery. Source-clock filtering cannot authenticate telemetry or distinguish
all delayed frames from a restarted source.

The browser timer advances telemetry age and detects silent streams. There is
no prediction, route snapping or automatic command on reconnect. Radio telemetry
does not carry the HTTP mission envelope to the onboard Jetson; physical mission
transport is still undecided. Host serial drivers remain outside the container.

## Recorded telemetry validation and limits

All 25 GCS tests passed in the `maritime-course-gcs:live-position-test` container.
The suite exercises real MAVLink frames over local UDP and a pseudo-terminal
serial device, checking configurable baud, source filtering, unit conversion,
invalid/sentinel fields, timestamp ordering/wrap/reboot, freshness, occupied
ports, retry after transport error and shutdown. A real Uvicorn/HTTP/SSE test
feeds changed positions, checks movement through the stream, stops the feed,
checks stale last-known position, and verifies snapshot access after client
disconnect. It runs with the boat HTTP helper blocked, demonstrating telemetry
independence. Existing command and route approval tests remain in the suite.

The production container build compiles the React frontend. Compose checks cover
both UDP and the optional serial device configuration. The operator reported
working live movement during simulator testing. A subsequent live Chrome check
confirmed the oriented silhouette and permanent heading label using the running
simulator's telemetry. Its local screenshot is retained at
`simulation/logs/gcs-boat-marker.png`. This was a rendering check, not a new
automated full-course or clearance evaluation. Physical RFD900 operation and RF
coverage/latency remain unverified. Before hardware use, measure actual message
arrivals and visible lag; the 5 Hz backend stream cannot create source updates that the radio
does not deliver. Configure one owner for any future message-rate requests so
stations do not compete with simulator/vehicle telemetry configuration.

### References

- [MAVLink common messages](https://mavlink.io/en/messages/common.html#GLOBAL_POSITION_INT)
  defines position, velocity and heading units and unavailable values.
- [Pymavlink](https://mavlink.io/en/mavgen_python/)
  documents UDP and serial connection setup.
- [MAVProxy telemetry forwarding](https://ardupilot.org/mavproxy/docs/getting_started/forwarding.html)
  documents serial input and multiple local/network UDP outputs.
- [Requesting MAVLink message streams](https://mavlink.io/en/mavgen_python/howto_requestmessages.html)
  documents rate requests, which this passive reader does not issue.
