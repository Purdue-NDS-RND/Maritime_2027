# Milestone 1 implementation handoff

**Status: selected simulator acceptance completed on 2026-10-28 (3/3 frozen passes).** Current work is on `revamp`, fast-forwarded locally to implementation commit
`9e11786` from `milestone1` under the repository branch instructions. Neither main
nor the archive was changed; nothing was pushed. See the follow-up results below. Runtime evidence is ignored under `simulation/logs/`.

## Implemented checkpoints

| Checkpoint | Implementation and evidence | Acceptance limit |
| --- | --- | --- |
| Reproducible scene | Per-run resolved world, models/meshes, manifest, bridge/SITL conversion source, parameter baseline, image identity, settings and source archive | Final dependency build reused verified pinned checkouts/binaries; plugins and application sources were rebuilt |
| Camera-free scenarios | `CAMERAS=off`, retaining the default camera-enabled path | Calibration/camera assets and baseline physics/parameters remain unchanged |
| GPS object map | Versioned export from snapshot, strict geometry/transforms, live model/pose/image verification; no source-scenario fallback | Fixed slalom active export is supported; other active scenes require corresponding recorder coverage |
| Alignment | Four live positions, three non-collinear locations, two headings; true SITL SIMSTATE versus physics IMU pose | Maximum observed conversion error 0.01495 m; estimated GPS error is separate |
| Whole-boat evaluator | Collision-mesh hull footprint and full-rotation propulsor bounds, per-step poses/contacts, stern/side/order/clearance/finish checks | Conservative collision prism is projected with full roll/pitch/yaw; missing height/pose/contact evidence remains inconclusive |
| GCS | React/Leaflet + FastAPI container, map import, manual edits, saved drafts, immutable approval, validation, individual commands and operation/status reporting | Live browser-to-boat entrance-gate workflow passed at 0.5 m/s; browser tile-load failure handling passed with external images blocked |
| Boat HTTP | Queue shared with ROS; single MAVLink worker, priority STOP cancellation, persistent idempotent operations, profile/firmware/geometry/parameter readbacks | Automated coverage plus a completed live GCS gate mission; live fault checks are recorded below |
| Gate passage | Boat-only and live GCS, unchanged entrance of the fixed slalom at commanded 0.5 m/s | Both passed independent evaluation; later full-course results are below |
| Full slalom | Development mission authored, evaluator/course support implemented | Full slalom independently passed boat-only at 0.5 m/s and through the browser at 1.0 and 1.5 m/s; three consecutive frozen 2.0 m/s target passes subsequently accepted below |

At the initial implementation checkpoint, the browser allowed tile-free map viewing, adding/reordering/deleting
waypoints, selecting the finish and saving a draft. File upload was blocked by
Chrome extension file-URL permissions. Later the browser explicitly denied
further access to localhost:8080. Browser actions stopped; that setting was not
changed and the denied browser workflow was not bypassed. The follow-up below
supersedes those browser limits for import, drag/reload and gate execution;
browser tile-load failure handling was subsequently tested with external images blocked; see below.

## Geometry and coordinate evidence

Development simulator run: `20261028T011251-321764`.
Evidence directory: `simulation/logs/runs/20261028T011251-321764/`.

- `scene/`: original immutable development snapshot and hash inventory.
- `alignment-raw.json`: first probe using requested positions, retained as
  diagnostic evidence only; teleports can retain motion and are not true poses.
- `alignment-poses.json` and `alignment.json`: actual adjacent physics IMU poses
  and true SIMSTATE geography, with measured conversion and heading differences.
- `object-map-final.json`: export verified against the active image, snapshot
  and recorded buoy centres. Initial marker-face coordinates are explicitly
  distinct from buoy centres; the face-orientation plugin can change them.
- `footprint-final.json`: collision STL/DAE extraction including link mounting
  and all-angle propulsor bounds, source geometry hashes and zero IMU offset.
  Enclosing circle radius is 0.668872 m. The inertial COM is not the GPS origin.
- `truth.jsonl`: actual boat/link/model poses and contacts at 0.001 s steps.
- `contact-probe.json`: first inconclusive contact placement in the gap between
  hulls, preserved. `contact-probe-hull.json`: deliberate hull-shell contact,
  independently recorded outside every mission evaluation window.

