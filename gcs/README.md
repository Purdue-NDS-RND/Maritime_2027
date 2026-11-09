# Course GCS

The main workflow is **Map → Configure → Build run → Review & execute**. A single task is a
one-card run. Configure has a dedicated workspace with an optional map preview. Build run
keeps a large map beside the selected task editor and a compact ordered task
strip above them. The map is primary during course and route review.
Planning works offline; execution requires a fresh boat connection.

## Startup and session state

From the repository root:

```bash
make -C gcs build
make -C gcs run
```

Open <http://localhost:8080>. Each page starts empty. **New run**, reload, another
tab and backend restart discard planner maps, assignments, routes, reviews,
approvals and return targets. None are restored from disk or browser storage.
Existing `simulation/logs/gcs/` files and operation journals remain untouched;
they are not planner inputs. Resetting the planner never clears or commands an
uploaded boat mission. Live boat status and Hold / Stop remain available.

1. **Map:** explicitly import a course or load **Full competition map**. Review
   object positions and types, apply corrections and confirm the map. Imports
   reset all course-specific inputs and restore shipped settings, even if object
   IDs are reused. Original observations remain available within this session.
2. **Configure:** set shared speed, ordinary required/preferred buffers, tower
   hard/soft zones, common boundary, start source and execution budget. Blue
   panels cover ordinary clearance; purple covers tower avoidance; amber covers
   start/boundary/execution limits. Open **Show map preview** to inspect distances.
   Wide layouts show three compact settings columns. Smaller panels use
   **Speed & clearance / LiDAR towers / Start & limits** categories; selecting a
   tower on the map opens its category. Continue stays pinned below the settings.
   Drawing tools open the map automatically; inputs remain in this page session.
3. **Build run:** use the direct **＋ Gate / Slalom / Channel / Manual** buttons.
   The sequence sits above a persistent map (about 60%) and task editor (about
   40%). **Expand map** gives more room to the map while retaining an inspector.
   The application fits the browser window: the page and map do not scroll.
   Long forms scroll inside the editor, the sequence scrolls horizontally, and
   Generate stays pinned below the selected-task editor. On phone-sized screens,
   the map and editor share the available height vertically.
   Select a task chip, then use the shared **↑ / ↓ / Duplicate / Remove** toolbar.
   The editor separates **Assignments** (or **Chains & sections**), **Finish**
   (or **Finish & water**) and **Advanced**. Local heading overrides live in
   Advanced; geometry review and complete-task confirmation remain visible below
   the content. Ordinary passage rows show names, sides and endpoint actions
   together to avoid scrolling through repeated settings.
   Assignments, local headings, passing sides, channel chains and endpoints belong
   to that instance. **Review geometry on map** opens the preview; explicitly
   confirm each complete task. Selecting a task frames its geometry automatically.
   Click **Gate N · show pair on map** to focus that exact pair, with persistent
   buoy names, a gate label and crossing arrow. Clicking a buoy shows its identity
   and assignment. **1st buoy / 2nd buoy** selects an endpoint
   for map-click replacement; **Done / cancel tool** cancels the tool. Replacements
   revoke task review, derived geometry, sharing and generated authority. Duplicate
   endpoints, towers and polygon objects are rejected as replacements. Task accents match selected map geometry: teal
   Gate, amber Slalom, cyan Channel and slate Manual. Actual buoy colors and
   purple tower zones retain their meanings. **Shared settings** returns to
   Configure without losing task selection or current inputs.
4. **Review & execute:** Generate recomputes the whole run from a fresh start.
   Review route/connector sections, instance IDs, final stopping area, clearance
   findings, nominal travel time and execution budget. Then **Validate → Approve
   → Upload/readback → Start**. A receipt is not confirmation. Upload requires a
   disarmed boat outside AUTO; Start checks the exact acknowledged approval.

Drag a task’s grip to reorder, or select it and use **↑ / ↓**. **Duplicate** copies only that
card's current configuration into a new independent instance. **Remove** deletes
that instance. These edits revoke the route, approval and shared-crossing
confirmation. Task cards always include all required passages; partial-task
recovery and per-card speeds are not part of Run builder.

Manual cards contain exact ordered waypoints. **Draw manual waypoints** appends
map clicks; edit coordinates or remove points in its editor. Every connecting
segment, including the join from the preceding endpoint, is checked directly.
Manual-only and mixed runs use the same approval/execution flow. The boat still
accepts independent manually supplied missions without any GCS or drone.

