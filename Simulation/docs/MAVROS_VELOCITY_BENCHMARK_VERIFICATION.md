# MAVROS velocity benchmark verification

Date: 2026-10-04. Revision under test: `4ff89fb9601a74c2433f28c62a1d6cd0956ea21d`
on local `Pre_Implementation`, fast-forwarded from `aeeb532` to
`codex/mavros-velocity-benchmark`. The checklist reconciliation is a subsequent
documentation-only change.

## Scope and behavior

The simulation evaluator now sends `geometry_msgs/TwistStamped` to
`/mavros/setpoint_velocity/cmd_vel`, observes GUIDED, publishes zero-velocity
setpoints for three seconds, and retries arming through the SITL startup race.
It commands 0.5 m/s on ROS ENU x for three seconds, then zero velocity. Acceptance
requires at least 0.10 m ground-truth displacement, speed settling to at most
0.10 m/s, observed HOLD, and observed disarm. Exit cleanup attempts bounded
zero-velocity publication and disarm if the test armed the boat. Existing
simulation-only and SITL-transport guards remain enabled.

This report supersedes the failed RC-command benchmark result in the
[September integration report](PRE_IMPLEMENTATION_MIGRATION_VERIFICATION.md)
for command acceptance only. It does not supersede its RGB-D failure or establish
hardware or autonomy readiness.

## Configuration

- Existing local Docker simulator, Adapter, and bootstrap images; no new clean
  Adapter/autonomy rebuild in this run.
- `SCENARIO=one make run`; the launcher selected the GPU Compose overlay on the
  host. ROS Jazzy, Gazebo Harmonic, ROS domain 0.
- Simulator image: `ardupilot-blueboat:4.7.0`.
- Adapter image: `maritime-sim-adapter:jazzy`; sole SITL endpoint `udp://:14552@`.
- Autonomy image: `maritime-autonomy:jazzy`, approved simulation-only bootstrap.
- Rebuilt evaluation image: `maritime-sim-evaluation:jazzy`, image ID
  `sha256:e584f0ca3ec41f9109f180490fdf436a546c998e7d568f0ea7be100518969234`.
- Runtime logs are ignored files under `Simulation/logs/`.

## Results

| Check | Result and evidence |
| --- | --- |
| `make validate` before the build | PASS, including Docker-backed `gz sdf -k` validation. |
| `docker compose -f container/compose.yaml --profile ros --profile evaluation build evaluation` | PASS; rebuilt the evaluator package from the integrated sources, reusing unchanged dependency layers. |
| `python3 -m unittest discover -s tests -v` | PASS, 3 Compose boundary tests. |
| `python3 -m unittest discover -s Simulation/tests -p 'test_*.py' -v` | PASS, 9 scenario tests. |
| `python3 -m unittest discover -s Simulation/tests/evaluation -p 'test_*.py' -v` | PASS, 18 Adapter/evaluator contract tests. |
| `python3 -m unittest discover -s autonomy/tests -p 'test_*.py' -v` | PASS, 4 bootstrap boundary tests. |
| `docker exec ardupilot-blueboat-sim gz model --list` | PASS: live `water_surface`, `blueboat`, and `buoy_0`; simulator log reports ArduPilot Ready. |
| `make mavros-smoke` | PASS, exit 0; `benchmark-validation-smoke.log`. |
| `make boundary-smoke` | PASS, exit 0; `benchmark-validation-boundary.log`: public camera/FCU data, generic camera TF, and exclusion of truth from shared navigation TF. This probe runs in the evaluator, not a real autonomy application. |

The live command result was:

```text
MAVROS PASS: connected telemetry, GUIDED velocity command, zero-velocity stop, motion, HOLD, and disarm verified
```

Launch output: `benchmark-validation-run.log`. Command and boundary tests ran
before shutdown at approximately 2026-10-04T21:48Z. The benchmark log records the
semantic pass, not numerical displacement samples or throughput measurements.

## Regression and cleanup

`make verify-rgbd` was run from a stopped stack and exited 2 in the `one`
scenario: the Gazebo source check passed with 120 exact timestamp pairs at
30.30 Hz simulated cadence, but `sensor_smoke` measured **3.44 Hz**, below the
unchanged **8.00 Hz** minimum. The suite stopped there; gate, multi, its internal
MAVROS smoke, and original-control regression were not reached. The separate
live velocity smoke above passed before this suite. No RGB-D code, settings,
thresholds, or lifecycle code were changed. Evidence:
`logs/benchmark-validation-rgbd.log` and `logs/verify-one.log`.

The first regression launch overlapped the earlier benchmark shutdown and was
invalid; both wrappers were stopped and the recorded final regression was rerun
from an empty Compose project. Final cleanup at 2026-10-04T21:51:36Z showed an
empty `docker compose -f container/compose.yaml --profile ros --profile evaluation
ps -a`, no remaining launch wrappers, and retained nonempty `logs/mav.parm`.
No matching ArduRover/MAVProxy/Gazebo/Adapter launch processes or UDP listeners
on 14550/14551/14552/9002 remained. One Xauthority file created by this run was
left behind by the interrupted wrapper and was removed explicitly. This is
cleanup evidence for this run, not a claim that all lifecycle failure modes pass.
Hardware, real perception/state/mapping, live repeated-category mapping, lifecycle
failure injection, and branch/worktree cleanup are outside this change.

## Checklist evidence

The reconciled [checklist](../../docs/Things_To_Fix_Before_Implementation.md)
marks implemented contracts, relocation, Adapter ownership, evaluation isolation,
normalized public interfaces, renderer/entity changes, category assets, bootstrap
separation, dependency checks, and updated operational ownership guidance complete.
Source and unit-test evidence support implementation claims; the September report
supplies prior clean-build/GeographicLib evidence. This run supplies current static,
command, and public-boundary evidence. Partial multi-requirement items remain
unchecked rather than treating implementation as full runtime acceptance.

Final documentation checks: `git diff --check` passed; local Markdown links in
the checklist and this report resolve. Generated logs remain ignored.
