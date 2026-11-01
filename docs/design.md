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
from the backend to the browser. Mission delivery still uses the boat HTTP API;
radio-only delivery to the onboard application remains undecided. See
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
physical vehicle formats and network transport remain open.

`boat/`, `drone/`, `gcs/` and `simulation/` are independently runnable application
areas with application-level containers. Multiple ROS 2 nodes may share a
vehicle application container. `shared/` holds common definitions, not a service.
Pixhawk firmware and host drivers stay outside application containers. Desktop
and Jetson builds may differ. The removed adapter is not part of this design. Development mission transfer
uses boat-owned loopback HTTP on port 8091. GCS map telemetry independently reads
the simulator's UDP 14550 output, preserving UDP 14551 for the boat app. A host
radio forwarder or configurable direct serial reader supports future shore
telemetry. Physical radio operation and mission transport remain unverified.

## Navigation and accuracy

The playing area is initially assumed clear except for mapped buoys/task
objects and defined boundaries. Automatic handling of unexpected obstacles is
outside the initial scope; a manual operator remains available.

The GCS treats the boat route as a point with a mandatory required buffer
to obstacle surfaces and an optional preferred buffer that may yield locally. The operator includes hull size, survey/GPS
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
- [Local course details](<competition_docs/AIMM-ICC Competition Course Details 12-13 2025.pdf>)
- [Local rules](<competition_docs/Rules and Regulations _ AIMM ICC.pdf>)
- [Official rules and competition document links](https://www.trine.edu/innovation-one/aimm/rules.aspx)

The local course filename is dated December 2025. Rules may change; these
documents provide design context rather than a guarantee of final event rules.

## GPS assisted planning extension

The accepted next scope adds backend planning for separate gate, slalom and
channel missions, using one persistent reviewed GPS object map and task-specific
course roles/drafts. Live point imports require no simulator identity and are
never simulator verified. Original observations are retained separately from
operator corrections, including explicit dimension assumptions. Course geometry,
direction, entry/exit/finish and bounded planning area require operator review;
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
mapping and detection-zone models remain deferred. See the GCS guide for schemas
and the milestone for measured validation limits.

Manual move provides an independent saved waypoint queue for repositioning.
Selection captures a fresh boat start when available; map clicks append ordinary
GPS waypoints and the last point is the stopped finish. The existing clearance,
review/approval, upload and explicit Go/start path applies. Switching back restores
each task draft. This uses ordinary boat mission execution, without introducing
GUIDED control or continuous GCS steering.

### Full competition workflow and approach semantics

The full competition scene is the primary development/operator test map; the
small slalom fixture is regression coverage. The normal GCS uses Map → Task
setup → Route review with explicit drawing/edit modes and advanced controls
collapsed. Labeled task suggestions are unconfirmed, use only imported GPS
geometry/labels and preserve selected speed/buffers. Different map imports
archive prior drafts rather than reusing incompatible identities.

The planning boundary and all physical obstacles constrain the complete task
approach. Before the finite task entry is crossed, extended passage planes do
not prohibit approaching from another part of the competition map. Channel
containment becomes active at entry; confirmed passage order/direction/sides
remain mandatory thereafter, and the selected finish disk must be inside the
channel and clear. This makes independent channel attempts from elsewhere on
the course possible without weakening obstacle clearance.

### Proposed general-course planning revision (2026-11-01)

Confirmed operating requirements: the course may have arbitrary geographic
orientation, uneven buoy spacing, staggered gates and curved channel boundaries.
Neither cardinal alignment nor collinearity is a valid prerequisite. The
following is a proposal for review, not implemented planner behavior or new
simulator/physical acceptance.

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

Implementation should first remove straight-course setup assumptions and define
start/progress semantics, then adapt planning/UI and qualify rotated, translated,
staggered, uneven and bent full-course fixtures. Verify safe starts inside and
outside channels, explicit partial retries, blocked openings, stale telemetry,
changed starts after approval, narrow bends and ambiguous assignments. Static
geometry checks must be followed by full-map browser workflows and independent
simulator whole-hull passage/clearance/finish evaluation. Rotation equivalence is
about valid task behavior and clearance, not identical grid-generated waypoints.

Open decisions before implementation: whether channel attempts always require
the official entrance or may explicitly resume inside, and how the operator
defines permitted channel edges between sparse buoy observations. Existing
finite-entry behavior remains in effect until this proposal is implemented.