The pinned bridge applies the inverse configured world transform, giving
world X=east, Y=north and heading = 90 degrees minus world yaw. Its reported
position is the IMU-link pose; the pinned model has no IMU mounting translation.
The projection uses the pinned ArduPilot mean-latitude longitude scaling.
The exporter rejects unsupported mounting/transforms/geometry, modified files,
mismatched run/image identities and displaced/missing active buoys.

New snapshots separate a stable physical scene identity from a per-run snapshot
hash, so recorder destinations/timestamps do not change the physical scene ID.
The original development snapshot retains its older identity format and is
still verified without rewriting it. Snapshot files are treated as immutable;
verification detects changes instead of updating their hashes.

Recorder contact components follow the Gazebo physics component interface;
see [Gazebo Physics collision processing](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/physics/Physics.cc).
The live deliberate-contact test was necessary before interpreting empty
contact arrays as evidence of no contact.

## Measured development results

These are simulator measurements, not physical boat guarantees.

| Run | Target | Actual mean / peak | Time | Independent result |
| --- | --- | --- | --- | --- |
| Straight calibration | 0.5 m/s | 0.396 / 0.688 m/s | 29.21 s | Max lateral error 0.058 m; max estimated GPS-to-truth error 0.146 m; finish truth error 0.838 m |
| Entrance gate | 0.5 m/s | 0.372 / 0.683 m/s | 29.47 s | Pass: 1.208 m minimum clearance, stern cleared, finish settled |

Gate evaluation covers 29,472 consecutive physics samples. Its last settling
window has maximum position error 0.7564 m and peak speed 0.19983 m/s. The boat
also reported completion; the independent result did not rely on that report.
Gate command, trajectory, result and standalone speed/clearance plot:

- `simulation/logs/calibration/gate-0.5.json`
- `simulation/logs/calibration/gate-0.5.result.json`
- `simulation/logs/calibration/gate-0.5.evaluation.json`
- `simulation/logs/calibration/gate-0.5.png`

Two-leg baseline and pivot experiments are preserved alongside their metrics.
The non-aligned initial turn produced substantial error. A subsequent aligned
6 m / 10 m, 90-degree baseline turn still measured 0.632 m maximum cross-track
and 0.141 m maximum GPS-to-truth error. Its conservative allowance plus reserve,
boat circle and required clearance would not fit the entrance opening. This
rejects that profile; it does not establish that the fixed course is impossible.

The last focused experiment (`aligned-turn-0.5-pivot.result.json`) selected
WP_RADIUS=0.2, WP_PIVOT_ANGLE=30, WP_ACCEL=2, WP_JERK=5 and retained
WP_PIVOT_RATE=60. ArduPilot rejected arming with AHRS/DCM yaw inconsistency
following development pose resets. No pre-arm check was disabled and no
force-arm was attempted. All original values were restored and read back:
WP_RADIUS=3, WP_PIVOT_ANGLE=0, WP_PIVOT_RATE=60, WP_ACCEL=0, WP_JERK=0.
The earlier pivot experiment also restored its values. No restoration failure
sentinel was created.

At the initial checkpoint, only `sim-straight-0_5-v1` was installed under `simulation/logs/profiles/`, limited
to the measured approximately 10 m straight and 0.5 m/s. It does not validate
turns or higher speeds. Validation adds the measured 0.203436 m position/
tracking bound and an additional 0.10 m reserve. Profile data and calibration
artifacts are intentionally runtime evidence, not shipped default settings.

## Reproduction and next work

All simulator commands run from `simulation/`. Retain the normal clean build:

```bash
make validate
make build
CAMERAS=off WATER=calm SCENARIO=slalom WIPE_PARAMS=1 make run
# In another terminal after readiness:
make smoke
make buoy-tracking-smoke
```

The dependency build initially began rebuilding large system layers with 15 GB
free, so it was cancelled. The documented lower-storage development alternative
verifies all four pinned source commits before compiling current plugins and
copying current scripts/models/configuration. It preserves the original image:

```bash
make build-cached
CAMERAS=off WATER=calm SCENARIO=slalom WIPE_PARAMS=1 make run
```

The live calibration command used the boat image, mounted simulator tooling
and exclusive UDP 14551 ownership, for example from the repository root:

```bash
docker run --rm --network host --user 1000:1000 \
  -v "$PWD/simulation:/simulation" maritime-boat:latest \
  python3 /simulation/scripts/calibrate.py \
  /simulation/logs/calibration/gate-0.5.json \
  --truth /simulation/logs/runs/20261028T011251-321764/truth.jsonl \
  --output /simulation/logs/calibration/gate-0.5.result.json
```

Do not rerun that example against the archived run path. Select the active run,
stop the boat app first, use new mission/output identities and record exact
settings. `calibrate.py` accepts the five documented WP overrides plus the explicitly
measured `ATC_STR_RAT_FF` experiment (0..3), and
blocks later experiments if restoration fails. Its truth reads are measurement
only; Executor receives only the supplied GPS mission and MAVLink telemetry.
Use a fresh simulator start after pose/heading experiments to avoid confusing
estimator convergence with tracking behavior. Pre-arm failures remain failures.

For the current active run, use the host `export_active.py` wrapper, supplying
that run's alignment report. `alignment_probe.py` runs inside the simulator
container while disarmed with the boat app stopped. It moves the simulation
model and restores its pose; never run it during a mission. `alignment_report.py`
assesses the saved SIMSTATE/physics samples. `make_course.py` produces evaluation
roles, not route waypoints. `evaluate_run.py` requires explicit mission start/end
simulation times. `plot_evidence.py` needs host Matplotlib and saves a standalone
figure. All output paths belong under `simulation/logs/`.

Initial work queue (later follow-up sections record completed items):

1. Finish tile-failure acceptance. Browser map import, drag/edit/save/reload,
   validation/rejection, approval/upload/start/progress and gate passage passed
   in the follow-up, with OSM tiles disabled.
2. Develop a turn/spacing profile with measured conservative allowance that
   admits the unchanged course, covering both turn directions, stopping and
   initial heading. Freshly confirm parameter restoration after experiments.
3. Freeze a manually edited route, physical scene, geometry, profile and exact
   settings. Progress through 0.5, 1.0, 1.5 and 2.0 m/s with independent evidence.
4. Complete three consecutive 2.0 m/s full slaloms, restarting from identical
   initial conditions. Save every failure and reset the pass count.
5. Live GCS-backend loss/reconnect, operator STOP, independent-port manual
   takeover and telemetry-loss detection have follow-up evidence. Total telemetry
   loss still needs the recovery policy described below; this is not physical RC
   or physical vehicle failsafe acceptance.

Do not widen the course, weaken clearance, shrink empirical allowance or label
lower-speed results as milestone completion.

## Automated verification

- 23 boat tests: retained protocol/ROS regressions, idempotent operations,
  conflicting revisions, HTTP receipt/origin handling, STOP during start,
  firmware/geometry/live-parameter profile checks and restart behavior.
- 13 GCS tests in a network-disabled container: workspace persistence,
  approval invalidation, unsafe route/finish/start rejection, profile/speed/
  turn envelopes, authoritative API and separate operator commands.
- 5 scene/export tests, 10 evaluator tests and one isolated real-physics recorder test: axes/round trips, camera-off
  geometry, modified/stale/mismatched scenes, stable identity, stern-only
  collision, incomplete gate, order/side, missing physics steps and finish speed.
- React production build passed with the committed npm lockfile; npm audit
  reported zero vulnerabilities after updating Vite to 6.4.5.
- Retained `make validate` passed before the final build and is rerun for the
  final source. Runtime regression results are recorded below when finished.

Primary logs: `simulation/logs/milestone1-*.log`. Automated success, independent
gate passage and final milestone acceptance are distinct claims.

### Final simulator regression

Fresh final-format run: `20261028T014500-383985`.
`make validate` passed, as did the retained autonomous `make smoke` (actual
movement, HOLD, RTL and disarm). The isolated buoy smoke passed 3,499 facing
checks. Fresh alignment passed with 0.01472 m maximum conversion error;
`object-map.json` in that run directory passed active-scene/image/pose checks.
The final recorder also passed an isolated real-physics contact test with
named boat/obstacle collision events and contiguous physics steps. Gate
acceptance evidence remains the earlier recorded boat-only run; no claim is
made that the smoke test is slalom acceptance. All task-started containers
were stopped after validation, with the vehicle disarmed before shutdown.