**Live boat** is the default start source. Generate captures position/heartbeat
ages at most three seconds. Offline planning explicitly selects **Manual start**
and a map location. Moving over 1 m from the approved start requires fresh
planning/review. An earlier route or task progress never supplies a new planning
start. Repeated Generate retains reviewed operator inputs and replaces all
results atomically; failure leaves no executable previous or partial route.

Labeled suggestions do not confirm task meaning. For an unlabeled course, use
**Assign another gate or turn**, set the local travel direction and passing
sides, and define the finish and common boundary. For Channel, enter both ordered
object chains, review/correct permitted water and use **Finish past last gate**.
Uneven, staggered, rotated and curved courses are supported. The full competition
map is the primary operator scene; the small slalom map is regression coverage.

Only adjacent compatible Gate → Slalom instances can share an entrance. Use
**Review adjacent shared crossings**, then explicitly confirm the named instances.
Without confirmation both crossing requirements remain. Reordering, assignment,
map, boundary or settings edits revoke confirmation. Sharing describes planned
semantics and does not establish official scoring credit.

## Boat controls and Return now

The persistent panel displays actual mode, arming, speed and GPS fix. **Stop boat**
sends priority Stop independently of planner work or approval. Hold / Stop selects
HOLD; wait for speed ≤0.20 m/s, then **Disarm** before replacement upload. Start
arms automatically through the existing boat controller.

**Return now** becomes available only after a run's Start operation succeeds in
this page session. Its captured planning start is frozen as the return target;
the map displays that target's 1 m stopping area. It remains available after
completion or Stop. A return Start never changes the target to the current boat
position. New run/reload/restart removes it.

Clicking Return now immediately sends priority Stop and consumes outbound
execution authority. Preparation waits for confirmed HOLD, fresh telemetry and
speed ≤0.20 m/s, then samples the current position. The existing bounded search
plans a new navigation route independently of the outbound waypoints, using the
current reviewed map, shared settings and boundary. Inside a reviewed channel,
it retains permitted water and mandatory side buffers until leaving through
that channel's beginning opening. It does not reverse the old route or resume a
partial task. Relevant failures report their specific cause and initiate no
return movement.

The return opens in review. **Validate → Approve**, explicitly **Disarm** after
preparation, then **Upload/readback → Start**. A return is an ordinary waypoint
mission, finishing within 1 m at ≤0.20 m/s for at least five seconds, then HOLD.
There is no automatic final return card, automatic upload/start or interrupted
run resume. Failed transfer leaves Start blocked.

## Buffers, boundaries and planning limits

Shipped defaults are 0.5 m/s, 1.8 m required/preferred point clearance, tower
1.8 m hard / 10 m soft distances and strength 10, and a 300 s execution budget.
They are editable assumptions, not measured physical guarantees. Include object
size, hull size, survey/GPS/tracking error and buoy motion in required clearance.
No object radius is added for live GPS points. Unknown objects remain obstacles.
Tower hard distances replace ordinary clearance at each detector; individual
tower overrides remain available. Task overrides and saved presets are removed.

**Show buffers** previews metric required/preferred circles and tower zones.
The soft preference may yield and produces review notes. Hard obstacles,
common boundary and channel containment never yield. A Channel card must cross
its finite entrance and all sections in order, then its actual final gate before
its endpoint. Channel can appear anywhere in the run. Intermediate endpoints
are transit points; only the final card has a stopped finish.

All cards share one 60-second search/simplification/final-validation deadline.
Every emitted GPS segment is revalidated, and the complete mission is limited to
500 waypoints. Search exhaustion does not prove blockage. One shared finite
positive speed applies to the mission. The editable execution budget is within
10–7200 s; the displayed suggestion is `max(300, ceil(2*length/speed + 60))`.
Approvals freeze the map, settings, ordered instances, start, sharing and path.
Actual-start checks run at Upload and Start. No vehicle tuning, simulator pins,
calibration or direct MAVLink ports are changed by Run builder.

## Object import and session API

Import JSON point lists, `{"points": [...]}` or CSV with latitude/longitude and
optional ID, color and object_type. Missing types become unknown; omitted IDs
are generated within the imported list. Provide one consolidated row per object.
The bundled full map has 23 buoys and six prop points and is unverified practice
input. Native simulator formats remain supported with alignment checks.

