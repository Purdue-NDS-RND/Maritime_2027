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

The initial GCS view shows labeled objects, route waypoints and clearance
margins from above. A stitched aerial image and a custom drone survey interface
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

The current GCS treats the boat route as a point with one configurable total
clearance buffer to buoy surfaces. The operator includes hull size, survey/GPS
error, tracking/turn error, buoy movement and extra room in that value. The GCS
checks the planned segments and finish region without adding hidden hull or
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

## Development and acceptance

The current first milestone is [camera-free slalom through the web GCS](milestone1.md).
Export the running simulator's buoy locations as a GPS object map, import it
into a minimal GCS, manually prepare and approve a route, and execute it through
the boat application and ArduPilot. Automatic route generation and drone mapping
are deferred. This brings the GCS earlier than the original development order.

Begin with boat-only execution of a manually supplied mission and keep that
independent test path available. Then integrate the GCS and verify gate/slalom
passage using the perfect simulator map before introducing survey errors.
Simulator truth belongs in map export and evaluation tools, not the boat
application. Completion must demonstrate actual passage, including whole-hull
clearance, rather than only waypoint acceptance. See the milestone for scope,
implementation steps, evidence and acceptance criteria.

Subsequent stages are to quantify navigation errors and clearance, compare
route following on the physical boat, develop drone mapping independently
against measured locations, add automatic GCS route generation, and integrate
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
