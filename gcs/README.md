# Course GCS

## Boat controls

The **Boat controls** panel above the map is available in every planning step.
It shows confirmed armed/disarmed state, vehicle mode, speed and GPS fix, with
**Hold / Stop** and **Disarm** actions. Offline state is shown as unavailable.
To upload another route after finishing, select Hold / Stop if needed, wait for
reported speed ≤ 0.20 m/s, then Disarm. Upload stays disabled while armed or in
Auto; Go / Start arms automatically after verifying the uploaded mission.
Command progress/errors appear in the panel and do not replace confirmed live
status. The header Stop boat action stays available during route planning.

## Manual move

In **Task setup**, select **Manual move**, set speed/buffer and click **Draw
waypoints**. Click the map in travel order; drag numbered points to adjust them.
The last point automatically becomes the stopped finish. Review the direct
segments, then **Validate route → Approve route → Upload to boat → Go**.
**Stop boat** remains available. Drawing never commands movement.

Selecting Manual move captures the fresh live boat position as the start;
offline planning can use a chosen start. Use **Use live boat position** again
if the boat moves before review. Every segment and the finish retain obstacle
clearance checks; manual routes have no gate/slalom/channel passage constraints.
Manual and task drafts are saved separately. **New empty manual route** clears
only the manual waypoint queue. The ordinary boat mission interface executes
the route and stops in HOLD at the finish; this adds no joystick/GUIDED control.

## Startup and map editing

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
select the finish centre using the last waypoint for task routes; manual routes
update it automatically as waypoints are added. Competition maps initialize
from their recorded west-facing start and select **Custom route (clearance only)**,
which needs no passage list. Version 1 buoy-only imports remain supported.
Version 2 adds physical props, conservative circle/convex-polygon footprints,
station labels, distinctive task buoy colors/Zebra pattern and a nonblocking
6 ft deployment-radius overlay. The view fits the full course and saved drafts
persist across reloads. All physical obstacles participate in segment and
finish-area clearance checks; station annotations do not block routes.

For the legacy gate/slalom scene, choose ordered gate/turn roles. `left`/`right` mean the boat passes on that side of the buoy when travelling
along the course direction (+X when omitted for legacy drafts). The generalized
validator also supports rotated gates and explicit travel directions.

Save the draft, then use **Validate**, **Approve**, **Upload**, and **Start** as
separate actions. Every edit revokes approval. Immutable approved JSON files
include the imported map, mission settings, validation and transfer envelope.
Reload restores saved drafts and approvals. Unsaved edits are identified in the UI.

Set **Target speed** and **Total clearance buffer** in the GCS. Speed must be
finite and positive; there is no calibrated-speed list or application speed cap.
ArduPilot still accepts/rejects the speed command and controls actual motion.
The default buffer for new routes is 1.8 m, an editable starting value rather
than a measured guarantee. It is the total distance from the reported boat
reference point to each physical obstacle's surface: include hull size, positioning error,
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

## GPS assisted planner

The full competition map is the primary test course. The small slalom example is
retained only for focused regressions. Start the normal workspace from the repo:

```bash
make -C gcs build
make -C gcs run
```

Open <http://localhost:8080>. The redesigned workspace has three steps:

1. **Map:** use **Load full competition map**, or import a survey. Click an object
   to inspect/correct it, apply corrections, and confirm reviewed dimensions.
2. **Task setup:** choose **Gate**, **Slalom / Dodge** or **Channel / Evade**.
   Labeled-map suggestions propose assignments, local direction, finish and bounds.
   Use **Review geometry on map**, inspect numbered passages/arrows and boundaries,
   then confirm the setup. **Live boat** and **Full task** are the defaults.
   Generate captures a fresh position and heartbeat (each at most three seconds
   old). Offline planning requires explicitly selecting **Manual start (offline)**.
3. **Route review:** review/edit the blue route, then **Validate → Approve →
   Upload → Start**. Start stays disabled until the selected approval's upload
   is confirmed. Planning works with the boat offline; Upload/Start need a fresh
   connection. **Stop boat** stays visible independently of the current step.

Map clicks normally inspect objects. A point/drawing tool displays instructions
and a **Done / cancel tool** button. **Edit on map** explicitly enables waypoint
placement/dragging; dragging the final waypoint also moves the finish centre.
**Full course** and **Selected task** change only the view. Labels, station
annotations, planning overlays and optional street tiles are under **Map layers**.
Object corrections, passage assignment/order, boundaries, preferred buffer,
heading, finish size, coordinates and command details are disclosed only where
needed. Raw passage JSON is no longer part of the normal operator workflow.

The normal saved workspace is `simulation/logs/gcs/workspace.json`. Reload keeps
it. Each task retains its own draft/settings; switching revokes approval and
never commands the boat. Retry a task from a new start and generate/review a new
route without repeating previous tasks. Importing a different map archives the
complete previous workspace in `workspace-before-map-import-*.json`; old task IDs
are not applied to the unrelated new map. Map corrections preserve the original
observations and invalidate affected reviews/approvals.

The practice map is [`examples/competition-gps-map.json`](examples/competition-gps-map.json):
23 buoys, six physical props, GPS footprints and available labels. It is a
simulator-derived **unverified GPS practice map**, not a new live survey or
simulator-alignment qualification. It contains no simulator run/start metadata.
The same map is bundled with the GCS image and available from the load button.
[`examples/slalom-gps-points.json`](examples/slalom-gps-points.json) remains a small
unlabeled regression fixture. Defaults are still 0.5 m/s and a 1.8 m required
buffer; preferred starts equal to required. The competition Dodge gate has a
3.52 m surface opening: a 1.8 m required buffer needs 3.60 m and is correctly
rejected. The setup explains this before generation. Choose a smaller buffer
only when its hull/navigation allowance is justified; no value is reduced by
suggestion, search or task selection. Simulator integration tests explicitly
use 1.5 m for gate/slalom; this is not physical-boat qualification.

