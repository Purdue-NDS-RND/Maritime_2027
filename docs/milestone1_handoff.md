# Milestone 1 implementation handoff

**Status: incomplete. Do not mark the milestone accepted.** Work remains on
`milestone1`, based on `320415d`; no merge, push or archive/main/revamp change
was made. Runtime evidence is ignored under `simulation/logs/`.

## Implemented checkpoints

| Checkpoint | Implementation and evidence | Acceptance limit |
| --- | --- | --- |
| Reproducible scene | Per-run resolved world, models/meshes, manifest, bridge/SITL conversion source, parameter baseline, image identity, settings and source archive | Final dependency build reused verified pinned checkouts/binaries; plugins and application sources were rebuilt |
| Camera-free scenarios | `CAMERAS=off`, retaining the default camera-enabled path | Calibration/camera assets and baseline physics/parameters remain unchanged |
| GPS object map | Versioned export from snapshot, strict geometry/transforms, live model/pose/image verification; no source-scenario fallback | Fixed slalom active export is supported; other active scenes require corresponding recorder coverage |
| Alignment | Four live positions, three non-collinear locations, two headings; true SITL SIMSTATE versus physics IMU pose | Maximum observed conversion error 0.01495 m; estimated GPS error is separate |
| Whole-boat evaluator | Collision-mesh hull footprint and full-rotation propulsor bounds, per-step poses/contacts, stern/side/order/clearance/finish checks | Convex bound is conservative; attitudes outside the small-angle projection envelope make a run inconclusive |
| GCS | React/Leaflet + FastAPI container, map import, manual edits, saved drafts, immutable approval, validation, individual commands and operation/status reporting | Complete live browser-to-boat workflow is unaccepted |
| Boat HTTP | Queue shared with ROS; single MAVLink worker, priority STOP cancellation, persistent idempotent operations, profile/firmware/geometry/parameter readbacks | New HTTP/queue paths have automated coverage, not a completed live GCS mission |
| Gate passage | Boat-only, unchanged entrance of the fixed slalom at commanded 0.5 m/s | Passed independent evaluation; not the full GCS gate demonstration |
| Full slalom | Development mission authored, evaluator/course support implemented | No accepted full slalom, higher-speed progression or frozen 2 m/s profile; 0/3 final passes |

The browser allowed initial tile-free map viewing, adding/reordering/deleting
waypoints, selecting the finish and saving a draft. File upload was blocked by
Chrome extension file-URL permissions. Later the browser explicitly denied
further access to localhost:8080. Browser actions stopped; that setting was not
changed and the denied browser workflow was not bypassed. Full reload/drag,
network/tile failure and end-to-end operator acceptance remain open.

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

Only `sim-straight-0_5-v1` is installed under `simulation/logs/profiles/`, limited
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
SIM_IMAGE=maritime-milestone1-sim:current CAMERAS=off WATER=calm SCENARIO=slalom WIPE_PARAMS=1 make run
```

The live calibration command used the boat image, mounted simulator tooling
and exclusive UDP 14551 ownership, for example from the repository root:

```bash
docker run --rm --network host --user 1000:1000 \
  -v "$PWD/simulation:/simulation" maritime-boat:milestone1 \
  python3 /simulation/scripts/calibrate.py \
  /simulation/logs/calibration/gate-0.5.json \
  --truth /simulation/logs/runs/20261028T011251-321764/truth.jsonl \
  --output /simulation/logs/calibration/gate-0.5.result.json
```

Do not rerun that example against the archived run path. Select the active run,
stop the boat app first, use new mission/output identities and record exact
settings. `calibrate.py` accepts only the five documented WP overrides and
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

Remaining required work:

1. Resolve browser authority and finish real map-import, drag/reload, offline/
   tile-failure and complete gate workflow acceptance through the GCS.
2. Develop a turn/spacing profile with measured conservative allowance that
   admits the unchanged course, covering both turn directions, stopping and
   initial heading. Freshly confirm parameter restoration after experiments.
3. Freeze a manually edited route, physical scene, geometry, profile and exact
   settings. Progress through 0.5, 1.0, 1.5 and 2.0 m/s with independent evidence.
4. Complete three consecutive 2.0 m/s full slaloms, restarting from identical
   initial conditions. Save every failure and reset the pass count.
5. Perform live GCS-backend loss/reconnect, operator stop/manual takeover and
   telemetry-loss tests. Unit tests are not live acceptance or physical RC proof.

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
all failed/diagnostic runs remain preserved. Browser authority remains denied;
there was no completed live GCS mission and no 2 m/s full-course attempt.