The final source archive, patch, image IDs and test summary are under
`simulation/logs/milestone1-implementation/`. The original simulator tag and
all failed/diagnostic runs remain preserved. At that checkpoint browser authority
was denied, with no completed live GCS mission or 2 m/s full-course attempt.
The follow-up below records the subsequently accepted GCS gate workflow.

## Follow-up: live browser gate acceptance

Run `20261028T021354-409912`, using the existing
`maritime-milestone1-sim:current`, `maritime-boat:milestone1`, and
`maritime-course-gcs:milestone1` images. Sources at run start were `9e11786` on
`revamp`. The user enabled the browser extension's file upload permission; the
existing file import then succeeded. No paste-import code was added.

The real Chrome workflow exercised fresh exported-map file import, waypoint
placement and dragging, exact coordinate edits, gate role entry, saving and full
reload, unsafe-clearance rejection, approval revocation after edits, immutable
approval, upload, operation confirmation, explicit start, execution status and
disarm. All map/route actions and execution used OSM tiles disabled. Actual tile
network failure has not been exercised. The backend correctly refused the first
upload because the actual start-to-waypoint distance was outside the installed
straight profile; the route was edited, validated and approved again.

Alignment passed at 0.01484 m maximum error. Approved mission
`e351e17c-a449-4ba9-a0c7-02f816fb88c1` used the existing measured straight profile
and target 0.5 m/s. The GCS backend was stopped during execution; the browser
reported stale telemetry, while the boat independently completed in HOLD.
Restarting the GCS recovered completion and operation status without a new start.
Explicit browser disarm then succeeded. A disarmed deliberate hull-shell contact
was recorded after the mission window, qualifying this run's contact evidence.

Independent result: **passed**, 28,451 contiguous physics samples, 28.45 s,
1.06107 m minimum footprint clearance, entrance-gate stern passage confirmed,
0.79255 m maximum finish-window error and 0.19991 m/s peak finish-window speed.
Actual mean/peak speed was 0.37924 / 0.68388 m/s. This is entrance-gate evidence
only, with the scene and thresholds unchanged.

Evidence is under `simulation/logs/milestone1-followup/`: the frozen workspace,
approved mission, boat operation journal, observed status/physics samples, GCS
loss timestamps, course/footprint, `gcs-gate-evaluation.json` and `gcs-gate.png`.
Raw alignment, object map, contact proof and physics recording are in the run
directory. The boat command journal and individual session events remain under
`simulation/logs/boat/`.

A fresh turn characterization run (`20261028T021932-423050`) first refused arming
with `Gyros inconsistent` during estimator startup; original parameters were
restored. After estimator convergence, a new explicit attempt executed both turn
directions with WP_RADIUS=0.2, WP_PIVOT_ANGLE=30, WP_PIVOT_RATE=60, WP_ACCEL=2
and WP_JERK=5. It **failed** finish settling: final truth error 1.49850 m and
1.24303 m travel after entering stopping. Maximum cross-track was 0.54561 m and
GPS/truth error 0.18795 m, a combined empirical allowance of 0.73356 m. The
180 s timeout expired in HOLD. Stop/disarm and restoration readbacks succeeded;
no profile was installed from this failed run. All failed artifacts are retained.

Calibration tools now fail success qualification if cleanup is unconfirmed or
any changed parameter lacks matching restoration readback. Reports reject failed
calibrations by default; `--diagnostic` retains their measurements while setting
`calibration_usable: false`. Six focused regression tests cover qualification,
missing/wrong/nonfinite restoration, navigation failure and cleanup failure.

### Full-attitude independent evaluation

The follow-up initially found that a successful turn run exceeded the evaluator's
implicit 0.05 rad roll/pitch approximation limit. Its original result remains
`turn-both-0.5-gentle.evaluation.json` (inconclusive). The evaluator now encloses
the collision geometry in its existing XY polygon extruded through
`[-max_abs_z_m, max_abs_z_m]`, rigidly rotates that conservative prism using the
full Gazebo attitude, and projects its convex hull. Containment is preserved by
both operations; buoy collisions are conservatively treated as infinite vertical
cylinders. Gate/side/stern checks use the same projected bound. Explicit
course-specific attitude limits remain enforced. No clearance, reserve or
empirical tracking allowance was reduced.

