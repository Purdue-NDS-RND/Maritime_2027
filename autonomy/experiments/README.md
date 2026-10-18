# Navigation experiments

These experiments live on `experiment/nav2-course-tuning`. Performance fixes
are integrated separately into `main`; navigation is not merged there.

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
