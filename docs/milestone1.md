# Milestone 1: camera-free slalom through the web GCS

Status: in progress. The first boat-only execution slice is implemented; see
[boat execution](boat_execution.md) for behavior and actual validation limits.

Read this alongside the [system design](design.md). This document defines the
current first milestone and supersedes the earlier plan to defer the custom
GCS until after boat-only development. Boat-only testing remains the first
implementation step and must remain possible without the GCS or drone.

## Outcome

Start the retained slalom simulation, import the true buoy locations into a
minimal web GCS, manually prepare and approve a GPS route, send it to the boat
application, and have ArduPilot execute it without boat-camera input. Observe
progress and independently verify correct passage and clearance.

Simulator truth substitutes for the drone's object map in this milestone.
Automatic route generation comes after this milestone; initially the operator
places and edits waypoints in the GCS.

## Scope and boundaries

- Use the existing fixed slalom scene in calm water. It contains entrance and
  exit gates and four alternating red/green turn buoys. Its dimensions are
  provisional simulator geometry, not official competition dimensions.
- The GCS is a browser application, with React and FastAPI as the provisional
  stack. Keep the interface limited to map import, route preparation, mission
  approval/upload/start, and boat progress.
- Mission speed and minimum clearance are configurable. Reject routes that
  fail the selected clearance check; do not silently shrink the margin.
- The boat application coordinates the mission and communicates with ArduPilot.
  ArduPilot follows the uploaded waypoint mission. The GCS does not bypass the
  boat application to control the Pixhawk.
- Simulation, boat and GCS remain separate application runtimes. Use ROS 2
  within the boat application. Do not restore the removed adapter or make
  cameras, MAVROS, Nav2, onboard mapping or continuous replanning prerequisites.
- Boat-GCS transport, mission formats and integration libraries remain open.
  This document does not prescribe ROS packages, message schemas or APIs.

## End-to-end flow

1. Start the simulator with `WATER=calm SCENARIO=slalom make -C simulation run`.
   Record the resolved scene and run identity for later evaluation.
2. A simulation-only export tool obtains the resolved buoy positions and types
   and produces an object map with GPS coordinates for GCS import. Use the
   resolved scene rather than assuming an arbitrary source file matches the
   running world. The current scene renderer already records local model
   positions in a generated manifest; geographic conversion still needs work.
3. Verify the local-world-to-GPS conversion against ArduPilot's geographic
   reference and the simulator's axes. Check more than a single origin point:
   scale, direction and heading errors must not create a plausible-looking but
   misplaced map. Do not assume local X is north or east without verification.
4. Import the map into the GCS and display labeled buoys and the boat's reported
   position. Object coordinates describe buoy locations, not boat waypoints.
5. The operator identifies the gates and passing order/sides, places and edits
   route waypoints, and selects speed, clearance and a finish area. Show the
   route and clearance margins and rerun checks after edits.
6. The operator approves the route. The GCS sends the complete mission to the
   boat application, which uploads it to ArduPilot and confirms acceptance
   before execution. Exact approval, upload and start mechanics remain to be
   specified; do not treat a transmission attempt as successful acceptance.
7. ArduPilot executes the route. The boat reports mission progress and vehicle
   status to the GCS. The boat needs neither simulator object truth nor
   continuing movement commands from the GCS.
8. After clearing the exit gate, the boat stops in the designated finish area
   and waits for the operator. Verify the actual ArduPilot stopping behavior;
   do not assume station keeping or automatically return to the dock.
9. An independent simulation evaluator records the actual trajectory, passage
   order, buoy contacts and minimum whole-hull clearance.

## Implementation order

- [x] Establish a boat-only execution path for a manually supplied GPS mission,
  including upload acceptance, start, progress and completion. Keep this path
  usable independently of the web GCS. The first open-water example passed;
  this is not gate/slalom or whole-hull acceptance. See [runtime evidence](boat_execution.md#runtime-evidence).
- [ ] Export the resolved simulator object map and verify its GPS alignment.
- [ ] Build the minimal GCS map view and manual waypoint editor, configurable
  speed/clearance, and route clearance checks.
- [ ] Connect GCS mission approval/upload/start and progress reporting through
  the boat application.
- [ ] Demonstrate simple gate passage before attempting the complete slalom.
- [ ] Evaluate the full slalom, repeat the run, and record measured results.

These are steps within one milestone, not additional applications or services.
Implement only the definitions and interfaces needed for these steps.

## Acceptance

The milestone is complete only when the end-to-end run demonstrates:

- The imported buoy map agrees with the running scene and ArduPilot's GPS
  frame within an explicitly selected conversion tolerance.
- A route can be manually prepared, edited, checked and approved in the GCS;
  a route that violates the selected clearance is rejected.
- The boat receives the complete approved mission, confirms ArduPilot upload
  acceptance, and provides meaningful execution progress and final status.
- The entire hull passes both gates in order, takes the intended side of each
  turn buoy, makes no buoy contact, and maintains the selected minimum clearance
  along the executed trajectory, including turns and stern passage.
- The boat reaches the finish area and stops within agreed position/speed
  tolerances, without automatically proceeding elsewhere.
- Execution uses no camera input or simulator-truth subscriptions in the boat
  application. Simulator truth is confined to map export and evaluation tools;
  the GCS consumes the exported map, not a live truth-based steering feed.
- After upload/start, losing the GCS connection alone does not stop or redirect
  the mission. Preserve a manual takeover/stop path for testing; this does not
  establish acceptance of physical RC hardware.
- The result is repeatable with the same recorded scene, mission and settings.

Before declaring acceptance, agree on and record the test speed, hull/buoy
geometry, clearance definition and margin, coordinate tolerance, finish
tolerances, timeouts and repeat count. No numeric thresholds are selected yet.
Measure actual passage independently of ArduPilot waypoint-reached events;
waypoint acceptance or a healthy container alone does not prove completion.

Keep the input map, approved mission, configuration, reported progress and
evaluation results together under ignored `simulation/logs/`. Document exact
run commands, outcomes, failures and limitations in the implementation handoff.

## Deferred work and limits

No drone application, detection model, geolocation from images, marker landing,
automatic route generation, Evade detector strategy, stitched aerial imagery,
or other competition task mechanisms are required here.

This uses a perfect simulator map and does not establish camera-free feasibility
on the real boat. Subsequent experiments introduce survey/GPS errors and buoy
movement, evaluate clearance limits, and compare with physical route following.
The retained BlueBoat dynamics are not calibrated competition-boat dynamics.

## Decisions needed during implementation planning

- Minimal mission input/transfer format, transport and acknowledgement.
- Boat-ArduPilot integration library and command ownership details.
- Route clearance method, turn behavior and relevant ArduPilot settings.
- Progress/completion semantics and responses to execution faults.
- Numeric acceptance settings and independent evaluation method.

Choose these to support the milestone; do not expand into a general-purpose
autonomy framework or treat unresolved choices as already approved.