Fifteen evaluator tests cover full attitude, independent sequential-rotation
containment, collision-height projection, tilted gate interference, missing
height, contacts, passage order, stern and finish settling. Re-evaluating the
original gate evidence still passes: minimum clearance 1.06113 m and stern-clear
time 240.747 s. Its new result/plot use `gcs-gate-prism-*` names, preserving the
original result. New turn evaluations use `*.prism.evaluation.json`; completed
open-water characterizations are not full slalom acceptance.

### Live control and telemetry fault checks

These used the existing boat image in run `20261028T023002-442841`, away from
course obstacles. A simulation-only relay bound the unchanged simulator API port
14551, with the boat temporarily configured to receive at 14651. No committed
port/default configuration changed. The separately supplied GPS missions used
the retained `local-file-unvalidated` boat-only path; these tests do not claim
GCS clearance approval or slalom passage.

- Dropping only GLOBAL_POSITION_INT while retaining heartbeat/GPS caused failure
  after position age exceeded 3 s. ArduPilot HOLD was confirmed with fresh
  heartbeat, and restoring position telemetry did not resume execution.
- Operator STOP during a live mission confirmed HOLD; explicit disarm succeeded
  after speed fell below 0.2 m/s.
- Dropping all telemetry caused a stale-heartbeat failure after 3 s. Without a
  fresh heartbeat, the app could not confirm stop. After link restoration,
  ArduPilot was still AUTO while the app remained failed; an explicit STOP then
  confirmed HOLD and disarm. This exposes the recovery-policy choice: deferred
  HOLD once fresh AUTO is observed versus requiring an operator STOP. No claim
  is made that total telemetry loss autonomously stops the vehicle.
- An independent client on the retained operator port 14550 selected MANUAL.
  The boat app reported interrupted, preserved MANUAL for the observation window,
  and required explicit new authorization. Subsequent explicit STOP/disarm
  succeeded. This verifies independent MAVLink takeover in simulation, not RC
  hardware or physical radio failsafes.

Scripts, receipts, per-case status samples and relay transitions are retained as
`fault_cases.py`, `fault_relay.py`, `manual_mode.py`, `fault-cases.jsonl`,
`fault-relay-events.jsonl` and `fault-cases-retry.log` under the follow-up directory.
The first harness launch preceded HTTP readiness and was refused before any
mission action; its error log is preserved separately. The retried harness
completed all four checks and left the boat disarmed in HOLD.

Additional turn trials kept the fixed scene and clearance settings unchanged:

| Characterization | Empirical tracking + positioning allowance | Stop travel | Finish truth error | Result |
| --- | --- | --- | --- | --- |
| Open-water 90°, accel 0.5 / jerk 1 / pivot 60°/s | 0.74505 m | 0.49583 m | 0.83580 m | Navigation and independent finish passed |
| Open-water 90°, accel 0.2 / jerk 0.4 / pivot 60°/s | 0.82255 m | 0.26869 m | 0.61361 m | Navigation and independent finish passed; worse tracking |
| Open-water 90°, accel 0.5 / jerk 1 / pivot 30°/s, aligned start | 0.74846 m | 0.44150 m | 0.78391 m | Boat completion; allowance does not fit gates |
| Open-water 55°, 2 m short legs, accel 0.5 / jerk 1 / pivot disabled | 0.88150 m | 0.45349 m | 0.61061 m | Navigation and independent finish passed; allowance does not fit gates |
| Open-water 55°, accel 0.5 / jerk 1 / pivot 15°/s | 1.14526 m | 0.48480 m | 0.66563 m | Boat completion; worse tracking |

An earlier 30°/s trial began 19.19° off its first leg; its smaller 0.68933 m
allowance is not substituted for the aligned characterization. Reports now
record actual initial-heading error, and the later probe authors its fixed test
pattern along a stationary, settled reported heading. None of these trials was
installed as a new live slalom profile.