To try the simple JSON import on the full course, choose **Import JSON / CSV**
and select `gcs/examples/competition-gps-points.json`. It contains only color,
latitude and longitude for the same 29 objects as `competition-gps-map.json`,
representing a minimal drone export without known IDs or object classifications.
Coordinates are copied exactly from the practice map; survey noise is not
simulated. The importer generates IDs such as `point_1` and sets object types to
`unknown`. It converts these points to a version 3 map; review and assign task
geometry in the GCS after import. No task labels or station annotations are
included.

### Clean up, compile and save a course

Map now shows **Clean up → Find course → Review tasks**, with the next action
fixed at the bottom of the panel.

1. Import the survey. When needed, **Mark N red/green detections as buoys**
   explicitly types unknown red/green observations together. Existing towers and
   obstacles are preserved. Click individual objects for corrections; bulk color
   selection, original comparison and position details are optional controls.
2. Click **I reviewed the map — continue**, then **Compile course**. The manual
   assignment link is available when course recognition is not appropriate.
3. Preview **Option 1–5** on the map and **Confirm** the tasks you want. A task
   row shows its confirmation directly. Unresolved tasks can be assigned later.
   Hints, object lists, measurements and search diagnostics stay collapsed.
4. **Continue to Configure**, then build your chosen run. Task geometry, finish,
   boundary, shared crossing and route still require their existing reviews.
   Confirming assignments never generates or approves a boat route.

**Save course → Download course JSON** retains observations, profile, hints and
selected roles. Use **Change map / source details → Import JSON / CSV** to reload.
Review the map and existing assignments again; confirmations and routes are never
restored. Map edits invalidate recognition and routes; settings changes preserve
recognition while invalidating routes. **Measurements & search details** reports
bounded-search limits and costs, which are not probabilities.

See [map compiling](../docs/map_compiling.md) for the complete workflow, profile
measurements, scoring assumptions, file format and session APIs.

To practice with rotated and imperfect full courses, run `make random-course
SEED=45` from `simulation/`, open its preview, and import the generated
`observations.json`. See [random course testing](../simulation/docs/USING_THE_SIM.md#random-full-course-layouts)
for repeatable seeds, variation levels and matching Gazebo launches. Preview
observations contain no course assignments and are synthetic, unverified inputs.

The browser first calls `POST /api/session`, keeps the returned `session_id` only
in memory, and sends `X-Planner-Session` on planner requests. Unknown sessions
are rejected after restart. `PUT /api/workspace` and `POST /api/import` require
the current `revision`. `run_draft.steps` contains `{id, type, setup}` objects;
manual `setup.waypoints` are explicit input. Clients cannot publish generated
geometry through workspace edits. Generation publishes only if both input
revision and interruption epoch still match. Superseded client responses are
also discarded. `POST /api/return/prepare` sends Stop and prepares the session's
frozen target; it may carry current reviewed inputs with their revision.
`POST /api/reset` clears planning only. `/api/status`, Stop, Disarm and passive
telemetry remain independent of planner authority. Mission commands still use
the boat-owned HTTP interface; the unchanged boat envelope contains GPS waypoints,
one speed, finish limits and timeout.

## Development checks

```bash
make -C gcs test                 # containerized backend/API checks
npm --prefix gcs/frontend test
npm --prefix gcs/frontend run build
make -C simulation validate
```

Raw evidence belongs under ignored `simulation/logs/`. Independent movement
assessment checks actual hull clearance, ordered instance passages, contacts,
channel containment and stopped settling. Passing UI/static planning checks
does not establish movement or physical-boat acceptance. See
[Milestone 1](../docs/milestone1.md) for recorded configurations and limitations.

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

## Telemetry development checks

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

## Historical fixed-order workflow note

The following operator note predates Run builder and describes the former
Single task / Competition run interface. Use the current card workflow above.

Individual tasks need reviewed assignments, not individually generated routes.
When assignments are already saved, review their geometry and confirm each
task in the run builder. If **Generate competition run** is disabled, check that
at least one task is selected, each selected task is confirmed, the common
boundary has at least three corners, settings/budget are valid, and Live boat
telemetry is fresh. A run initialized from a manual draft may have no boundary:
click **Add boundary corners**, click corners around the entire intended run
and boat start, then **Done / cancel tool**. Use **Review run geometry on map**
to check the tasks before confirming them. Shared entrance confirmation becomes
available after all selected task reviews and **Review shared entrance gate**.