Unknown objects are obstacles. JSON point lists (or `{"points": [...]}`) and CSV
accept `latitude,longitude`, optional `id,color,object_type,radius_m,height_m`.
Visible radius defaults are buoy 0.25 m and unknown/detector 0.50 m. Confirm every
size assumption before approval. Polygon props retain editable GPS vertices;
moving their centre translates the footprint. Original observations are retained
separately from corrected objects. Existing simulator-map versions 1/2 still
require their alignment evidence; live version 3 never claims simulator verification.

Suggestions use imported labels and geometry, never `world_centre`, simulator
station annotations or truth to steer. Unlabeled/ambiguous maps still require
operator assignments. On the labeled competition map, Dodge is westbound and
Evade is southbound. Gates use their actual pair orientation; slalom turns use
neighboring anchors for local travel, with an advanced direction override.
Correct membership/order and passing sides before confirmation. The normal
workflow has no mandatory manually positioned Entry. An automatic approach
connects the captured start to the first included finite passage; a full run
from beyond the beginning may show a return approach. Advanced settings retain
an exceptional physical connection crossing.

Channel chains include **every** ordered point. Correct their object IDs under
**Correct ordered channel chains**, then review the derived polygon and section
connections. Each chain vertex contributes its fraction of chain length; equal
fractions across the two chains define progress sections. Crossing or ambiguous
connections require correction. Permitted water is an operator assertion, not a
boundary proved by buoy observations. Outside starts enter through the selected
beginning opening; inside starts enforce containment immediately. Starts inside
an obstacle/boundary exclusion buffer are rejected. Required side-boundary and
obstacle room is preserved while traversing the entrance cap. The finish disk
must remain fully inside permitted water with required clearance.

**Remaining section** is an explicit partial attempt. Click **Suggest remaining
section**; an ambiguous position leaves the choice empty. Choose or correct the
first included section, review the grey excluded sections and confirm the choice
before Generate. Excluded passages receive no completion credit and do not
change the full task setup. Moving more than 1 m after selection requires a new
review. A start beyond a selected channel cell requires choosing the appropriate
later first section. Approval freezes the captured start, scope and generated
route. Upload and Start validate the actual connection against those same inputs;
no command silently regenerates, changes scope or rewrites approval.

Workspace migration writes `workspace-before-general-course-*.json` before
changing legacy planner drafts, retains maps/routes/manual queues and assignment
candidates, and revokes planner approvals. Review geometry and regenerate these
drafts. Manual routes and boat-only execution retain their existing interfaces.

A* remains deterministic, metric and 8-connected, carrying passage progress and
incoming direction. It tries 0.25, 0.10 and 0.05 m, with at most 250,000 expansions
per resolution, with a shared 60-second search/simplification time budget.
Time exhaustion returns an error without a generated draft or a blockage claim.
An admissible lower bound through remaining finite openings guides search;
precomputed local obstacle geometry and conservative distance bounds avoid
repeated geographic/polygon work without dropping obstacles. Each edge enforces
required clearance, active task direction/order/sides and boundaries. Final GPS
segments receive a separate complete validation after simplification. Gate
opening proofs, blocked entry windows, unsafe finishes and search exhaustion
remain distinct. Exhaustion does not prove continuous-space impossibility.

Required buffer includes the operator's hull and navigation allowances. Preferred
shortfalls appear as orange sections with achieved clearance. Detector proximity
is bounded/count-normalized preference only and cannot override required
clearance or channel containment. No detection-avoidance, controller-tracking or
physical-radio qualification is implied.

Backend operations: `GET /api/examples/competition` supplies the practice map;
`POST /api/course/prepare` takes `task` and optional existing `settings`, returning
an **unconfirmed** proposed draft plus setup diagnostics. Generic geometry
suggestions remain at `POST /api/course/suggest`. `POST /api/generate` returns a
proposed GPS draft, final validation and resolution/search diagnostics. Workspace,
`POST /api/course/geometry` returns reviewed derived sections, and
`POST /api/course/remaining` returns an unconfirmed suggestion. Drafts use
`geometry_version: 2`; `attempt` contains `start_source`, `captured_at`,
`start_snapshot`, `mode`, `first_section` and selection confirmation. Persistent
course configuration excludes attempt/route metadata. Generation returns
`derived_sections`, `excluded_sections`, `partial_attempt`, `route_sections` and
structured failure `errors` with code/reason/location/object IDs where known.
Validate/Approve and boat command interfaces remain unchanged. For isolated
local browser qualification, `GCS_ORIGIN` selects the allowed origin; default
remains `http://localhost:8080`. Use a separate data directory and unused passive
telemetry port when running a second GCS.

### Buffer preview before validation

Use **Show buffers** above the map immediately after loading a course, before
confirming sizes/setup or validating. Amber outlines show required clearance
around all circular and polygon objects, bands along every planning/channel edge,
the saved start, and the finish radius plus clearance. A larger preferred buffer
is blue. The preview updates with edited dimensions and buffer settings and is
independent of Planning overlays. Edge bands also cover concave boundaries;
convex polygons additionally show an inset outline. A collapsed inset reports
no remaining room. Polygon outlines use a
slightly conservative sampled visual approximation; backend validation is authoritative.

**S** is the captured attempt start, distinct from the moving boat marker. Its
source and capture time appear in Route review. Amber route sections show the
approach; blue sections show task travel. Buffer geometry is illustrative;
authoritative validation checks every emitted GPS segment after simplification.
