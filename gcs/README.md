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
reference point to each object GPS centre: include object size, hull size, positioning error,
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

Open <http://localhost:8080>. The redesigned workspace has four steps:

1. **Map:** use **Load full competition map**, or import a survey. Click an object
   to inspect/correct it, apply corrections, and confirm reviewed positions/types.
2. **Configure:** set shared speed, required clearance and preferred room. Set
   tower hard exclusion and soft avoidance distances; click a purple tower to
   configure it. Settings preview immediately on the map. Save once for the
   entire course; optional task overrides remain in this panel.
3. **Task setup:** choose **Gate**, **Slalom / Dodge** or **Channel / Evade**.
   Labeled-map suggestions propose assignments, local direction, finish and bounds.
   Use **Review geometry on map**, inspect numbered passages/arrows and boundaries,
   then confirm the setup. **Live boat** and **Full task** are the defaults.
   Generate captures a fresh position and heartbeat (each at most three seconds
   old). Offline planning requires explicitly selecting **Manual start (offline)**.
4. **Route review:** review/edit the blue route, then **Validate → Approve →
   Upload → Start**. Start stays disabled until the selected approval's upload
   is confirmed. Planning works with the boat offline; Upload/Start need a fresh
   connection. **Stop boat** stays visible independently of the current step.

Map clicks normally inspect objects. A point/drawing tool displays instructions
and a **Done / cancel tool** button. **Edit on map** explicitly enables waypoint
placement/dragging; dragging the final waypoint also moves the finish centre.
**Full course** and **Selected task** change only the view. Labels, station
annotations, planning overlays and optional street tiles are under **Map layers**.
Object corrections, passage assignment/order, boundaries,
heading, finish size, coordinates and command details are disclosed only where
needed. Raw passage JSON is no longer part of the normal operator workflow.

The normal saved workspace is `simulation/logs/gcs/workspace.json`. Reload keeps
it. Each task retains assignments and saved drafts. A new browser session (or a GCS backend restart detected by its telemetry
session identifier) displays
no saved course route, waypoints or captured start until you explicitly
Generate that task. Selecting a task shows its reviewed geometry and finish;
choosing Manual start explicitly also shows the editable start. Route review stays disabled until then. Manual queues remain
available through an explicit Manual move selection. Shared settings persist;
switching revokes approval and
never commands the boat. Retry a task from a new start and generate/review a new
route without repeating previous tasks. Importing a different map archives the
complete previous workspace in `workspace-before-map-import-*.json`; old task IDs
are not applied to the unrelated new map. Map corrections preserve the original
observations and invalidate affected reviews/approvals.

The practice map is [`examples/competition-gps-map.json`](examples/competition-gps-map.json):
23 buoy points, six prop points and available labels. It is a
simulator-derived **unverified GPS practice map**, not a new live survey or
simulator-alignment qualification. It contains no simulator run/start metadata.
The same map is bundled with the GCS image and available from the load button.
[`examples/slalom-gps-points.json`](examples/slalom-gps-points.json) remains a small
unlabeled regression fixture. Defaults are still 0.5 m/s and a 1.8 m required
buffer; preferred starts equal to required. The competition Dodge gate has a
4.00 m centre-to-centre opening: a 2.1 m hard buffer on each side needs
4.20 m and is correctly rejected. The 1.8 m default fits this point opening.
No value is reduced by suggestion, search or task selection. Historical simulator
results with physical footprints use the settings and geometry recorded in the
milestone; they do not qualify arbitrary centre-based allowances.

Unknown objects are obstacles. JSON point lists (or `{"points": [...]}`) and CSV
accept `latitude,longitude`, with optional `id,color,object_type`. Explicit
`"object_type": "unknown"` and omitted types both produce unknown obstacles. IDs
are optional and generated when absent. Provide one consolidated row per object.
No radius or height is required or added. Legacy dimensions supplied in simple
point rows are preserved in raw observations but ignored for planning.

```json
{
  "points": [
    {"latitude": 41.12345, "longitude": -86.12345, "object_type": "unknown"},
    {"latitude": 41.12360, "longitude": -86.12370, "object_type": "detector"}
  ]
}
```