A manually authored 12-waypoint slalom draft, with short flat sections at each
turn buoy, is retained as `manual-slalom-flat-0.5.json` and
`manual-slalom-flat-draft.json`. Validation against the measured 55°/short-leg
non-pivot candidate rejected both gates: the required conservative swept circle
overlaps each gate buoy's required margin by 0.239 m. This candidate uses a
0.76735 m sphere radius enclosing the complete collision prism at every attitude,
the measured 0.88150 m tracking/position allowance, the unchanged 0.10 m reserve
and 0.25 m clearance. The report is `manual-slalom-flat-validation.json`. The
candidate profile is saved only in the follow-up directory, **not** installed
under `simulation/logs/profiles/`. No rejected slalom was started. At that checkpoint no higher-speed
progression had been attempted; the subsequent accepted stages are below.
Final repeatability was 0/3 at that checkpoint; the final sequence below supersedes this count.

The next control investigation should explain the measured corner drift before
further speed progression. Changing the protected baseline dynamics/parameters,
widening the course, dropping the reserve or replacing the empirical allowance
with a smaller assumption are not validated solutions.

### Steering-rate diagnosis and bounded tuning

The parameter sweep alone did not establish a useful route. DataFlash log
`simulation/logs/state/logs/00000110.BIN` and its matching MAVProxy tlog showed
that the observed cross-track error was also reported by ArduPilot, rather than
being an exporter/frame mismatch. Steering requests around 12 degrees/s sometimes
produced only 2--4 degrees/s, followed by heading oscillation. Read-only extracted
control evidence is retained under the follow-up directory.

A single new calibration override, `ATC_STR_RAT_FF`, is now bounded to the pinned
firmware's documented 0..3 range. This does not change the protected parameter
file. Every experiment saves the prior live value, independently reads back the
applied value, and restores/readbacks it under the same failure sentinel as the
waypoint settings.

In run `20261028T041402-619068`, FF=0.8 with the earlier 0.5 m/s/90-degree probe
reduced maximum cross-track to 0.45731 m and the conservative combined allowance
to 0.62147 m. Stop travel was 0.47988 m and finish truth error 0.78067 m. Independent
evaluation passed, with finish error 0.78663 m, no contact and 2.08202 m minimum
clearance in that open-water probe. All original values, including FF=0.2, were
restored and verified.

The resulting development profile uses the conservative full-attitude enclosing
sphere (0.76735 m), the unchanged measured allowance and 0.10 m reserve. A manually
authored seven-waypoint route was validated against both gates and all four turn
buoys without reducing clearance. New boat readback checks verify the explicit
steering gain at both upload/start; old five-parameter profiles require FF=0.2.
All 24 boat tests passed, including wrong-gain rejection and legacy-profile
protection. No control gain is silently applied by the boat application.

An additional diagnostic matched DataFlash POS and SIM geography at identical
TimeUS values. The 26,329 matched pairs agree exactly in the retained simulation,
which runs AHRS_EKF_TYPE=10 (native simulator state). The earlier reported
GPS/truth separations compare old telemetry with a newer physics sample and
include transport age. Existing profile allowances were **not reduced** using
this diagnostic; the report now states that timing method explicitly. This
simulation does not establish noisy GPS/estimator or physical-boat performance.

### Accepted full-course development stages

| Stage | Run / mission | Independent clearance | Time | Actual mean / peak | Finish maximum error |
| --- | --- | --- | --- | --- | --- |
| Boat-only 0.5 m/s | `20261028T041811-626990` / `manual-slalom-0_5-ff08-001` | 1.25485 m | 134.532 s | 0.39805 / 0.68655 m/s | 0.71287 m |
| Live browser 1.0 m/s | `20261028T044511-677325` / `4ca54c53-8829-43f7-aff5-9d383f79347b` | 1.24567 m | 86.522 s | 0.62581 / 1.05716 m/s | 0.71488 m |
| Live browser 1.5 m/s | `20261028T045817-704630` / `c73fc9a5-2891-4c3f-af8b-662ac6a15642` | 1.22079 m | 76.459 s | 0.72044 / 1.55506 m/s | 0.79458 m |

All three passed all six passage-order/side/stern checks, contact and complete-footprint
clearance checks, and independent 5 s finish settling. The 0.5 m/s run covered
134,533 consecutive physics samples; 1.0 m/s covered 86,523. Raw result, evaluator,
course, frozen inputs and plots use `slalom-0.5*` and `gcs-1.0*` names under the
follow-up directory. These are lower-speed development successes, not final
Milestone 1 acceptance.

