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

Runtime data lives under ignored `simulation/logs/gcs/`. Mount measured profile
JSON files read-only from `simulation/logs/profiles/`. No production profile is
shipped: a synthetic test fixture must never be installed as a live profile.
See [the implementation handoff](../docs/milestone1_handoff.md).

Import the JSON produced by `simulation/scripts/export_active.py`. Click to add
GPS waypoints, drag them, edit coordinates, reorder or delete them. Explicitly
select the finish centre using the last waypoint and choose ordered gate/turn
roles. `left`/`right` mean the boat passes on that side of the buoy when travelling
along the fixed course's +X direction. This validator supports that course
orientation; it rejects other gate orientations.

Save the draft, then use **Validate**, **Approve**, **Upload**, and **Start** as
separate actions. Every edit revokes approval. Immutable approved JSON files
include the imported map, settings, profile, validation and transfer envelope.
A changed profile invalidates approval even without browser edits. Reload
restores saved drafts and approvals. Unsaved edits are identified in the UI.

The backend validates both the planned start connection and the actual boat
position at upload and start. Clearance uses an enclosing boat circle plus the
selected clearance, measured position/tracking allowance and 0.10 m reserve.
Finish-region validation also includes its radius. No route is generated,
waypoint changed or clearance reduced by validation.

The browser talks only to the GCS backend. Mission commands use the boat's
loopback HTTP API on port 8091. A 202 response means
receipt; query the returned operation ID for confirmation. After an ambiguous
start timeout, inspect operation and vehicle status instead of issuing a new
mission. Reconnecting never starts a mission automatically. STOP remains
available independently of draft/approval; disarm is checked by the boat.

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
| `GCS_IMAGE` | `maritime-course-gcs:milestone1` | Image for build/run |

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

`GET /api/telemetry` returns the latest snapshot; `GET /api/telemetry/events`
streams the latest snapshot every 200 ms without an accumulating client queue.
Both include independent heartbeat/position/GPS ages, vehicle IDs, a session ID,
heading, speed and stale/connection state. `/api/status` remains boat-owned
mission status; radio telemetry does not prove mission identity or completion.
See [live position design and validation](../docs/gcs_live_position.md).
Use the [simulator tracking test](../simulation/docs/GCS_LIVE_POSITION.md) for a
manual end-to-end check without changing route approvals or controller settings.

Tests: `PYTHONPATH=.. python3 -m unittest discover -s tests -v` and
`cd frontend && npm ci && npm run build`. Container builds use the committed
npm lockfile. These are development loopback interfaces, not a selected
physical vehicle networking or authentication design.
