# System design — working draft

Status: working design, with Milestone 1 simulator acceptance completed. See
[Milestone 1 results](milestone1.md#recorded-simulator-results) for implemented interfaces and
measured acceptance limits. Choices marked provisional and open questions
must not be treated as settled requirements.

## Goals and scope

Develop reliable navigation in this order: gate passage, slalom, then the Evade
channel. Initially test each as a separate mission. Keep the system simple and
develop primarily in simulation for the foreseeable future. A physical test
boat already supports Pixhawk GPS waypoint missions.
The test boat runs ArduPilot, matching the retained simulator's firmware family.
Exact firmware versions and competition-boat configuration remain to be verified;
the drone's firmware has not been confirmed.

The boat initially navigates all three tasks without camera input. Whether that
provides sufficient clearance must be measured. Boat perception may be added
later if needed. Other competition tasks are outside the current design scope.

## Responsibilities and workflow

1. An operator defines the drone survey area and altitude using an existing
   flight-planning tool. The drone follows a predefined coverage flight.
2. The boat waits in a designated safe area during survey and review.
3. The drone detects buoys and other relevant objects, estimates their GPS
   locations, and produces one consolidated object map after the survey.
   One survey covers the whole course; reuse its map for the separate gate,
   slalom and Evade missions. Show the map capture time during review. How long
   the map remains usable as objects move must be established through testing;
   reuse does not guarantee that it stays accurate for the entire run.
4. The drone lands before the boat begins its route. Marker-based landing is a
   tentative direction; its mechanism and operational details are deferred.
5. The operator reviews the map in the GCS. They can correct object positions
   and labels, while retaining the original survey for comparison, and assign
   course roles such as gate buoy or detector tower.
6. The operator specifies course order and which side to pass relevant buoys.
   The GCS generates a GPS route with clearance margins. The operator can move
   waypoints; clearance checks run again after edits.
7. The operator approves the complete route before execution. The boat Jetson
   uploads the mission to its Pixhawk, coordinates execution, and reports
   progress. The Pixhawk follows the waypoint mission itself.
8. The GCS monitors execution. Continuous GCS guidance is not required.
9. Each separate mission ends with the boat stopping in a designated finish
   area and awaiting the operator. Do not automatically return to the dock or
   start the next challenge. Exact Pixhawk stopping behavior remains to be
   verified; stopping does not imply guaranteed station keeping.

The development GCS is a web application accessed through a browser on the
desktop at localhost:8080, using React/Leaflet and FastAPI. Its live map uses
passive MAVLink telemetry, with configurable UDP or serial connections, streamed
from the backend to the browser. Mission delivery uses the boat HTTP API.
The selected field configuration uses Wi-Fi/Ethernet to the Jetson for mission
commands/status and a separate RFD MAVLink link for passive shore telemetry.
The GCS Connections dialog selects and persists Simulator/Field API and passive
telemetry profiles; environment variables seed initial settings. Boat bind
interface and local transport remain startup settings. Simulator loopback
defaults remain available for explicit recovery. Radio-only mission
delivery remains undecided. See
[live position](../gcs/README.md#live-map-telemetry) for implemented behavior and limits.

The GCS starts with objects on a plain map; object labels, station annotations
and planning overlays have independent toggles. Route waypoints and clearance
margins are shown from above. A stitched aerial image and a custom drone survey interface
are not prerequisites.

## Data and application boundaries

- **Object map:** estimates of where objects are, their detected appearance,
  and operator-assigned roles. It is not a route.
- **Route:** approved waypoints describing where the boat should travel.
- **Task instructions:** actions associated with a mission; detailed semantics
  remain open. Initial navigation missions do not require mechanisms for other
  competition tasks.
- **Status:** vehicle and mission progress reported to the GCS; exact contents
  remain open.

The drone sends its map to the GCS. The GCS sends the prepared mission to the
boat. Both vehicles report status. No initial direct boat-to-drone link is
required. Development delivery/acknowledgement now uses the boat HTTP operation API;
physical vehicle operation remains unverified. The selected field transport is
HTTP over a trusted private Wi-Fi/Ethernet network. The shore API target is
editable at runtime; switching targets expires every tab's mission authority
and requires fresh map/run review.

`boat/`, `drone/`, `gcs/` and `simulation/` are independently runnable application
areas with application-level containers. Multiple ROS 2 nodes may share a
vehicle application container. `shared/` holds common definitions, not a service.
Pixhawk firmware and host drivers stay outside application containers. Desktop
and Jetson builds may differ. The removed adapter is not part of this design. Development mission transfer
uses boat-owned loopback HTTP on port 8091. GCS map telemetry independently reads
the simulator's UDP 14550 output, preserving UDP 14551 for the boat app. A host
radio forwarder or configurable direct serial reader supports future shore
telemetry. The boat API can explicitly bind to a Jetson LAN interface and the
shore GCS can target its URL; localhost is the default. Physical radio/network
operation remains unverified.

## Navigation and accuracy

The playing area is initially assumed clear except for mapped buoys/task
objects and defined boundaries. Automatic handling of unexpected obstacles is
outside the initial scope; a manual operator remains available.

The GCS treats the boat route as a point with a mandatory required buffer
to imported object GPS centres and an optional preferred buffer that may yield locally. No object radius is added. The operator includes object size, hull size, survey/GPS
error, tracking/turn error, buoy movement and mandatory extra room in the required value. The GCS
checks the planned segments and finish region against all physical obstacles without adding hidden hull or
tracking allowances. It does not establish that the chosen buffer is sufficient
for the actual boat or speed. Whole-hull evaluation remains a simulator test tool.

If no acceptable passage can be established before execution, do not start the
mission. Another survey is a possible future recovery option; automatic
resurvey is not required initially. Responses to faults encountered during
execution are still open.

Mission target speed is directly configurable in the GCS as a finite positive
value. Mission authorization has no navigation-profile, geometry-hash, measured
speed/turn envelope or tuning-gain dependency. ArduPilot tuning is separate from
boat/GCS mission operation; simulation tuning/calibration tools live under
`simulation/`. Physical firmware tuning remains part of vehicle setup.

The historical Milestone 1 acceptance used a 2.0 m/s target and frozen measured
settings; see its acceptance table. It is evidence for that configuration, not
a restriction on new mission speeds or proof for arbitrary buffers/settings.

For Evade, the proposed strategy is to identify detector towers and plan a
route away from them within the permitted channel. Whether this actually avoids
detection depends on detector coverage and available space; it is an unverified
strategy, not a demonstrated capability.

## Control and perception choices

A small state machine is the provisional coordination approach. The current
workflow does not justify a behavior tree. State definitions, fault transitions
and detailed ROS decomposition remain open.

Loss of the GCS connection alone does not stop an uploaded mission. A dedicated
RC operator can take control through the Pixhawk independently of the Jetson
and GCS. Manual control takes priority; resuming autonomy requires an explicit
command. Detailed takeover mechanics are a small integration requirement,
not the focus of initial development. Positioning/vehicle faults are separate
from GCS link loss; their responses remain to be decided.

For drone mapping, a fixed downward-facing camera is the working assumption,
pending confirmation. Camera model, lens, altitude range, geolocation method
and timing/calibration approach remain open. A homemade gimbal is not assumed
to improve geolocation accuracy. Survey altitude should be configurable and
its usable range established through testing.

## Competition scene extension

The default simulator scene now represents the full reference competition course.
This is a fixed scene/map extension: manual custom routes use obstacle clearance
checks without gate/slalom passage requirements. Version 2 simulator object maps
add physical circle/polygon obstacles, station annotations and start-pose metadata;
version 1 buoy maps remain supported. The boat mission interface is unchanged.
See [scenario geometry and estimates](../simulation/scenarios/README.md).
Challenge mechanisms and scoring remain deferred; GPS assisted planning is described below.
The historical accepted slalom scene remains available as `SCENARIO=slalom`.

## Development and acceptance

The current first milestone is [camera-free slalom through the web GCS](milestone1.md).
Export the running simulator's buoy locations as a GPS object map, import it
into a minimal GCS, manually prepare and approve a route, and execute it through
the boat application and ArduPilot. Drone mapping remains deferred. The GPS assisted planner is a subsequent extension. This brings the GCS earlier than the original development order.

Begin with boat-only execution of a manually supplied mission and keep that
independent test path available. Then integrate the GCS and verify gate/slalom
passage using the perfect simulator map before introducing survey errors.
Simulator truth belongs in map export and evaluation tools, not the boat
application. Completion must demonstrate actual passage, including whole-hull
clearance, rather than only waypoint acceptance. See the milestone for scope,
implementation steps, evidence and acceptance criteria.

Subsequent stages are to quantify navigation errors and clearance, compare
route following on the physical boat, develop drone mapping independently
against measured locations, qualify GPS assisted GCS route generation, and integrate
the drone workflow. Exact acceptance thresholds remain to be agreed.
Simulator results alone do not establish real-world positioning accuracy or
competition-boat dynamics.

## Open decisions

The first boat-only slice selects ROS 2 Jazzy and direct `pymavlink`, with local
JSON mission files and ROS services for testing. See [boat execution](boat_execution.md)
for the implemented semantics and limits. These local interfaces do not settle
the vehicle-GCS protocol or final clearance/acceptance settings.

- First-milestone mission input, progress and completion semantics.
- Route geometry, turning behavior, operating speed and clearance validation.
- Error measurements, numeric margins and GPS/RTK hardware availability.
- Drone camera, geolocation, survey settings and map quality evaluation.
- Map freshness limits and when an additional survey is necessary.
- Mission transfer/acknowledgement and vehicle-GCS transport.
- Vehicle faults and safe responses during execution.
- Drone launch/recovery details, including marker-based landing.
- Competition clarification: gate/slalom numbering differs between the course
  document and rules; GCS operator involvement and Evade detector coverage also
  need clarification before claiming competition compliance.

## References

- [Simulator setup](../simulation/docs/SETUP.md)
- [Hardware knowledge](hardware.md)
- [Local course details](<competition_docs/Course and Competition Details.pdf>)
- [Local rules](<competition_docs/Rules and Regulations _ AIMM ICC.pdf>)
- [Official rules and competition document links](https://www.trine.edu/innovation-one/aimm/rules.aspx)

The supplied course concept document is historical. Rules may change; these
documents provide design context rather than a guarantee of final event rules.

## GPS assisted planning extension

The implemented [map compiling workflow](map_compiling.md) adds observation cleanup,
bounded local-geometry gate/slalom/channel recognition, ranked proposals, operator
hints and reviewed task templates. Original observations remain separate; JSON
save/reload restores assignments for review without routes or execution authority.
Recognition does not change navigation clearance or physical-boat acceptance.

The accepted next scope adds backend planning for separate gate, slalom and
channel missions, using one page-session reviewed GPS object map and task-specific
course roles/drafts. Live point imports require no simulator identity and are
never simulator verified. Original observations are retained separately from
operator corrections. Live objects are points, with total hard/soft distances
measured directly from their GPS centres. Course geometry,
local direction, passage order, permitted boundaries and finish require operator review;
geometry suggestions do not confirm assignments. Station annotations are optional.

Deterministic metric grid A* carries ordered passage progress and incoming
direction; all edges enforce physical clearance, finite directed openings, turn
sides/order and channel containment. Failed searches refine from 0.25 to 0.10
and 0.05 m, with bounded effort and explicit exhaustion diagnostics. Required
buffer remains mandatory; preferred buffer starts equal and may yield locally,
with every shortfall reported. Identified detector proximity is a bounded
preference, never a constraint override or detection-avoidance claim. Final GPS
waypoints undergo independent segment/finish/course validation after simplification.
The boat still receives ordinary supplied routes and remains independently testable.

Generate/Edit/Validate/Approve/Upload/Start stay separate. Map/setup/settings edits
and task switches revoke authority while retaining editable drafts. Retries use
a fresh safe start and new review/approval without replaying earlier tasks.
Actual-start safety checks remain in force before upload/start. Each task stops
at its selected finish; only an explicit subsequent action starts another task.
Physical/radio qualification, controller optimization, online replanning, drone
mapping and measured detection models remain deferred. See the GCS guide for schemas
and the milestone for measured validation limits.

Manual move provides an independent saved waypoint queue for repositioning.
Selection captures a fresh boat start when available; map clicks append ordinary
GPS waypoints and the last point is the stopped finish. The existing clearance,
review/approval, upload and explicit Go/start path applies. Switching back restores
each task draft. This uses ordinary boat mission execution, without introducing
GUIDED control or continuous GCS steering.

### Full competition workflow and approach semantics

The full competition scene is the primary development/operator test map; the
small slalom fixture is regression coverage. The normal GCS uses Map → Configure → Task
setup → Route review with explicit drawing/edit modes and advanced controls
collapsed. Labeled task suggestions are unconfirmed, use only imported GPS
geometry/labels and preserve selected speed/buffers. Different map imports
archive prior drafts rather than reusing incompatible identities.

The planning boundary and all physical obstacles constrain the complete approach.
Only finite local passage crossings affect progress; unrelated extended planes
do not block return approaches. Each generated attempt captures its start and
selected progress, and approval freezes those inputs for actual-position checks.

### General-course planning (2026-11-01)

Confirmed operating requirements: the course may have arbitrary geographic
orientation, uneven buoy spacing, staggered gates and curved channel boundaries.
Neither cardinal alignment nor collinearity is a valid prerequisite. The
implementation uses version 2 task geometry and separate attempt metadata.
Qualification results and limits are recorded in the milestone.

- Keep the reviewed GPS object map fixed while the boat moves. Use one fixed
  local metric reference for geometry; the boat start is a separate live
  observation. Preserve original observations and dimension assumptions.
- Represent task meaning separately from objects: ordered gate pairs, ordered
  slalom turns with reviewed passing sides, and both ordered channel boundary
  chains using intermediate vertices. Suggestions are editable and unconfirmed;
  IDs, colors, nearest-neighbor pairing or one global heading cannot establish
  task order by themselves. The operator reviews the permitted water boundary;
  sparse buoy positions do not prove its shape.
- Use local travel directions along the task. A gate crossing derives its
  orientation from the actual pair and reviewed course order. Slalom passing
  sides are relative to local progress. Channel geometry follows the reviewed
  chains, including bends; any centerline guides progress rather than forcing
  the boat through obstacle-blocked midpoints. Reject crossed/ambiguous chains
  rather than replacing them with a bounding rectangle or convex hull.
- Default new attempts to a fresh boat-position snapshot with timestamp, shown
  on the map before generation. Offline/manual start remains an explicit mode.
  Keep saved task setup separate from the start captured for a new attempt.
  Approval freezes the route/start/map/settings; later motion does not silently
  rewrite it. Existing actual-position checks still apply before execution.
- Derive a safe connection to the task from that snapshot. Channel approaches
  join through the allowed beginning opening, then obey channel containment.
  A safely inside start can avoid an artificial entry crossing only when task
  progress semantics permit it. Being spatially inside does not establish that
  earlier required passages were completed. Normal full-task attempts and
  explicit reviewed resume/reposition attempts must remain distinguishable.
  Manual connection/entry correction belongs in advanced setup; physical task
  entry/exit requirements remain authoritative.
- Retain required obstacle/boundary clearance, optional preferred room, and
  separate route/course/finish validation. Plan around actual geometry with the
  existing bounded search where feasible. Validate all emitted GPS segments
  after simplification; smoothing must not cut corners. A start already inside
  an exclusion buffer requires an explained recovery, not relaxed clearance.
- Present Load/review map → confirm task meaning and finish → plan from boat →
  review/validate → approve → upload/readback → explicit Start. Maintain separate
  task drafts and manual waypoint queues, persistent boat controls, and buffer
  previews before validation. Show approach versus task sections, task order,
  safe-water limits, start age and located failure diagnostics. Failure must
  distinguish invalid setup, proven blockage and exhausted search effort.
- Retain boat-owned supplied-waypoint execution and explicit stop at each task
  finish. Mapping remains an import boundary for now; drone mapping, unexpected
  obstacle avoidance and continuous replanning remain deferred.

The implementation separates task geometry and attempt progress before search
and UI handling. Qualification covers rotated, translated, staggered, uneven
and bent fixtures; measured limits are recorded in the milestone. Verify safe starts inside and
outside channels, explicit partial retries, blocked openings, stale telemetry,
changed starts after approval, narrow bends and ambiguous assignments. Static
geometry checks must be followed by full-map browser workflows and independent
simulator whole-hull passage/clearance/finish evaluation. Rotation equivalence is
about valid task behavior and clearance, not identical grid-generated waypoints.

Agreed defaults are **Suggest, then confirm**, **Live boat**, and **Full task**.
Generate captures position and heartbeat ages no greater than three seconds;
offline planning explicitly selects Manual start. Remaining section suggestions
never confirm themselves. The operator confirms or changes the first included
section; excluded sections receive no completion credit. Movement over 1 m after
that selection requires another review. Full task retains every assigned passage
and shows any return approach. Safe starts in the selected first channel cell
activate containment immediately; starts in later full-task cells retain the
return to the beginning. A partial selection behind an inside start is rejected
with instructions to review the first included section.

Channel boundaries connect all ordered chain points, with operator correction.
Progress connections pair the union of normalized chain-vertex distances.
Crossing chains, self-intersections and sections outside permitted water require
correction. The entrance uses an end-cap allowance where needed; short first
intervals retain the finite beginning opening. The final crossing lies on the
actual last buoy pair, followed by the reviewed stopping region beyond it.
The permitted polygon is never expanded automatically. Outside connections enter through
the selected beginning opening. Its entrance cap is traversable during connection;
side boundary and physical obstacle buffers remain mandatory. Inside starts
already in any boundary exclusion band are rejected. Finish clearance includes
the entire stopping disk. New channel suggestions place that disk beyond the
actual final buoy pair, with required room beyond the gate plane. The route
crosses that finite opening in order before channel containment ends; its exit
leg and stopping disk retain overall planning-boundary and obstacle checks.
The reviewed polygon is not expanded. GPS channel task finishes before that
gate are invalid, including legacy drafts submitted from older browser tabs.
An explicit Finish past last gate suggestion updates only the finish and revokes
the prior route/approval for review. An advanced connection crossing remains available.

An outside channel attempt may start anywhere safe in the overall planning
area. For reviewed water extended upstream of the selected beginning buoy pair,
approach boundary checks use channel edges clipped to the downstream side of
that opening. This keeps the upstream extension accessible while preventing
side/exit entry farther along the task. After the first crossing, the complete
reviewed channel containment checks apply through the final gate.
Generation retains the shared
60-second budget; a separate 75-second browser request timeout ends stalled
response waits with a visible error and releases the busy state.

Workspace version 2 archives legacy state before migration, keeps saved routes,
manual queues and assignment candidates, and revokes affected planner approvals.
New attempts retain the complete setup even when selecting a partial run. Setup
identity and the captured start must match at validation; actual-position checks
at Upload/Start must preserve the approved progression and safe connection.
Boat mission envelopes and GPS object-map formats are unchanged.

### Shared course configuration and tower preferences (2026-11-03)

The accepted workflow adds a map-focused Configure step before task selection.
Shared speed, ordinary required/preferred clearance and tower avoidance settings
apply across tasks, with explicit task overrides and individual tower distance
overrides. Preserve existing maps, assignments, saved routes and manual queues;
back up workspaces before adding settings. A fresh browser session or backend restart shows no saved
course paths; Generate explicitly reveals a route for the selected task in that
session. Manual moves remain an explicit independent workflow.

Live objects, including towers, use GPS points without an object radius. A
configurable hard centre-distance zone is mandatory, and a larger soft
centre-distance zone contributes a decreasing
squared proximity cost. Tower-specific hard clearance replaces ordinary object
clearance at that tower; boundary containment and other obstacle buffers retain
their meanings. These are distances between the boat planning point and the object GPS point,
without hidden object, hull or error allowances. Native simulator formats retain
physical geometry for compatibility and independent evaluation; the normal
competition practice map uses points. A purple fading overlay previews the settings. Soft-zone traversal
is reported for review; weighted avoidance trades distance against proximity
rather than asserting global maximum minimum clearance or detection avoidance.

Settings changes revoke approval and require generation/review. Settings are
materialized authoritatively into drafts and frozen with approval; the boat still
receives ordinary GPS waypoints. Tower planning uses bounded weighted A* (initial distance weight 4; bounded retries at 8/16/32), with a distance-based lower
bound on approach/escape cost; it makes no global optimality claim.
Simplification preserves sampled avoidance cost
so it cannot discard a searched detour merely because a direct segment satisfies
the hard buffer. Exact final segment/finish validation and the shared 60-second
search/simplification deadline remain. Continuous replanning and measured LiDAR
detection behavior are outside this change.

### Drone point-map contract (2026-11-03)

A JSON object containing `points` (or a bare point list) supplies latitude and
longitude in degrees, with optional `id`, `object_type` and `color`. Explicit
`"object_type": "unknown"` is supported; omitted types become `unknown`, and
omitted IDs receive stable identifiers within the imported list. Each row must
represent one consolidated object, not repeated detections. Types do not confirm
task membership or passage order. No drone routes or physical dimensions are
required. Legacy dimension fields in simple point rows remain in original
observations but do not affect planning.

The GCS represents live objects as `type: point` in version 3 maps. Hard and soft
distances are measured directly from their centres, including tower overrides,
gate feasibility, starts and stopping regions. Point objects cannot carry a
hidden radius or footprint. Existing live workspaces are backed up byte-for-byte
before conversion; original observations and saved routes/manual queues remain,
while approval and map/task review are invalidated. Regenerate planner routes
and revalidate manual routes after reviewing total centre-based allowances.

## Fresh-session Run builder and reviewed return

Run builder is the primary Map → Configure → Build run → Review & execute workflow. All
planner state is in memory under an ephemeral page-session ID. New run, reload,
new tab and backend restart start empty. Imports reset course-specific inputs
and shipped settings, including when object IDs are reused. Existing files and
logs are retained outside planner inputs. Reset never commands or clears an
uploaded boat mission; actual boat status and priority Hold / Stop remain live.
Earlier persistent-workspace and fixed-order workflow descriptions in this
design are historical and superseded by this section.

A run contains ordered `steps` with unique instance IDs, type and independent
setup. Complete Gate, Slalom, Channel and exact Manual waypoint cards may appear
in any order, including repeats. Shared speed, obstacle/tower settings, common
boundary and start selection live in a dedicated Configure workspace. Build run
uses direct task buttons and a compact sequence above a persistent map and
selected-task editor. Configure uses three compact settings columns, switching
to category selection in narrower panels; its map preview remains optional.
The task strip holds compact instance chips and one selected-instance action
toolbar. Assignments, finish/water and advanced settings occupy separate editor
views; local heading overrides remain in Advanced. Geometry review and task
confirmation stay below the content pane. The application
uses a viewport-sized shell with compact toolbars and a status bar.
Only the editor and task strip scroll; the map and vehicle controls stay in place,
and Generate remains below the scrolling task editor. Errors and planning progress
use a message dock without covering controls. Task selection
frames geometry; gate rows focus an explicit named pair and crossing arrow.
Map-click endpoint replacement revokes task review and generated authority.
Blue/purple/amber configuration sections distinguish obstacle clearance, towers
and navigation limits; task colors match selected geometry without recoloring
physical buoy symbols. Editors expose assignments,
local directions, order/sides, channel chains, permitted water and endpoints.
Duplication copies one configuration into a new instance. Partial-task recovery,
saved presets, setup copying and per-card speeds are outside this workflow.

Map loading now suggests the common planning boundary before map confirmation.
The GCS projects every mapped object/physical footprint, station annotation and
known start into the fixed local metric frame, fits a rectangle using the
observations' convex hull edge orientations, and adds an editable 10 m padding
on all four sides. Arbitrary course rotation is supported without cardinal
alignment or inferred task headings. The map-review action confirms the shown
outline together with the observations. Explicit regeneration, corner dragging
and manual replacement are available in Map and Configure; the boundary never
tracks moving telemetry or expands silently for later tasks. A suggestion does
not establish permitted water or replace reviewed channel chains. Existing
boundary clearance, route invalidation and execution approval checks still apply.

Generation captures a fresh start and plans each complete task from its preceding
endpoint. Manual waypoints are retained exactly and all joins checked. One shared
60-second deadline covers search, simplification and final segment validation;
no partial or previous executable route survives failure. The starting gate is
a separate Gate task; Slalom begins with the first turn and retains its exit
gate. Add Gate before Slalom to include both, or run Slalom on its own. Each card
produces its own block; there is no shared crossing or repeated starting-gate
requirement in Slalom. Recognition retains the starting pair as a geometric
reference, without adding it to Slalom's required passages. Channel entry, ordered sections,
containment and actual final-gate exit are retained wherever its card appears.

The complete run uses one ordinary ≤500-waypoint boat mission, one speed and
one editable 10–7200 s execution budget. Intermediate endpoints are transit;
only the final endpoint settles and HOLDs. Review shows route/connectors, instance
progress, clearance findings and time budget. Validate → Approve → Upload/readback
→ Start remain explicit. Start consumes authority and rechecks actual position;
interrupted runs require fresh generation and approval. Asynchronous results
must match session, input revision and interruption epoch before publication.

A successfully acknowledged run Start freezes its captured start as this
session's Return now target, displayed as a 1 m stopping area. It remains after
completion/Stop and is never overwritten by return generation or return Start.
Return now immediately sends priority Stop independently of planner locks and
consumes the interrupted run's authority. Preparation requires confirmed HOLD,
fresh position/heartbeat and speed ≤0.20 m/s. Task-free bounded navigation then
plans independently from the sampled current position against the current
reviewed map, boundary and shared settings. Inside reviewed channel water,
retain side buffers/containment until exiting through the beginning opening.
Unsafe targets, telemetry/HOLD failures, search failures and transfer failures
initiate no return movement and report a specific cause.

Return is opened for review and requires Validate → Approve, explicit Disarm
before replacement Upload/readback, then explicit Start. It uses the existing
boat waypoint executor, with finish radius 1 m, speed ≤0.20 m/s for at least 5 s,
then HOLD. There is no automatic return card or interrupted task resume. Reset
and restart remove the target. Boat-only manual mission operation is unchanged.
Physical-boat/radio qualification, controller tuning and continuous replanning
remain outside this revamp. See the GCS guide and milestone for evidence limits.

Survey developer tools perturb the imported point list while keeping the map
reference and physical scene fixed. Reviewed assignment IDs are explicit inputs;
the harness never reconstructs missing roles from physical truth. Capture time
comes from the source and import time is separate. Missing/legacy capture times
are unknown/unverified; age alone imposes no expiry. Seeded offset/point-error
sweeps are exploratory inputs, not accuracy estimates. Independent physics
assessment includes omitted objects, polygon props, hull passages, contacts,
channel containment and stopped settling. Missing physics/contact proof makes
acceptance inconclusive. See the simulator guide for isolated commands and the
milestone for measured results and limits. Controller tuning, curves, physical
qualification, drone flight automation and official scoring remain deferred.