The 1.0 m/s profile adds explicit speed P=1.2 / I=0.05 to steering FF=0.8 and
WP_RADIUS=0.2 / PIVOT_ANGLE=30 / PIVOT_RATE=60 / ACCEL=0.5 / JERK=1. Its
independently checked turn probe measured a 0.56536 m combined allowance.
The boat app verifies all recorded gains; missing gains in older profiles
require their original defaults. All 26 boat tests passed, including legacy-gain
protection, nonfinite-value rejection and observed telemetry-rate verification.

A requested 20 Hz interval was initially acknowledged but still delivered 4 Hz: we
traced MAVProxy's repeated rate enforcement. `MAVLINK_STREAMRATE=4|10|20` now
selects the launch rate, defaulting to the original 4 Hz. No MAVLink ports,
firmware/source pins, physical dynamics or default controller parameter file
changed. The 20 Hz launch and profile agree; upload/start verify source-timestamp
frame spacing, rather than relying on an ACK alone. The 1.0 m/s probe observed
a maximum 0.0204 s reported position age and 0.06885 m reported-position/latest-
truth separation, retaining that measured error plus the unchanged 0.10 m
reserve. Calibration restores the explicitly recorded launch-rate baseline.

For live GCS testing, `profile_settings.py` explicitly applies a measured profile
while the boat service is stopped and disarmed, saves originals before mutation,
and verifies the live profile. The boat application remains readback-only for
these gains. After confirmed browser disarm and boat shutdown, the same script
restores/readbacks the originals. Its state files and any restoration failure
sentinel are retained.

The browser test also found and fixed a same-physical-scene import bug: the old
uncontrolled passage textarea could display earlier roles after the saved draft
was reset. The passage editor now resets on import/load, revokes approval while
edited, and blocks save/validate/approve/upload/start for invalid JSON. Live
checks verified same-scene import reset and invalid-role approval revocation
before reapproval/upload/start. STOP/disarm remain available. The React
production build passed. Browser tile-load failure handling is recorded below.

### 1.5 m/s completion and optional tile failure

The 1.5 m/s browser-started mission completed with 76,460 consecutive physics
samples and a valid finish window whose peak speed was 0.19995 m/s. Explicit
disarm was confirmed through the boat API, then the boat application was stopped
and every staged parameter was restored and independently read back. Evidence:
`gcs-1.5.evaluation.json`, `gcs-1.5-observation.jsonl`, frozen workspace and
`gcs-1.5-settings-20261028T045817-704630.json` in the follow-up directory.

The optional OSM layer previously used maxZoom=19 while the course opens above
zoom 19; checking its box created zero tile images. Its display ceiling is now
24 with native tiles still capped at 19. Live Chrome loaded two 256-pixel tiles
at course zoom. A temporary runtime-only Content-Security-Policy then blocked
external image loads while preserving the local frontend/API. The browser
reported “Background unavailable. Course editing remains available.”; changing
target speed and saving the draft still worked. This tests browser resource
load failure, not a physical internet outage. Screenshot:
`tiles-blocked-browser.png`. The original served HTML was restored and its
SHA256 checked equal; the fault fixture was not added to application code.

The first 2.0 m/s 90-degree probe with speed P=1.2 completed and independently
passed open-water clearance/finish checks, but measured allowance 0.65788 m
exceeds the fixed gate budget (about 0.64265 m). It was not installed as an
approved slalom profile. Its original settings were restored; the failed
clearance qualification remains recorded as `open-turn-2.0-p12-20hz*`.

### 2.0 m/s qualification and frozen repeat procedure

Increasing only the bounded experimental speed P gain to 1.6 (I=0.05, steering
FF=0.8, other measured waypoint settings unchanged) improved the 90-degree probe:
0.40348 m maximum cross-track, 0.11809 m latest-reported-position/physics
separation, 0.52157 m combined allowance. Navigation, independent collision-prism
clearance and finish checks passed, then disarm and all original gains were
restored. Raw files: `open-turn-2.0-p16-20hz*`.

A first browser-started full course with the larger retained 1.5 m/s allowance
(0.61546 m) passed independent evaluation in run `20261028T050944-734036`:
74.416 s, 1.26211 m minimum clearance, 0.73174 / 1.91675 m/s actual mean/peak,
0.58747 m finish error. However, the 10 Hz browser observation stream measured
0.44485 m maximum lateral error plus 0.17261 m position/physics separation:
0.61746 m combined. This observation method includes HTTP/status transport age.
The allowance was therefore increased to **0.640 m**, including a further
0.02254 m empirical guard. The separate **0.10 m reserve and 0.25 m hull clearance
remain unchanged**. The fixed gate geometry still passes static validation.