Hard and soft distances start at each object GPS point. Include object size,
boat size and positioning/tracking allowances in the hard distance. The map
uses fixed-size identification symbols, including purple tower squares; these
symbols do not represent a physical footprint. Buffer circles are metric.
Original observations are retained separately from corrected objects. Existing
live maps migrate to points after a byte-exact
`workspace-before-point-objects-*.json` backup; saved routes/manual queues remain
but approval is revoked and map/task review is required again. Regenerate task
routes and revalidate manual routes before approval. Native simulator formats
1/2 retain physical geometry and still require alignment evidence; live version
3 never claims simulator verification.

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
obstacle room is preserved while traversing the entrance cap. New channel
suggestions place the finish beyond the final buoy pair (4.5 m by default,
farther when its required buffer/stopping radius or obstacles need more room).
The route crosses the actual final opening before leaving the channel. Its
exit leg and stopping disk obey the overall planning boundary and all obstacle
buffers; channel containment applies through the exit crossing. The stopping
disk must also be beyond that gate with the selected required allowance.
Inside-channel finishes are rejected for GPS channel tasks, including drafts
submitted by older tabs. In Task setup, **Finish past last gate** suggests a
point from the reviewed final pair without changing chains, boundaries or
buffers. Review the stopping region, confirm and Generate; ordinary finish
editing remains available farther beyond the gate.

Channel generation can start anywhere safe inside the overall planning area;
the boat does not need to be inside the channel overlay first. When reviewed
water extends before the first buoy pair, its upstream cap and sides allow the
approach to reach that pair. Side crossings downstream of the selected entrance
remain forbidden until the ordered final gate has been crossed. All physical-object and overall planning-boundary
buffers still apply, and the complete task remains selected unless the operator
explicitly confirms Remaining section.

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
The browser also ends a generation request after 75 seconds, including response
reading, so an interrupted connection cannot leave Generate spinning indefinitely.
It displays a planning-response timeout and releases the busy controls; it does
not retry or command the boat.
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
confirming the map/setup or validating. Amber outlines show required clearance
around all circular and polygon objects, bands along every planning/channel edge,
the saved start, and the finish radius plus clearance. A larger preferred buffer
is blue. The preview updates with edited positions and buffer settings and is
independent of Planning overlays. Edge bands also cover concave boundaries;
convex polygons additionally show an inset outline. A collapsed inset reports
no remaining room. Polygon outlines use a
slightly conservative sampled visual approximation; backend validation is authoritative.

**S** is the captured attempt start, distinct from the moving boat marker. Its
source and capture time appear in Route review. Amber route sections show the
approach; blue sections show task travel. Buffer geometry is illustrative;
authoritative validation checks every emitted GPS segment after simplification.

### Shared configuration and LiDAR tower zones

**Configure** owns settings reused by gate, slalom, channel and manual moves.
Existing speed/clearance values seed these settings; differing saved task values
become task overrides. Before adding settings, the GCS makes a byte-exact
`workspace-before-course-settings-*.json` backup. Saved maps, routes and manual
queues remain intact. Saving configuration revokes approval and requires planner
regeneration. Merely opening the configuration panel does not change settings.

Tower zones apply to objects explicitly classified as `detector`, including the
purple square towers on the full competition map. Color alone does not classify
a tower. In the normal GPS-map workflow, distances are measured directly from the
boat's planning point to each tower GPS centre; no physical radius is added. Tower hard exclusion replaces
the ordinary required object buffer for that tower; permitted-water boundary
clearance remains required. Include object size, hull and navigation allowances when
choosing distances. The soft distance must be at least the hard distance.

A solid inner outline shows the hard zone; fading purple bands extend to the
soft distance. Shared distances affect all towers without individual overrides.
Select a tower on the map or in the panel, enable **Use individual distances**,
and edit its two distances. Disable the override to inherit shared settings.
Task overrides can also retain a different set of tower preferences.

The initial soft-distance suggestion is 10 m (or the existing required distance
when larger), with Strong avoidance. This is editable planning input, not a
claim about detector coverage. Strong/Very strong increase a squared proximity
cost that decreases to zero at the soft boundary. Costs from nearby towers add.
This balances path length with avoidance; it is not an absolute requirement to
remain outside every soft zone whenever such a route exists. Hard constraints
never yield. Route review reports each soft-zone penetration and its closest
planned centre distance. Actual detector performance remains unverified.

The existing 60-second shared deadline remains. Configured tower planning uses
bounded weighted A* (initial distance-heuristic weight 4), with a distance-based lower bound on
unavoidable approach/escape cost for large zones. It prioritizes a useful route
within the search budget and does not claim a globally optimal path. When the
initial search exhausts its expansion budget, weights 8, 16 and 32 retry that
resolution before refining; the same hard checks and shared deadline apply.
A route found after the initial budget carries a visible review notice. Visibility
simplification samples the same travel/avoidance cost at intervals no greater
than 0.5 m and preserves the searched detour's cost as well as passage order and
hard constraints. Every emitted GPS segment and the stopping disk are checked
against the exact hard geometry. Tower settings freeze with route approval and
are applied again to the actual-position connection at Upload/Start. Boat
mission envelopes, controllers and tuning are unchanged.

