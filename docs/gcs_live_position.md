# Live boat position on the GCS

Implemented for the web GCS after Milestone 1 simulator acceptance.
Connection setup and environment variables are in the [GCS README](../gcs/README.md).

## Data and ownership

```text
Simulation: ArduPilot → MAVProxy UDP 14550 → GCS telemetry reader
Hardware:   Pixhawk → radio ⇢ shore radio → host forwarder → GCS reader
                                         ↘ optional direct serial reader
GCS reader → latest snapshot / server-sent events → Leaflet boat marker
```

The backend has one passive reader per process. The default endpoint is the
simulator's existing `udpin:127.0.0.1:14550`. Connection, serial baud and target
system/component IDs are configurable. Linux `/dev/` paths support USB serial
radios such as an RFD900 with its actual configured host baud. Host forwarding
is the preferred container setup; an optional Compose override also supports
direct serial access without running the app as root. Host serial drivers stay
outside the application. A radio is assumed to carry MAVLink, not arbitrary
HTTP/IP traffic to the onboard Jetson.

The GCS reader does not send heartbeats, command messages or message-rate
requests. The boat retains UDP 14551, all execution decisions, and command
ownership through its existing HTTP operation API. No simulator sources, ports,
firmware parameters or calibrated stream-rate settings were changed. If QGC
also needs telemetry, give it a separate forwarded output instead of sharing
14550. The reader checks for an occupied UDP endpoint and disables socket sharing
on its own connection.

The browser's map telemetry is independent from its boat mission API polling.
Losing the HTTP connection does not hide fresh radio position; it does disable
commands that require fresh boat status. Radio mode/armed state is not proof of
an approved mission ID, operation confirmation or boat-app completion. This
change does not provide mission transfer to the Jetson over a radio-only link.

## Backend behavior

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

## Browser behavior

The existing map consumes the backend event stream and updates one marker in
place, rotated by reported heading. A large outlined boat silhouette, pointed
bow, forward arrow and permanent compass/degrees label make orientation visible
without hovering. Unknown heading uses a question-mark position circle. The
marker turns grey at its last known location on stale data or stream loss, and
its tooltip identifies that position as last known. A browser timer advances age and detects
a silent stream even when no messages arrive. The header distinguishes live
position from unavailable position; boat mission API availability is reported
separately. There is no route snapping, prediction or automatic command on
reconnection. Track trails, follow-boat controls and interpolation remain future
UI work.

## Validation and limits

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
stations do not compete with boat profile settings.

## References

- [MAVLink common messages](https://mavlink.io/en/messages/common.html#GLOBAL_POSITION_INT)
  defines position, velocity and heading units and unavailable values.
- [Pymavlink](https://mavlink.io/en/mavgen_python/)
  documents UDP and serial connection setup.
- [MAVProxy telemetry forwarding](https://ardupilot.org/mavproxy/docs/getting_started/forwarding.html)
  documents serial input and multiple local/network UDP outputs.
- [Requesting MAVLink message streams](https://mavlink.io/en/mavgen_python/howto_requestmessages.html)
  documents rate requests, which this passive reader does not issue.