The initial 2.0 m/s pass is retained as development evidence, excluded from the
three-pass sequence after this profile change. No measured error was reduced.
The revised profile is `sim-slalom-2_0-p16-20hz-v2`; its probe/full-course source
hashes and metrics are retained in the profile. `series1-reclassified.json`
records the exclusion. All original files and persistent journals remain.

Each final repeat uses a fresh calm-water slalom simulation with
`MAVLINK_STREAMRATE=20 CAMERAS=off WATER=calm SCENARIO=slalom WIPE_PARAMS=1`
and the same simulator image. There are no teleports before these missions.
A fresh stationary SIMSTATE observation checks alignment; the frozen map retains
the original full multi-position/two-heading conversion proof. Active scene,
image and buoy-coordinate identity are checked on each run.

The same approved envelope is explicitly uploaded and started from the browser
for every repeat. Separate explicit `/logs/final2-series2-repeatN` test-session
journals preserve the existing replay protections without deleting historical
operations or changing the boat application. No automatic start is introduced.
After each mission, disarm is independently confirmed, its boat container is
stopped, and the staged gains are restored and read back. Frozen workspace,
input/image hashes, session identity, raw observations, evaluations and rollback
states use `final-2.0-series2-*` in the follow-up directory.

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
parameter restoration/readback. Their stopped boat containers and persistent
journals are retained. Task-started simulator and GCS runtimes were stopped
after evidence capture. The default parameter file, dynamics, source pins and
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

Final verification: simulator `make validate` passed, including 15 evaluator
and 6 calibration qualification tests; all 26 boat tests and 13 GCS tests
passed. The rebuilt React production bundle passed and live Chrome verified
normal background tile loading plus controlled external-image failure. The
retained movement/HOLD/RTL/disarm smoke and buoy-tracking runtime results
remain as recorded above; no extra physical-control acceptance is implied.

Remaining work belongs to subsequent design/physical validation: noisy survey
and GPS errors, buoy movement, competition-boat dynamics, physical RC and
networking. The separately documented total-telemetry-loss recovery policy is
still undecided: after restoration the failed application does not silently
resume or claim HOLD; the observed AUTO case required explicit operator STOP.
No unapproved recovery-policy change was made. No commit or push was performed.

## Follow-up: live GCS map telemetry and orientation

The web GCS now has a passive MAVLink reader, independent of the boat's HTTP
mission interface. It defaults to simulator UDP 14550; the boat retains UDP
14551. Connection, serial baud and target autopilot IDs are configurable for
future radio use, including host-forwarded or directly mapped serial devices.
The reader does not send commands or change stream rates. The browser samples
the latest snapshot through a 5 Hz event stream and shows an outlined boat with
a clear bow, forward arrow and permanent compass/degrees label. Stale data
greys the last known position; unknown heading has a neutral question-mark
symbol. Mission commands and completion remain boat-owned.

All 25 GCS tests passed, including real UDP/serial pseudo-terminal input and a
real HTTP/SSE movement/loss test with the boat API blocked. The production
frontend build and UDP/serial Compose checks passed. The operator reported live
simulator movement working; Chrome rendering of the updated oriented marker
was checked against the running simulator. This does not extend the earlier
full-course/clearance acceptance to hardware. Physical RFD900 operation, RF
coverage and latency remain unverified. See [live position](gcs_live_position.md)
and the [manual tracking test](../simulation/docs/GCS_LIVE_POSITION.md).

## Canonical runtime images

Current commands use `maritime-sim:latest`, `maritime-boat:latest` and
`maritime-gcs:latest`. Earlier image names above identify historical evidence;
their tags are superseded and may have been removed after source/image checks.
Image IDs remain in the ignored run inventories. See [runtime maintenance](runtime_maintenance.md)
for the fresh integration check and cleanup. Plain simulator `make run` now
selects calm water, cameras off and slalom; telemetry remains 4 Hz. Reproducing
the measured slalom profile requires explicit 20 Hz and staged profile settings.