### Understanding blocked actions and failures

Task setup shows a **Generation readiness** checklist beside Generate. It lists
only outstanding requirements and links directly to Map, Configure, geometry
review, start selection or confirmation. A blocked gate shows the actual opening
and required width; no buffer is changed automatically. Geometry review unlocks
the setup confirmation. A previous generation failure remains identified as a
failed attempt rather than showing a green readiness card.

Validate, Approve, Upload and Start show their current blocking reason directly
below the button. Live planning requires finite position/heartbeat ages no older
than three seconds; offline planning still explicitly selects Manual start.
Upload remains disarmed-only and Start awaits the approved mission's confirmed
upload. Pending commands cannot be mistaken for completed commands, and an
executing/completed mission is identified rather than prompting another upload.

Progress and action results stay visible in a dismissible notification, including
elapsed generation time and the shared 60-second limit. Structured API failures
show readable reasons and recovery guidance. **Locate on map** centres a reported
conflict and shows its label/buffers. Delayed failures or unknown outcomes for
commands requested in the current browser session raise a visible alert with a
**Review command results** link; inspect vehicle state before retrying. Restored
historical commands do not raise new alerts. No notification retries a command.

Soft-clearance notes are grouped separately from mandatory validation failures;
they do not block approval when mandatory checks pass. Invalid configuration
messages identify the shared settings, task override or individual tower that
needs correction. Task forms and map edits pause during requests, while the
independent boat Stop controls remain available. These are frontend usability
changes; planner constraints, approval rules and boat control are unchanged.

## Optional competition run

1. Review the full map, configure shared course settings, and review/confirm the
   complete assignments for each selected task in Single task mode.
2. In Task setup choose **Competition run**. Select any of Gate, Slalom and
   Channel; the order is fixed. Review the per-task assignments and finish; use **Review run geometry on map**
   to inspect local travel arrows and channel sections.
3. Review one common planning boundary, one run speed and one set of hard/soft
   point/tower zones. These initialize from shared course settings; separate task
   overrides do not configure the run. Correct the run settings independently.
4. Use **Review shared entrance gate**. Explicitly confirm sharing only for a
   matching pair and forward direction. Without sharing, review the separate
   Gate finish and return approach to Slalom. No scoring credit is asserted.
5. Choose Live boat or explicit Manual start and press **Generate competition
   run**. Generation captures a fresh start and has one 60-second budget. Failure
   revokes the prior executable attempt and publishes no partial route.
6. Review task/connector sections, global waypoint ranges, the shared crossing,
   final finish, nominal travel time and execution budget. Suggested seconds are
   `max(300, ceil(2 * route_length / speed + 60))`; explicitly choose a budget
   within the boat's unchanged 10–7200 s limits. Suggestions over 7200 are flagged.
7. Validate → Approve → disarmed Upload/readback → explicit Start. The boat gets
   one ordinary mission (at most 500 GPS waypoints), one speed and one final
   stopped finish. Intermediate endpoints carry no HOLD or settling command.

Saved paths stay hidden on browser startup until Generate. Existing workspaces
get a byte-exact `workspace-before-competition-run-*.json` backup before migration;
maps, individual drafts, manual queues and historical approval files remain.
Inside-channel run starts return to the first reviewed section; position alone
does not establish completion. Runs use `planning_mode: "competition"` and a separate `run_draft`; Single task
uses `planning_mode: "single"` and the existing `draft`. `/api/generate`,
`/api/validate` and `/api/approve` act on the selected mode. `/api/run/prepare`
initializes a run, `/api/run/geometry` derives review overlays, and `/api/run/relationship` checks its entrance relationship.
Approval freezes all run inputs. A changed actual start or progress requires
review; displacement over 1 m requires a fresh run. Start, Stop, manual takeover
and GCS process restart never trigger automatic continuation. After an attempted
Start or process restart, Generate and approve a complete run again.

The UI estimates sections from ArduPilot's waypoint item; this is telemetry
progress, not judge-confirmed task completion. GCS disconnection does not stop
uploaded execution. Survey point JSON may include `captured_at` and
`geographic_reference`; import preserves source capture time and records
`imported_at` separately. Unknown/legacy survey times are unverified. No
unmeasured age expiry rule is applied.
