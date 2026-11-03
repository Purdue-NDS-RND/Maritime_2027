# Milestone 1: camera-free slalom through the web GCS

Status: complete for the selected simulator acceptance on 2026-10-28. Three
consecutive browser-started full slaloms passed at a commanded 2.0 m/s target
with frozen scene, map, mission, profile and settings. Minimum independent
whole-hull clearance was 1.26091 m; all passage/side/stern, contact and finish
checks passed. GCS backend loss/reconnect also passed during the third run.
This establishes simulator acceptance; physical-boat performance is unverified.
See [recorded results](#recorded-simulator-results) below and
[boat execution](boat_execution.md) for interfaces and fault behavior.

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
- Development transport is loopback HTTP from GCS to the boat (8091), with
  ROS 2 retained inside the boat app. The GCS serves React/Leaflet and FastAPI
  together on desktop localhost:8080. A subsequent live-position update adds
  passive MAVLink map telemetry, independently of mission HTTP, with UDP/serial
  configuration and an oriented boat marker. See [live position](../gcs/README.md#live-map-telemetry).
  Physical radio operation and mission networking remain unverified.

## End-to-end flow

1. Start the simulator with `WATER=calm SCENARIO=slalom make -C simulation run`.
   Record the resolved scene and run identity for later evaluation.
2. A simulation-only export tool obtains the resolved buoy positions and types
   and produces an object map with GPS coordinates for GCS import. Use the
   resolved scene rather than assuming an arbitrary source file matches the
   running world. The current scene renderer already records local model
   positions in a generated manifest; export and multi-position geographic alignment
   are implemented and have live evidence in the recorded results below.
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
   before execution. Approval freezes the complete inputs; Upload and Start are
   separate operator actions. Each returns a boat operation ID whose confirmed
   result is distinct from transmission receipt.
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
- [x] Export the resolved simulator object map and verify its GPS alignment.
  Four live positions/two headings passed; maximum error 0.015 m.
- [x] Build the minimal GCS map view and manual waypoint editor, configurable
  speed/clearance, and route clearance checks.
- [x] Connect GCS mission approval/upload/start and progress reporting through
  the boat application.
- [x] Demonstrate simple gate passage before attempting the complete slalom.
  A live browser mission passed at 0.5 m/s with independent whole-hull evaluation;
  backend loss did not interrupt execution and reconnect did not restart it.
- [x] Evaluate the full slalom, repeat the run, and record measured results.
  Three consecutive frozen 2.0 m/s target passes are recorded below.

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

The approved acceptance settings are:

| Criterion | Required value |
| --- | --- |
| Mission speed target | 2.0 m/s |
| Minimum complete-footprint to buoy-collision clearance | 0.25 m |
| Coordinate conversion/alignment error against truth | At most 0.10 m |
| Finish position error from selected centre | At most 1.0 m |
| Finish speed and settling | At most 0.2 m/s continuously for 5 s |
| Full-course execution timeout | 300 s |
| Repeatability | Three consecutive full passes with frozen inputs/settings |

Develop at 0.5, 1.0 and 1.5 m/s before attempting 2.0 m/s. Lower-speed
success does not complete this milestone. Report actual speed, elapsed course
time and tracking error separately from the commanded speed. Record the
conservative collision-mesh footprint, settings and empirical positioning/
tracking allowance (including an additional 0.10 m reserve).
Measure actual passage independently of ArduPilot waypoint-reached events;
waypoint acceptance or a healthy container alone does not prove completion.

Keep the input map, approved mission, configuration, reported progress and
evaluation results together under ignored `simulation/logs/`. Document exact
reproduction settings, outcomes and limitations in this document; keep raw
per-run evidence in the ignored logs rather than creating task handoffs.

## Deferred work and limits

No drone application, detection model, geolocation from images, marker landing,
automatic route generation, Evade detector strategy, stitched aerial imagery,
or other competition task mechanisms are required here.

This uses a perfect simulator map and does not establish camera-free feasibility
on the real boat. Subsequent experiments introduce survey/GPS errors and buoy
movement, evaluate clearance limits, and compare with physical route following.
The retained BlueBoat dynamics are not calibrated competition-boat dynamics.

## Implementation and reproduction

### Current mission workflow

Boat/GCS mission authorization no longer requires navigation profiles, geometry
hashes, calibrated speed/turn envelopes or active gain readback. GCS speed and
total point-to-buoy-surface clearance buffer are operator settings. No hidden hull
or tracking allowance is added. ArduPilot tuning is separate simulator/vehicle
configuration; simulation experiment tools live under `simulation/scripts/`.
Fresh telemetry, explicit approval, upload/readback, speed acknowledgement before
arming, STOP/takeover and finish checks remain. Existing profile-based drafts
retain their route with a backup, but require a new total buffer and reapproval.

The results below predate this simplification and remain historical evidence for
the recorded frozen settings. They do not validate arbitrary speeds/buffers or
establish a new full-course acceptance for the changed application workflow.
See the [GCS guide](../gcs/README.md) for current operation.

Simplification validation: 23 boat, 27 GCS and 4 relocated simulation-profile
tests passed; boat/GCS images and React built; simulator static/Compose/SDF checks
passed. Live Chrome confirmed the profile selector was removed and the retained
seven-waypoint draft requires a new total buffer and reapproval. Rebuilt boat/GCS
services started; the simulator was stopped, so no new motion/slalom run was
performed. Runtime build/test logs are `simulation/logs/point-buffer-*.log`.

The shared simulator defaults now include the previously measured controller
settings in `simulation/config/blueboat.parm`, used by every world/scenario.
Pivot turns are enabled at 30 degrees with a 60 degrees/s limit. This changes the
simulator's starting configuration; it does not add any boat/GCS tuning dependency
or establish a new full-course run. See the simulator guide for EEPROM precedence.

Shared-default verification: cached rebuild and simulator static/Compose/SDF
checks passed. All 12 configured parameters matched independent readback after
restart in run `20261028T235904-95001`, disarmed at 0.0 m/s. Existing EEPROM was
backed up before startup and the eight tuning settings explicitly saved/read
back; evidence is under `simulation/logs/slalom-defaults-20261028T235627Z/`.
No mission or new movement test was run. The verification simulator was stopped
and the previously running boat service restored. Normal source snapshot creation
also now handles tracked files deleted in an uncommitted working tree.

### Historical acceptance setup

The boat owns serialized HTTP/ROS mission commands and a single MAVLink worker;
see [boat execution](boat_execution.md). The [GCS guide](../gcs/README.md)
documents manual editing, immutable approval, separate Upload/Start and passive
map telemetry. Measured profiles and their source evidence are local files under
`simulation/logs/profiles/`. The maintained simulator-only tuning helper is
`simulation/scripts/profile_settings.py`; a fresh checkout still needs its own
measured settings/evidence to reproduce a characterized controller configuration.

Simulator runs retain immutable resolved worlds, models/meshes, source and image
identities, baseline parameters and per-step physics/contact streams. The map
exporter rejects unsupported transforms/geometry, modified snapshots, mismatched
active images and displaced/missing buoys. Stable physical scene identity is
separate from the per-run snapshot hash. Object marker faces are distinct from
buoy centres.

World X is east, Y is north; heading is 90 degrees minus world yaw. The pinned
bridge reports the IMU-link pose (no mounting translation in this model), not
the inertial centre of mass. Geographic conversion uses the pinned ArduPilot
mean-latitude longitude scaling. Four live positions, three non-collinear
locations and two headings established at most 0.01495 m conversion error;
run `20261028T014500-383985` subsequently measured 0.01472 m.

The independent evaluator projects a conservative collision prism under full
roll/pitch/yaw, including propulsor bounds. Missing pose, height, physics steps
or contact evidence is inconclusive. Buoys are conservative infinite vertical
cylinders. Empty contact arrays count only with a qualified recorder: deliberate
hull-shell contact was recorded outside mission windows. The planned-path
validator uses a full-attitude enclosing sphere of radius 0.76735 m.

To reproduce the accepted profile:

1. Build the current canonical images using each app's `make build`; simulator
   `make build-cached` is an alternative with verified source pins and an existing
   base image, not proof of a clean dependency build.
2. Start a fresh simulator from `simulation/` with
   `MAVLINK_STREAMRATE=20 CAMERAS=off WATER=calm SCENARIO=slalom WIPE_PARAMS=1 make run`.
   Plain `make run` defaults to 4 Hz and does not stage measured gains.
3. With the boat service stopped and disarmed, use simulation-only
   `profile_settings.py apply <profile> --state <new-state-file> --baseline-position-hz 20`
   from the boat image with `simulation/` mounted at `/simulation`. Save original
   parameters before mutation. Use `sim-slalom-2_0-p16-20hz-v2` for the
   recorded tuning configuration. The simulator-only helper verifies gains;
   current boat/GCS operation does not check them.
4. Verify the active scene/image/buoy coordinates and fresh stationary alignment.
   Keep the original multi-position/two-heading conversion proof with the map.
   Import the manually prepared workspace, then explicitly Validate, Approve,
   Upload and Start in the browser. Record operation confirmation separately
   from HTTP receipt. Use fresh session/output identities and preserve journals.
5. Record raw observations and independent evaluation; after completion confirm
   disarm, stop the boat service, and use `profile_settings.py restore <profile> --state <saved-state-file>`
   with the same profile and saved state. Independently verify every original parameter's readback.

Tool ownership and precautions:

- `alignment_probe.py` runs inside the simulator while disarmed with the boat
  stopped. It moves/restores the model; never run during a mission. Use a fresh
  simulator after pose experiments to avoid estimator-convergence artifacts.
  `alignment_report.py` assesses saved SIMSTATE/physics samples.
- Host `export_active.py` needs the active run's alignment report. `make_course.py`
  defines evaluation roles, not waypoints. `evaluate_run.py` needs explicit
  mission start/end simulation times. `plot_evidence.py` needs host Matplotlib.
- `calibrate.py` uses exclusive UDP 14551 ownership with the boat app stopped.
  Use new mission/output identities and active truth recordings, never archived
  run paths. It saves/restores supported waypoint/steering/speed overrides;
  restoration failures block subsequent experiments. Failed calibration is
  rejected by default; `--diagnostic` keeps measurements with
  `calibration_usable: false`. Pre-arm failures must not be bypassed.

## Default competition scene extension

The default simulator course is now `competition`; explicitly select
`SCENARIO=slalom` to reproduce the historical acceptance layout below.
The larger scene adds all reference stations and fixed physical props, exports
version 2 obstacle maps and supports manually authored custom GCS routes.
The GCS validates segments and finish areas against every collision footprint
using the operator's total buffer. Geometry estimates are recorded in
`simulation/scenarios/competition.json` and the scenario guide.

This extension does not transfer the old slalom acceptance to the new course.
Full-course navigation, Identify contact, deployment, detection avoidance, launch,
recovery, docking actions, Receive communication and scoring remain unverified
or deferred. Physical boat/radio performance remains unverified.

Verification on 2026-10-28 (UTC evidence dated 2026-10-29): simulator static,
Compose and Gazebo SDF checks passed, along with 72 simulator container tests
(one automatic-NVIDIA-host test skipped without GPU device passthrough) and
28 GCS container tests. React and GCS builds passed; simulator rebuilds used the
verified pinned dependency cache rather than a clean network dependency build.
Tests cover feet conversion, station/color completeness, deterministic output,
legacy rendering/imports, invalid footprints, version 2 persistence, immutable
export identity and segment/finish rejection at all 29 physical objects.

Runtime `20261029T004128-174602` passed the normal movement/HOLD/RTL/disarm
smoke. A separate browser-approved custom route to world (-5, 0), commanded at
0.5 m/s with a 1.8 m total buffer, uploaded/read back, started and completed with
finish settling and HOLD confirmed; explicit disarm then succeeded. The saved
map/draft survived reload. Full-course GCS orientation, colors, station labels,
Zebra pattern, docks and deployment overlay were visually checked against the
reference. Native Gazebo-window visual comparison was unavailable through the
session's UI tools; its live scene description, complete fixed-object roster,
poses and SDF were checked instead. This is short-route integration evidence,
not independent whole-hull/full-course or competition-task acceptance.

Fresh run `20261029T004835-203334` retained the same physical scene identity.
Its first physics pose was within 0.000001 m of (0, 0), facing west; the spawn
probe measured SITL heading 269.9999975 degrees. Multi-position/two-heading
alignment passed at 0.01585 m maximum position error and below 0.000001 rad
heading error. Active-scene exports included all 23 buoys and six props. Final committed-source
run `20261029T005141-211122` also passed alignment at 0.01572 m, retaining the
same physical scene and exactly matching exported objects, stations and start pose.
Raw evidence is ignored under `simulation/logs/competition-*`, including
`competition-custom-result.json`, alignment reports, live scene description,
container/static/build logs and `competition-gcs-overview.png`; immutable scenes
and per-step truth remain under their run directories. The existing `output/`
and prior GCS/boat data were preserved. Test runtimes were stopped after capture.

## Recorded simulator results

These are historical measurements from 2026-10-28, not a fresh validation run.
Raw files are ignored local artifacts under `simulation/logs/`; another checkout
must generate its own evidence. Current runtime tags are `maritime-sim:latest`,
`maritime-boat:latest` and `maritime-gcs:latest`; historical image identities remain
in each evidence inventory and do not imply those old tags are still installed.

### Development and qualification

Boat-only entrance-gate evaluation passed at 0.5 m/s (1.208 m minimum clearance).
The live browser gate run `20261028T021354-409912` exercised import, drag/exact
edits, save/reload, unsafe-route rejection, approval invalidation, separate
Upload/Start, progress, backend loss/reconnect and explicit disarm. Its
full-attitude re-evaluation (`gcs-gate-prism-*`) passed at 1.06113 m clearance.

Early turn profiles did not fit the fixed gates or failed finish settling;
none authorized a slalom. Failed trials and rejected routes remain under
`simulation/logs/milestone1-followup/` (`turn-both-*`, `open-turn-*`,
`manual-slalom-flat-validation.json`). The flat route missed the conservative
margin by 0.239 m. DataFlash `simulation/logs/state/logs/00000110.BIN` and the
matching MAVProxy log confirmed steering lag/oscillation rather than a map-frame
error. Bounded steering feedforward tuning to 0.8 enabled measured qualification
without changing protected dynamics or default parameters.

The selected 2.0 m/s profile uses steering FF=0.8, speed P=1.6 / I=0.05,
WP_RADIUS=0.2, PIVOT_ANGLE=30, PIVOT_RATE=60, ACCEL=0.5 and JERK=1.
The 2.0 m/s P=1.2 probe's 0.65788 m allowance exceeded the approximately
0.64265 m gate budget and was rejected. P=1.6 measured 0.52157 m in the probe.
The first full-course observation then required increasing the retained allowance
to **0.640 m**, with the separate **0.10 m reserve and 0.25 m clearance** unchanged.
That earlier pass was excluded from the final sequence after the profile change
(`series1-reclassified.json`); measured error was never reduced to admit a route.

| Development stage | Run | Min hull clearance | Elapsed | Actual mean / peak |
| --- | --- | --- | --- | --- |
| Boat-only 0.5 m/s | `20261028T041811-626990` | 1.25485 m | 134.532 s | 0.39805 / 0.68655 m/s |
| Browser 1.0 m/s | `20261028T044511-677325` | 1.24567 m | 86.522 s | 0.62581 / 1.05716 m/s |
| Browser 1.5 m/s | `20261028T045817-704630` | 1.22079 m | 76.459 s | 0.72044 / 1.55506 m/s |

Each passed all six passage/side/stern checks, contacts, clearance and independent
finish settling. Files use `slalom-0.5*`, `gcs-1.0*` and `gcs-1.5*` under the
follow-up directory. A matched DataFlash POS/SIM diagnostic found 26,329 identical
geographic pairs: this simulator uses `AHRS_EKF_TYPE=10` (native state).
Reported-position/latest-physics separations include transport age and do not
measure real GPS error. Existing allowances were retained.

### Final simulator acceptance: three consecutive passes

The final frozen approval is `745d25d7-c924-41f7-bbd1-2399bffb05fe`, revision
`f6bdffc1214d2f2c6c0ea574c1fd720b44e46604e8e2480674562b14d62bace3`.
All three runs used this same manually prepared mission, imported map, physical
scene, collision geometry, measured profile and controller/telemetry settings.
No edits or reapproval occurred between the three runs. The 0.640 m empirical
allowance, separate 0.10 m reserve and required 0.25 m clearance were frozen.

| Repeat | Simulator run | Min hull clearance | Elapsed | Actual mean / peak | Max finish error | Max observed lateral / position separation |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `20261028T051356-744247` | 1.26219 m | 74.350 s | 0.73236 / 1.91687 m/s | 0.58532 m | 0.44493 / 0.18986 m |
| 2 | `20261028T051705-753649` | 1.26221 m | 74.337 s | 0.73251 / 1.91685 m/s | 0.58654 m | 0.44666 / 0.16844 m |
| 3 | `20261028T052009-763074` | 1.26091 m | 74.462 s | 0.73127 / 1.91663 m/s | 0.58727 m | 0.44446 / 0.13766 m |

The commanded target was 2.0 m/s; actual mean speed includes deliberate braking,
pivot turns and final stopping. The actual peak was about 1.917 m/s on this
short-leg route. This is target-speed acceptance, not a claim of continuous
2.0 m/s travel. All six passage-order/side/stern checks passed without contacts.
The evaluator processed 74,351 / 74,338 / 74,463 consecutive physics samples,
respectively, including full-attitude conservative collision-prism clearance.
All three independently settled within 1 m and at or below 0.2 m/s for 5 s;
window peak speeds were 0.19975 / 0.19981 / 0.19951 m/s. No evidence was missing.

The lateral and position-separation columns use the recorded 10 Hz HTTP/status
and physics observations; they are separate from every-step clearance checks.
Each run's maximum lateral error plus maximum position separation remained
within the frozen 0.640 m bound. These separations include transport age and do
not establish real GPS error. The initial observed positions differed by at
most 0.0000101 m; initial yaw spread was below 3e-10 rad. Each fresh run's
stationary alignment error was at most 0.00140 m, with the unchanged inherited
full multi-position/two-heading conversion proof. There were no failed full
missions between these three final passes.

During repeat three, the GCS backend container was stopped after waypoint 1
was reached. The live browser correctly showed stale/unavailable telemetry and
disabled Upload/Start. The boat application continued through the remaining
course and independently completed in HOLD while the backend remained stopped.
Restarting the same GCS container reconnected to the completed mission without
restarting it. Browser Disarm then succeeded. The frozen workspace was checked
unchanged after reconnection. This is local process/backend-loss acceptance,
not physical radio-link or RC hardware acceptance.

All three final sessions have confirmed explicit disarm and complete original
parameter restoration/readback. Persistent journals are retained; temporary
runtimes were stopped after evidence capture. Later runtime maintenance removed
obsolete containers. The default parameter file, dynamics, source pins and
MAVLink ports remain unchanged. No boat camera or simulator-truth subscription
was introduced. The boat-only path remains available.

Primary evidence under `simulation/logs/milestone1-followup/`:

- `final-2.0-series2-summary.json`: aggregate results, observed errors, initial
  spread and rollback verification; `three_consecutive_passes: true`.
- `final-2.0-series2-frozen-workspace.json` and `*-input-manifest.json`:
  approved map/mission/profile plus image identities and input hashes.
- `final-2.0-series2-repeatN-observation.jsonl`, `.evaluation.json`,
  `.evaluation.course.json`, `-session.json`, `-settings.json`, `-disarm.json`:
  raw observations, independent checks, journal/run identity and rollback.
- `final-2.0-series2-repeat3-gcs-loss.json`: outage, completion and reconnection.
- `final-2.0-browser-disarmed.png`: live browser after confirmed final disarm.
- Each simulator run directory retains its immutable resolved scene, per-step
  physics/contact stream, frozen-map check and alignment observation.

### Fresh canonical-runtime integration check

A subsequent single integration pass used normal launcher/Compose paths and
canonical image tags in run `20261028T175441-1211274`. Evidence is under
`simulation/logs/canonical-runtime/`. It is separate from three-pass acceptance.
The scene and buoy centres matched the frozen map exactly; fresh stationary
alignment passed, retaining the original multi-position proof. Profile staging,
20 Hz telemetry and geometry identity were explicit as described above.
The seven-waypoint workspace was imported without approval; browser Validate,
Approve, Upload and Start were separate confirmed actions. Approval was
`eff52d5f-39ca-4c99-9bcd-f835396ab011`, with the same revision as the final series.
The oriented map marker and changing heading were observed in Chrome.

Independent evaluation passed with 73,621 contiguous physics samples:
1.26141 m minimum clearance, 73.620 s, 0.73935 / 1.91754 m/s mean/peak speed,
0.56826 m maximum finish error and 0.19969 m/s peak speed during 5 s settling.
The auxiliary HTTP observer exited before HTTP readiness, so this run has no
complete HTTP tracking-error observation. `evaluation-driver.py` derives the
start one second before first 1 cm motion from the alignment-verified stationary
pose; `evaluation-extended-hold.json` also passes with a longer stopped tail.
Contact qualification reuses deliberate-contact proof for the same physical
scene. HOLD, browser disarm and all restored parameter readbacks were confirmed;
the prior GCS workspace was restored. A separate plain launch
`20261028T175956-1230599` confirmed calm/slalom/cameras off at 4 Hz.

Historical verification passed simulator static checks (including 13 menu,
15 evaluator and 6 calibration qualification tests), 26 boat and 25 GCS tests,
normal boat/GCS and React builds, and a simulator cached rebuild after pin checks.
Source/image inventories are `integration-containers.json`, `candidates.json`
and `canonical-images.json`. A fresh network dependency build was not tested.
Earlier run `20261028T014500-383985` passed movement/HOLD/RTL/disarm smoke,
3,499 buoy-facing checks and an isolated real-physics recorder/contact test.

Browser checks also covered same-scene import resets, invalid passage JSON
revoking/blocking approval, and external tile-image failure while draft editing
remained usable (`tiles-blocked-browser.png` in the follow-up directory).
This is resource-load failure, not physical internet-outage acceptance.

Obsolete Docker images/containers were later removed without pruning volumes or
shared build cache; bind-mounted evidence and journals were retained. Cleanup
inventory, exact removed tags and output remain in `canonical-runtime/`
(`removed-image-tags.json`, `image-removal.log`); the legacy container export is
`legacy-gcs-container.tar.gz`. Measured net host space recovered was 7.98 GB,
subject to unrelated host activity. Historical tags/containers are not runtime
dependencies. Physical boat/radio behavior remains unverified.

## GPS assisted planner extension

This subsequent scope adds separate gate/slalom/channel planning, independent
retries and persistent reviewed course roles. It does not change the historical
Milestone 1 acceptance above. Live GPS JSON/CSV imports preserve original values
and corrections separately, use explicit editable size assumptions and never
inherit simulator verification. See the GCS guide for setup and operations.

A* uses required clearance as a hard constraint and preferred clearance as a
reported, locally yielding preference. Each task has confirmed direction,
entry/exit, finish, bounds and ordered roles or channel containment; searches
refine 0.25/0.10/0.05 m and distinguish blocked gate proofs from exhaustion.
Simplified GPS drafts receive full segment/course/finish validation. Manual and
boat-only route interfaces remain available. Map/setup/settings changes and task
switching revoke approval. Upload/start retain actual-position checks.

Automated planner, workspace and API checks and simulator evidence are recorded
under ignored `simulation/logs/gps-planner/`. Browser acceptance is currently
blocked: the computer-use service reports no available browsers/apps. This must
be completed before claiming the requested full setup/edit/retry workflow.
Physical boat/radio, detection avoidance and controller tracking at arbitrary
settings remain unqualified. Final measured task results are recorded below.

### GPS planner simulator results (2026-10-29)

Base run `20261029T182329-8355` executed three consecutive separate missions for
each task using generated drafts from `gps-only-base.json` (only GPS points,
anonymous point IDs and physical radii; no colors, station/start metadata,
alignment or simulator identity). Missions alternate reviewed travel directions
and regenerate from actual stopped starts, with separate approval/upload/start
and confirmed disarm after each. These are independently regenerated missions,
not three repetitions of one frozen approval. Map and task drafts remain saved.
Channel retries start at different safe ends without replaying earlier tasks.

| Task | Independent outcomes | Minimum hull clearance per pass (m) |
| --- | --- | --- |
| Gate | 3 passed | 1.24376 / 1.04769 / 1.01178 |
| Slalom | 3 passed | 0.93195 / 0.65918 / 0.80005 |
| Channel | 3 passed | 0.80380 / 2.04582 / 2.33873 |

All passed contiguous physics-step evidence, ordered/side/stern gate/slalom
checks, full-attitude collision-prism clearance, no contacts, containment inside
operator-selected planning/channel polygons, and independent finish settling
within 1 m at <=0.2 m/s for 5 s. The channel fixture is an operator-bounded polygon
in the slalom scene, not qualification of the competition Evade station or detector
coverage. Contact-recorder qualification reuses the independently verified
same-scene deliberate hull-contact proof; the source/image/scene remain recorded.

Test settings explicitly select 0.5 m/s, 1.5 m required and preferred planned
point buffers and a 0.25 m independent hull-clearance threshold. Defaults remain
0.5 m/s and 1.8 m required; preferred initializes equal to required. The default
1.8 m cannot fit the 3.52 m gate surface opening and is correctly rejected; it
was not reduced by the planner. An initial gate finish disk beside the next
slalom buoy was rejected before upload and moved to clear space without changing
buffers. Actual tracking consumes the chosen allowance; these runs do not prove
that physical or higher-speed error stays inside it. Preferred shortfall and
detector constraints/preferences have automated coverage, not detector runtime
qualification. No controller parameters, dynamics or firmware pins changed.

Verification: 41 GCS/API/planner/workspace/telemetry tests and 16 independent
evaluator tests pass; React and production image `maritime-gcs:gps-planner` build,
Python compilation and simulator static/configuration checks pass. Saved base
routes also pass final-source revalidation. Browser setup/edit/retry acceptance
remains blocked by the unavailable browser surface and is not claimed.

Additional run `20261029T184525-41988` used a 0.5 rad rotated slalom with
alternating 0.05 m lateral perturbations, freshly exported and stripped to GPS
points. The production GCS image generated ten waypoints; all six actual
passages, full-hull clearance, contacts and stopped finish checks passed over
124,438 contiguous physics samples. Minimum hull clearance was **0.91670 m**.
The active recorder was qualified by deliberate disarmed contact after the
mission window, then the original pose was restored. A first normal start was
rejected during gyro/EKF initialization; retry after initialization used normal
pre-arm checks. No force-arm or parameter bypass occurred. Fixture coordinates
use the renderer's six-decimal precision to satisfy strict manifest/SDF equality.
The tracked scene was restored byte-for-byte; temporary runtimes are stopped,
and the original stopped main-checkout simulator container name is restored.

Raw evidence includes task `*-generated.json`, `*-approval.json`,
`*-observation.jsonl`, `*-session.json`, `*-evaluation.json`, operation results,
contact proofs, source/image inventories, build/test logs and both immutable
run directories. `final-source-revalidation.json` checks all ten saved generated
routes. Existing `output/` and the main checkout remain untouched. Full browser
setup/correction/retry acceptance remains outstanding; backend/API tests and
HTTP-driven simulator runs do not substitute for that browser check.

### Full competition map and guided GCS redesign (2026-10-29)

The full competition scene is now the primary development/operator test target;
the eight-buoy map remains regression coverage. The normal GCS uses three panels:
Map → Task setup → Route review. Map inspection is the default click mode,
drawing/editing tools are explicit and cancellable, and advanced controls are
collapsed. The bundled full GPS practice map includes all 23 buoys and six props,
without simulator run/start/alignment requirements or a simulator-verified label.
Normal workspace replacement archives the previous map and drafts first.

Full-map failures were traced to mixed-station suggestions, northbound defaults,
return markers misidentified as slalom turns, and channel/task constraints applied
before entry. Task suggestions now use the available imported task/object labels;
Dodge is westbound and Evade southbound. They remain unconfirmed. Complete
approaches enforce physical clearance and planning bounds; task passage planes
and channel containment activate at the finite entry. Final validation checks
the complete generated route. Precomputed metric obstacle geometry, conservative
bounds and a next-opening heuristic reduce full-map planning work without dropping
obstacles or reducing required clearance. The default 1.8 m gate rejection is
shown as a 3.52 m opening versus 3.60 m needed; no allowance is silently changed.

Run `20261029T225445-98188` executed **one separate generated mission per task**
on the actual full competition scene, through normal GCS/boat APIs, at an
explicitly selected 0.5 m/s and 1.5 m required/preferred test buffer. All three
uploaded/read back, completed in HOLD and explicitly disarmed. Slalom started
from the gate finish, including its return approach to entry; channel started
from the slalom finish without rebuilding the map or replaying prior tasks.

| Task | Independent result | Minimum whole-hull clearance, including props |
| --- | --- | --- |
| Gate | passed | 1.29242 m |
| Slalom / Dodge | passed | 0.83310 m |
| Channel / Evade | passed | 2.75838 m |

Independent evaluation covers contiguous physics, full-attitude collision prisms,
all circle/polygon obstacles, approach clearance, active passage order/sides/stern,
channel containment, contacts and finish settling within 1 m at <=0.2 m/s for 5 s.
The active contact recorder was qualified after mission windows using disarmed
deliberate contact and pose restoration. The independent hull threshold was
0.25 m. No tuning, dynamics, firmware pins, direct ports or boat interface changed.
This is one-pass integration per full-map task, not three-pass full-map
qualification, physical/radio acceptance or detector-avoidance proof.

Verification: all 49 backend/planner/workspace/telemetry/API tests, 17 evaluator
tests, four frontend workflow assertions and server rendering of all three
panels pass. Production/React builds, Python compilation and simulator static
checks pass. Live browser interaction/visual acceptance remains unavailable
because the computer-use service reports no browsers/apps; server-rendered checks
are not a substitute. Raw inputs, approvals, operations, physics evaluation,
contact proof and build/test logs are under ignored `simulation/logs/gcs-redesign/`.
Normal operator settings were restored with the full competition map and no
approval. The GCS remains available for review; simulator/boat tests are stopped.

### Channel planning recovery (2026-11-01)

Live Chrome inspection found an edited channel entry beside the right boundary:
its entire crossing window violated the selected 2 m channel inset. Generation
searched for minutes without explaining the conflicting setup. Convex-channel
entry feasibility now rejects that conflict before search; other searches share
a 60-second time budget and return explicit exhaustion without relaxing buffers.
The production GCS was rebuilt/restarted with saved drafts retained. Chrome
confirmed immediate actionable rejection and an enabled Generate button for the
same failing input. All 51 containerized GCS tests pass, including full-course
generation, entry rejection and deadline coverage. The test image now includes
the full-map example fixture. This is planner/UI recovery evidence, not a new
boat execution or physical acceptance run. Raw evidence is retained under
`simulation/logs/channel-planner-fix/`.

### Manual waypoint movement (2026-11-01)

Manual move is a visible task option with a separate saved waypoint queue,
fresh-start capture, editable speed/buffer and last-waypoint finish. Gate,
slalom and channel drafts survive switching. Existing validation, approval,
upload and explicit Go/start remain separate; no boat interface changed.
Chrome checks on the full competition map queued two waypoints, validated the
direct route and verified that Upload/Go stayed disabled before approval.
The test queue was cleared afterward, leaving an empty saved manual draft for
the operator. No movement was commanded in this UI check. All 52 containerized
backend tests, frontend workflow/render checks and production builds pass.
Evidence is under `simulation/logs/channel-planner-fix/manual-*`. Actual motion
reuses the existing supplied-route executor and was not requalified in this check.

### Boat controls visibility (2026-11-01)

A persistent Boat controls panel shows armed state, mode, speed and GPS fix,
with Hold / Stop and Disarm available across planning steps. Disarm is enabled
only with fresh armed status in Hold at reported speed ≤ 0.20 m/s. Upload is
disabled while armed or in Auto, with recovery guidance. Arming remains part of
the existing verified mission Start/Go path. Historical command results are
labeled separately from live status. Frontend render checks cover offline,
moving, wrong-mode, settled and disarmed states plus armed-upload blocking;
frontend checks and production build pass. Chrome verified live armed/Hold/
zero-speed presentation and availability of Disarm. No vehicle command was
sent as part of this UI check; the approved route was retained. Evidence is
under `simulation/logs/channel-planner-fix/controls-*`.

### Buffer preview (2026-11-01)

A visible Show buffers toggle works before confirmation/validation and updates
from current draft settings. It covers circle/polygon obstacles, convex boundary
insets, start clearance and finish allowance, plus larger preferred buffers.
Unsupported concave boundary previews and collapsed insets are identified. Entry
is drawn as its finite crossing window; setup copy distinguishes it from saved S
and live boat position. Geometry/frontend render checks and production build pass.
Chrome verified the toggle on the full competition map in Map review before
validation, then Channel setup with the same preview enabled. Saved geometry
and settings were retained; no vehicle commands were sent. Screenshot/build
evidence is under `simulation/logs/channel-planner-fix/buffers-*`. This is a
visual debugging aid, not new route or vehicle acceptance.

### General-course planning (2026-11-01)

Version 2 task geometry separates reviewed setup from attempt start/scope.
Normal operation uses Live boat and Full task; Generate captures position and
heartbeat no older than three seconds. Remaining section suggestions require
operator confirmation and label the result as partial, without credit for
excluded passages. Local finite crossings replace a mandatory manual Entry.
Channels follow all chain points, reject invalid section connections and support
safe inside starts. Approval freezes the selected progress and route; actual
Upload/Start positions cannot silently change that selection. Workspace migration
backs up existing state and preserves maps, routes and manual queues for review.

Full-map Chrome checks exercised all three task generations, gate assignment
correction, buffers before confirmation, the unchanged blocked-opening warning,
ambiguous and explicitly confirmed Remaining section selection, partial labels,
slalom validation/approval, and armed-upload blocking. The checks used an isolated
workspace on port 8082; the operator's normal workspace was not replaced.
Automated verification passed 68 GCS tests, frontend workflow/render/buffer checks,
19 independent evaluator tests, production builds and simulator static checks.
Raw inputs, build/test logs and runtime evidence are under ignored
`simulation/logs/general-course/`. Independent simulator movement qualification is recorded below; HTTP completion
alone was not used as acceptance.
Physical boat/radio performance, detector avoidance, drone mapping, unexpected
obstacle avoidance and continuous replanning remain unverified or deferred.


One separate mission per task ran on each physical Gazebo fixture in run
`20261101T182911-12690`, using isolated GCS workspaces and disarmed position
resets. Target speed was **0.5 m/s**, required/preferred point buffers **1.5 m**,
and independent minimum whole-hull clearance **0.25 m**. These test settings do
not replace the operator's saved 2 m/s / 2 m settings or the application defaults.
Actual speed includes pivots and stopped settling; this is not continuous-speed
qualification. The rotated fixture turns all objects/footprints by **0.47 rad**.
The bent fixture also staggers Dodge turns/the final gate and shifts both middle
channel-chain points by 3 m, retaining all reviewed boundary vertices.

| Fixture | Gate min hull clearance | Slalom min hull clearance | Channel min hull clearance |
| --- | ---: | ---: | ---: |
| Baseline | 1.286408 m | 1.032169 m | 5.243459 m |
| Rotated | 1.260925 m | 0.952706 m | 5.191515 m |
| Bent | 1.273973 m | 0.974589 m | 2.906822 m |

All nine independently passed contiguous every-step physics evidence, finite
local passage order/passing sides/stern clearance, whole-hull clearance against
all circular and polygon objects, permitted-water containment, no contacts, and
finish settling within 1 m at ≤0.2 m/s for 5 s. This is **one pass per task and
fixture**, rather than three repeats of a frozen approval. Dynamic Gazebo pose
fixtures were checked against frozen GPS maps at every recorded physics step;
no simulator truth was used by boat steering or route generation.

Two additional baseline-channel attempts started safely inside: Full task and
an explicitly confirmed Remaining section. Both passed immediate containment,
clearance, no-contact and stopped-finish evaluation, with minimum hull clearance
**5.150066 m** and **5.392722 m**, respectively. The partial attempt excluded
prior sections without changing the full setup or claiming competition completion.
Moving the disarmed boat outside the approved full attempt's progress region
caused Upload to return HTTP 409; the approval remained unchanged.
Restoring a safe actual position allowed that same approved route to execute.

The active contact recorder was qualified by deliberate disarmed contact after
mission windows. One channel start was rejected by normal ArduPilot pre-arm
checks after a test heading teleport (`DCM Yaw inconsistent 81 deg`). Subsequent
resets preserved heading; no force-arm or parameter bypass occurred. A rotated
channel setup rejection exposed near-duplicate normalized fractions after GPS
round trips; numerical coalescing and a full-map rotation regression fixed it.
Transient Gazebo reset-service timeouts received bounded, idempotent retries.
Rejected inputs/operations remain archived separately from successful missions.

All **11** saved GPS routes pass final-source segment/course/finish revalidation.
Original static object poses were restored exactly; final boat position was
within **0.033 m** of its original position, disarmed in HOLD at reported zero
speed. No tuning, dynamics, firmware pins, camera assets, direct MAVLink ports
or boat mission envelope changed. The normal GCS was updated locally; migration
created a byte-exact workspace backup and preserved the reviewed/original maps,
all saved routes, settings and manual queue while requiring renewed planner review.
Chrome confirmed Live boat / Full task, unchanged saved 2 m/s / 2 m settings,
live boat marker, buffers before review, and disabled generation until confirmation.

Primary evidence: `qualification-summary.json`, `*-generated.json`,
`*-approval.json`, `*-observation.jsonl`, `*-physics.jsonl.gz`, `*-evaluation.json`,
`contact-proof.json`, `final-source-revalidation.json`,
`operator-migration-verification.json`, `frozen-scene-verification.json` and
`restoration-verification.json` under
`simulation/logs/general-course/`. Physical boat/radio operation, arbitrary
speed/error allowances, detector avoidance and continuous replanning remain
unqualified. No Git commit or push was performed.

### Shared course settings and tower zones (2026-11-03)

The GCS now uses Map → Configure → Task setup → Route review. Shared speed,
required/preferred obstacle clearance and tower hard/soft surface distances
persist across tasks, with explicit task and individual-tower overrides. The
configuration map previews the zones immediately. Invalid distances prevent
saving. Settings changes revoke approval and require generation/review; the
boat mission envelope and controller remain unchanged.

New browser sessions hide saved course paths and disable Route review until
explicit task generation. Saved maps, assignments, routes and manual queues are
retained; adding settings creates a byte-exact workspace backup. Manual moves
remain explicitly selectable. Tower hard zones are checked on every segment,
actual-position connection and finish disk; soft-zone traversal is reported.
Cost-preserving simplification retains avoidance detours. Bounded weighted A*
uses the existing shared 60-second deadline and distinguishes search exhaustion
from a proven hard blockage; fallback effort is identified during route review.

Full-map browser verification covers shared and individual tower controls,
invalid-distance blocking, persistence after a preview-container restart,
clicking the purple tower, explicit gate generation and hiding that generated
route again after reload. The preview uses a copied workspace on port 8082 and
sends no vehicle commands. Configured gate/slalom/channel routes on the full
competition map pass final segment/course/finish validation at 0.5 m/s, 1.5 m
ordinary required/preferred buffers and tower 1.5 m hard / 10 m soft distances.
A separate channel check with a 30 m soft distance also generates and validates,
using fallback search effort, without reducing hard clearance.

Automated verification passes 76 backend tests, frontend workflow/settings/
render checks, production builds and simulator static checks. The open-browser
backend-restart check also hides a generated route and disables Route review.
Normal-workspace migration preserves every existing field and has a byte-exact
backup; the updated local GCS is running without sending vehicle commands.

Raw test/build output, generated routes, workspace snapshots and configuration
checks are under ignored `simulation/logs/course-configuration/`. These checks
establish planning/UI behavior, not actual movement with the new preferences.
Earlier simulator movement evidence remains limited to its recorded settings.
Detector coverage, physical boat/radio operation and continuous replanning remain
unqualified. No vehicle tuning, simulator pins/dynamics or MAVLink ports change.
