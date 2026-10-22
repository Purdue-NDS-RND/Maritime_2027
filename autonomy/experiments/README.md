# Navigation experiments

This records navigation development on `experiment/nav2-course-tuning` and
optional controller tuning. The shared baseline includes map-backed navigation,
reduced rates, and pose timing hardening; the moderate-speed profile
remains opt-in. Historical trial results below retain their original limitations.

## Main baseline integration checks (2026-10-22)

The broader integration run passed `make -C Simulation verify-rgbd` across
`one`, `gate`, seeded `multi`, `repeated_red`, `slalom`, and the original
camera-only ArduPilot smoke test. It also passed all 12 `lifecycle-smoke` cases:
default Adapter startup, two bounded startup failures, simulator/child/Adapter
exits, camera and FCU silence, SIGINT, SIGTERM, double-start rejection, and
parameter persistence/reset. Original SITL EEPROM bytes are preserved and
restored after the owned test stack stops.

Additional checks passed: 48 ROS evaluation tests; 14 repository boundary tests
(one ROS-only host skip covered by the 9-test ROS boundary run); 58 simulator
unit tests (six MCAP host skips covered by the 12-test recording run); Monitor
validation and cross-container smoke; and 14 live-mapping tests on the rebuilt
viewer image. After the terminal-gate correction below, a fresh navigation image
built through the supported Dockerfile passed 43 autonomy tests, 5 bridge tests,
and all 3 real Nav2 scenarios, including the full-stern gate assertion. Its
installed mapper/navigation sources were compared byte for byte with checkout.

Evidence is under `Simulation/logs/merge-*.log`,
`Simulation/logs/lifecycle-20261022T030905Z/`, and
`Simulation/logs/merge-validation/`. GitHub reported no commit status entries or
PR-triggered workflow runs; these are local/simulation checks, not CI results.

The repeat run `navigation-20261021-232941` captured three actual adjacent-pose
rate anomalies. Examples include 17.8 mm over 0.926 ms and 22.3 mm over 0.707 ms
in converted time. Their original odometry headers were also less than 1 ms
apart; another event's 1.004 ms source interval became 0.244 ms after conversion.
Thus these events already contain upstream timing/pose inconsistency, and the
converter can amplify it. The exact upstream cause and the historical
rotation-specific incident are not proven. Offline replay confirms each captured
pair would trip the old adjacent-rate rule, while all three captured histories
pass the hardened checker with short-interval poses withheld. Evidence:
`merge-validation/live-anomaly-replay.json` and the session's `clock.log`.

### Terminal gate completion correction

The repeat completed all six mission events and all independent buoy-crossing
checks in 642.5 s, with minimum hull clearance 0.555 m, a healthy mapper, and
verified HOLD/disarm. **It failed full-course acceptance:** the stern was still
0.155 m short of the physical exit plane. This is not counted as another full
slalom pass. The prior constant 2.2 m departure target used the estimated gate
center without carrying its range uncertainty into the completion rule.

Terminal gates now retain each landmark's covariance and footprint. Their
departure goal clears the farther endpoint's two-sigma bound, footprint, maximum
projected rear extent of the 2.2 x 1.2 m hull, and configured clearance. Padding
also covers mission arrival tolerance, target-update deadband, and a small
reserve. Completion explicitly requires the resulting course-coordinate
`gate_finish_s`. Intermediate entry gates keep their existing departure distance
to avoid extending that leg through the next course turn. Physical obstacle
costs and the independent evaluator are unchanged.

Regressions cover a 1 m underestimated range, skewed endpoints, covariance
projection, and intermediate-entry behavior. The final correction passed the
43-test autonomy suite and real Nav2 gate integration. **No full slalom was
rerun after this final correction.** Broader seed, water, and hardware acceptance
remain open; this merge establishes a development baseline.

After the repeat session's verified HOLD/disarm, the Adapter later became
unhealthy and the launcher removed the stack. The cause is unresolved; evidence
is `merge-slalom-startup.log` and run `20261022T032843-235400/failure.log`.
A subsequent stationary telemetry-service probe timed out before collecting its
planned comparison; its direct Adapter health check passed. No telemetry cleanup
behavior was changed on that evidence. The auxiliary retry was not run, the owned
stack was stopped, and original SITL state was restored. Restart Simulation
between trials; post-session Adapter readiness remains a follow-up limitation.

### Existing clean Adapter build limitation

