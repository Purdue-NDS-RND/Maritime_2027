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