The supported Adapter Dockerfile was unchanged from the prior `main`, but its
clean build failed during this run because apt no longer serves pinned MAVROS
`2.15.1-1noble.20260903.022619` and extras `2.15.1-1noble.20260903.025450`.
Those versions were verified in the retained working image. The Adapter used
for broad regressions has identical executable telemetry code (only a module
docstring differs); a source-only rebuild on that retained image matches the
checkout exactly and preserves installed packages. The simulator startup script
also matches the checkout. No pinned versions were relaxed. A clean installation
still needs a verified archive/mirror or a separately reviewed dependency update.
The navigation and viewer images built successfully. Logs:
`merge-adapter-build.log`, `merge-adapter-package-versions.log`,
`merge-adapter-executable-match.log`, and `merge-adapter-source-build.log`.

## Start with the system overview

Read the [experimental navigation overview](../../docs/NAVIGATION_SYSTEM_OVERVIEW.md)
for architecture diagrams, every navigation node's responsibilities, the RGB
mapping and Nav2 flow, map representations, stop/fault behavior, and monitoring
commands. It distinguishes ROS nodes from the mission/costmap modules inside
the supervisor.

The boat's reported real-world 1 m/s capability is a future test target.
The current supervisor **and** command bridge reject forward commands above
0.50 m/s; the default is still 0.20 m/s. The overview includes the
[changes and measurements needed for faster trials](../../docs/NAVIGATION_SYSTEM_OVERVIEW.md#speed-development-toward-1-ms).

## Run a controller comparison

The first comparison changes only Regulated Pure Pursuit's desired speed from
0.20 to 0.35 m/s. The standard Nav2 YAML remains the default. The experimental
YAML does not alter the hull, physical obstacle clearance, graded uncertainty,
freshness checks, collision prediction, or independent truth-only judge.

Start a fresh dual-camera, calm-water gate in `Simulation/`. From the repository
root, compare these runs, resetting the simulation between trials:

```bash
NAVIGATION_IMAGE=maritime-autonomy-nav2-experiment:jazzy \
  python3 autonomy/tools/navigation.py run --task gate \
  --assume-bounded-water --bootstrap-clear-start --evaluate --mission-timeout 240

NAVIGATION_IMAGE=maritime-autonomy-nav2-experiment:jazzy \
  python3 autonomy/tools/navigation.py run --task gate \
  --assume-bounded-water --bootstrap-clear-start --evaluate --mission-timeout 240 \
  --nav2-overrides autonomy/experiments/moderate-speed.yaml
```

The runner copies overrides into `Simulation/logs/navigation-*/nav2-overrides.yaml`
and records their SHA-256 plus the exact image ID in `settings.json`. The image
must include this branch's updated launch file; `NAVIGATION_IMAGE` selects an
independent image tag for both build and run actions. A normal full build is:

```bash
NAVIGATION_IMAGE=maritime-autonomy-nav2-experiment:jazzy \
  python3 autonomy/tools/navigation.py build
```

Compare independent course completion and hull clearance before elapsed time.
Passing a gate does not establish slalom performance or repeatability.

## Pose timing hardening (2026-10-21)

The shared mapper now uses a minimum 20 ms motion-check interval. Shorter
interval poses are withheld from interpolation until a sufficiently separated
pose arrives. The 15 m/s and 4 rad/s bounds are unchanged; large short-interval
jumps still fault immediately using the minimum-window envelope (0.30 m and
0.08 rad at defaults). Rewinds and conflicting duplicates are checked against
every received pose, including withheld ones. A confirmed fault still requires
a new mapping session and navigation HOLD/disarm. This change is shared by
simulation and hardware consumers; it adds no simulator inputs to autonomy.

The previous 0.446 ms / 0.001834 rad failure is covered by an exact regression.
Tests also cover sustained excessive turn rate, immediate large jumps,
withheld-pose ordering, missing brackets, and end-to-end frame waiting. The
minimum interval is the mapper parameter `min_pose_motion_interval_s`; reducing
it increases instantaneous-rate sensitivity, increasing it adds pose latency.
The 20 ms default is a bounded engineering choice, not hardware calibration.

Diagnostic capture is bounded and emits structured JSON into session logs:

- `mapping.log`: one `POSE_FAULT_TRACE` containing up to 100 received poses,
  covariance, accepted-clock stamps, and the latched reason.
- `clock.log`: the first three `POSE_CLOCK_ANOMALY` events include original and
  converted timestamps, receipt times, pose, and exact conversion brackets.
  A mapper ERROR also emits one `POSE_CLOCK_TRACE` with up to 200 recent poses.
- `/mapping/diagnostics`: `pose_short_interval_withheld` counts downsampled poses.

A synthetic ROS test demonstrates that an allowed clock-conversion slope can
compress pose spacing and trigger the old adjacent-rate check. This is a
possible mechanism, not proof of the historical fault's cause. The provisional
receipt-based converter is **not repaired or approved for hardware** by this
change. Hardware still needs verified camera/FCU acquisition-time alignment;
neither changing `use_sim_time` nor raising a rate limit supplies that alignment.

Validation logs are `Simulation/logs/nav-pose-*.log`. The first benchmark attempt
used stale generated map interfaces; the isolated `maritime-benchmark-pose:jazzy`
image rebuild resolves that mismatch. The current-image suite passes 70 tests;
the focused clock capture suite passes 2 tests. The standard live-mapping suite
passes 14 tests, including the new capture tests. All 39 autonomy unit tests,
5 bridge tests, and 3 real Nav2 integration scenarios also pass. Final static
validation includes the Gazebo asset checks.

**Live full slalom passed** in `navigation-20261021-215154` at the unchanged
default desired speed of 0.20 m/s: 697.0 s, all six course events completed,
minimum conservative hull clearance 0.548 m, whole-stern exit clearance 0.844 m,
no clearance violation, and verified HOLD/disarm. Both cameras contributed.
Late-course diagnostics recorded 8 withheld short-interval poses with a healthy
mapper and no pending frames. No `POSE_CLOCK_ANOMALY` or mapper fault was emitted;
this run therefore does not establish the cause of the historical failure.
The exact old failure pair is covered synthetically, not reproduced live here.

The 60 s rate probe passed: 5 Hz maps, 10 Hz commands, supervisor tick p99
14.5 ms. This early window overlapped isolated integration tests. Late in the
course, the existing planning-grid age guard briefly stopped commands twice
for about one tick each; the early rate result is not a full-course timing
guarantee. Evidence: `Simulation/logs/nav-pose-validation/`. This is one calm,
dual-camera run on the simulation PC, not repeatability or Jetson/hardware
acceptance. The earlier failed course records below remain historical evidence.

The isolated test image is `maritime-autonomy-nav2-pose:jazzy`; older rate or
experiment images do not acquire this checker change automatically. To rebuild
from this checkout and run it against a separately started simulation:

```bash
NAVIGATION_IMAGE=maritime-autonomy-nav2-pose:jazzy \
  python3 autonomy/tools/navigation.py build
NAVIGATION_IMAGE=maritime-autonomy-nav2-pose:jazzy \
  python3 autonomy/tools/navigation.py run --task slalom \
  --assume-bounded-water --bootstrap-clear-start --evaluate --mission-timeout 1200
```

## Reduced map rates (2026-10-21)

The navigation runner now requests 5 Hz shared-map/physical-grid snapshots.
The standalone mapper's default remains 10 Hz. The supervisor builds/publishes
planning grids at up to 5 Hz and caches unchanged geometry; header timestamp
changes alone do not trigger a rebuild. Cell content, mapped geometry/covariance,
bearings and mission policy changes are included in the cache key.

Global/local Nav2 costmaps update at 2/10 Hz and publish at 1 Hz each. The
controller and supervisor remain 10 Hz, the command bridge remains 20 Hz, and
camera capture, desired speed and freshness thresholds are unchanged.

One background worker builds immutable input snapshots at up to 5 Hz, coalescing
new requests while busy. The command loop uses its last completed grid. If
geometry has changed and that grid's source is over 0.5 s old, commands stop
with `waiting_for_planning_grid` until a usable result arrives. Sensor progress checks,
permanent-pause/session-reset faults and per-command hull sweeps remain active.
Old map publications cannot refresh acquisition evidence.

`/navigation/status` adds `planning_grid_builds`, `planning_grid_build_ms` and
`tick_ms`. A read-only acceptance probe checks live ROS parameters, topic rates,
build rate and callback timings:

```bash
# From the repository root, after building this branch's navigation image:
docker run --rm --network host -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" \
  -v "$PWD/Simulation/tests/evaluation/navigation_rate_probe.py:/probe.py:ro" \
  -v "$PWD/Simulation/logs:/results" \
  "${NAVIGATION_IMAGE:-maritime-autonomy-nav2-experiment:jazzy}" \
  bash -lc 'source /etc/maritime_autonomy_setup.bash && python3 /probe.py \
    --duration 60 --output /results/navigation-rates.json'
```

This probe requires this branch's interfaces, a running navigation session and
the same ROS domain. Host simulation timing is not a Jetson benchmark.

### Final sparse-sector validation and remaining blocker

Static validation, **39 autonomy unit tests**, **5 bridge tests**, and all three
real Nav2 integration scenarios passed with the final optimized image. Detour
and narrow-gate minimum hull clearances were 1.140 m and 0.451 m. Stale-map
stopping/recovery, blocking walls, session resets and permanent mapper-pause
handling remain covered. The stalled-worker test verifies bounded outstanding
work and the 0.5 s cached-source stop.

The final live slalom's first 60 s rate probe passed every check: 5 Hz map
snapshots, 10 Hz commands, 0.110 s maximum command gap, 3.83 grid builds/s,
11.4 ms supervisor tick p99, and no worker-backlog stops in that window.
Active global/local costmap update settings were 2/10 Hz, publication 1/1 Hz.
Evidence: `Simulation/logs/nav-rate-validation/final-slalom-rates.json`.

**Before pose timing hardening, full-course acceptance did not pass.** Session `navigation-20261021-205903`
cleared the entry gate and first turn, then at 147.3 s hit the existing mapper
pose-discontinuity fault: `dt=0.000446s`, zero translation, `turn=0.001834rad`.
The supervisor latched the fault, commands stopped, and HOLD/disarm was verified.
The evaluator reported no clearance violation. Its underlying pose/timestamp
cause remains unresolved; no fault threshold was weakened. Results must not be
reported as a successful full slalom or as Jetson acceptance.

The default-speed live gate result below validates the same background-worker
architecture before the geometry-equivalent sparse-sector optimization. A
successful full course was still required at this stage. The pose timing section
above records the later passing run; broader repeatability remains untested.

### Background-worker validation before sparse sector optimization

- Static Simulation validation, 38 autonomy unit tests and 5 command-bridge
  tests passed.
- Real Nav2 detour and 3 m gate fixtures passed with minimum hull clearance
  1.202 m and 0.452 m. Tests cover stale snapshots, new blocking walls, recovery,
  map-session reset, and permanent mapper pause without later resumption.
  The blocked-route fixture observes the injected wall in the planning grid
  and requires a sustained stop within its original 8 s reaction budget.
- Live default-speed gate passed in 96.6 s, minimum conservative clearance
  0.227 m, whole-stern exit 0.698 m, both cameras contributed, HOLD/disarm verified.
  Session `navigation-20261021-204623`.
- The 60 s gate probe passed: occupancy 5.00 Hz, gated commands 10.00 Hz,
  maximum command gap 0.109 s, supervisor tick p99 12.7 ms. The initial full-slalom
  probe also passed: commands 10.00 Hz, maximum gap 0.118 s, tick p99 14.1 ms,
  grid builds 3.86/s. Evidence: `worker-gate-rates.json` and
  `worker-slalom-rates.json` in `Simulation/logs/nav-rate-validation/`.

These measurements are from the simulation PC, with RViz/recording closed.
They do not establish Jetson deadlines or repeatability across seeds/water.

The heavier turn-2/turn-3 probe kept 10.00 Hz commands with a 0.116 s maximum
gap and 14.8 ms tick p99, but worker builds reached 296 ms and triggered backlog
stops. A 30 s performance window measured 0.748 RTF, below its 0.8 target.
Session `navigation-20261021-204940` then reached the exit gate but latched the
known mapper pose-discontinuity fault (`dt=0.000680s`, translation `0.020760m`)
at 432.6 s and verified HOLD/disarm. It did not pass the full course; no clearance
violation was reported. Fault thresholds were unchanged.

This led to sparse unresolved-bearing evaluation: conservative ray-cone bounds
select candidate cells before applying the original angular cost formula. The
39-unit-test suite includes exact grid comparisons across heading wrap, narrow
and wide uncertainty, and graded/hard modes. A host benchmark on the default
planning extent with eight metric obstacles produced identical grids while
reducing median build time from 59/119/305 ms to 24/40/89 ms for 4/12/32 bearings.
Evidence: `Simulation/logs/nav-rate-validation/grid-benchmark.json`. This is a
focused numerical benchmark, not an end-to-end or Jetson speedup claim.

### Earlier synchronous candidate (superseded)

- `make -C Simulation validate`: passed.
- 37 autonomy unit tests and 5 simulation command-bridge tests: passed.
- Real Nav2 detour and 3 m gate fixtures: passed with 5 Hz source snapshots;
  minimum hull clearance 1.163 m and 0.452 m respectively. Duplicate/stale-map
  stopping and recovery, new blocking obstacles, session-reset faults, cached
  geometry reuse, and permanent mapper-pause/no-resume behavior passed.
- Live default-speed dual-camera gate: passed in 104.4 s, minimum conservative
  clearance 0.198 m, whole-stern exit 0.681 m, both cameras contributed, and
  HOLD/disarm verified. Session `navigation-20261021-184730`.
- A 60 s live rate probe measured 5.00 Hz map snapshots, 10.00 Hz gated commands,
  and 3.82 planning-grid builds/s under the 5 Hz cap. Active parameters matched
  global/local update rates 2/10 Hz and publication rates 1/1 Hz. Supervisor tick
  p95/p99 were 44.3/60.9 ms on the simulation PC; maximum command gap was 0.195 s.
  Evidence: `Simulation/logs/nav-rate-validation/gate-rates.json`.
- A 30 s simulation performance window passed its 0.8 minimum real-time factor
  requirement at 0.813, with no clock rewind. This is not a controlled CPU
  speedup comparison. Evidence: `Simulation/logs/nav-rate-performance.log`.

The first scheduler candidate stopped movement whenever changed geometry was
waiting for its build slot. A live probe exposed excessive stop/start commands;
that candidate was interrupted through verified HOLD/disarm and replaced by
the bounded cached-grid refresh described above. Its evidence is retained in
`Simulation/logs/nav-rate-validation/first-scheduler/` and session
`navigation-20261021-184307`; it is not a completed acceptance run.

The next synchronous candidate passed the gate above but full-slalom profiling
found 150-220 ms grid builds blocking the supervisor and a 317 ms command gap.
Session `navigation-20261021-185107` was stopped through verified HOLD/disarm.
That result led to the background worker and 0.5 s backlog stop described above;
the synchronous timing results are not acceptance evidence for the final worker.
Saved probe evidence is `Simulation/logs/nav-rate-validation/synchronous-scheduler/`.

## First live trials, 2026-10-18

Both used dual RGB cameras, calm water, NVIDIA rendering and 15 Hz capture,
with graded uncertainty and the independent conservative hull-clearance judge.
RViz was closed for both. Session elapsed time below is the bridge's wall timer;
the runner's total also includes discovery and shutdown.

| Trial | Outcome | Session elapsed | Minimum clearance | Stern exit |
| --- | --- | --- | --- | --- |
| Default 0.20 m/s | Failed: mapper pose-discontinuity pause | 252 s at shutdown | 0.178 m | Not cleared |
| Opt-in 0.35 m/s | Passed; HOLD/disarm verified | 75.2 s | 0.189 m | 0.659 m |

Evidence: `Simulation/logs/navigation-20261018-134036/` and
`navigation-20261018-134630/`. This is not a controlled speedup claim: the
baseline failed, and the earlier successful 0.20 m/s run had different monitoring
load. The speed override remains experimental.

The same opt-in profile also passed one full eight-buoy slalom in session
`Simulation/logs/navigation-20261018-134949/`: entry gate, all four alternating
turns, and exit gate. Session elapsed time was 518.3 s (531.2 s including runner
startup/shutdown); minimum conservative hull clearance was 0.484 m, and whole
stern exit clearance was 0.475 m. Both cameras contributed to the shared map,
the judge reported no envelope violation, and HOLD/disarm was verified.
Brief map-progress timeouts stopped commands and recovered once inputs resumed.
This establishes one successful course run, not repeatability across seeds,
water conditions, or competing workloads.

A 20 s measurement during turn 4 gave a real-time factor of 0.802 with all
received navigation samples reporting path following, no clock rewind and a
maximum clock delivery gap of 0.016 s. See
`Simulation/logs/navigation-experiment-slalom-performance.log`. This run did
not include RViz or recording.

The failed baseline exposed a separate reliability problem: navigation waited
indefinitely for a mapper pause that requires a session restart. The experiment
now latches a terminal fault with the mapper's cause, so the command bridge can
HOLD/disarm. A live Nav2 test in isolated ROS domain 96 passed an injected
permanent mapper pause and verified that subsequent healthy-looking snapshots
cannot resume motion. Pose discontinuity diagnostics now include the measured
time, translation and rotation deltas; the rejection thresholds are unchanged.

Validation passed: `make -C Simulation validate`, 34 autonomy unit tests,
4 pose timing tests, 5 bridge tests, and the isolated live Nav2 mapper-pause test.
The controlled baseline failure remains a documented limitation: its underlying
pose discontinuity was not reproduced with the added delta diagnostic, so its
root cause is still unproven.
