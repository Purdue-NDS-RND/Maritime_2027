# Simulation pre-implementation final verification

Date: 2026-10-04 local / 2026-10-05 UTC. Branch: `Pre_Implementation`.

This report covers the simulation foundation and approved non-commanding
bootstrap. Hardware deployment and real perception, state interpolation,
mapping, and mission readiness remain deferred. It supersedes the open simulation
acceptance gaps in the [original migration report](PRE_IMPLEMENTATION_MIGRATION_VERIFICATION.md)
without changing that report's historical results.

## Revisions and changes

The full RGB-D regression ran at `645bd4f`. Lifecycle acceptance revision is
recorded with the completed results below;
the intervening commits add service-exit cases, source ownership tests, static
scenario validation, and documentation without changing the runtime images.

- Startup now renders a fresh manifest, verifies advancing Gazebo time and
  SITL, waits for Adapter camera/calibration/TF/FCU readiness, and finally starts
  the explicitly named simulation bootstrap. Each handoff has a bounded timeout
  and captures failure evidence.
- The launcher supervises required services throughout the run. Child exits,
  sustained source failures, failed startup, INT/TERM, and `make down` converge
  on full-stack cleanup. A launcher lock rejects a duplicate start before it
  can replace the running scenario or its display authorization.
- Every run records a unique identity, resolved Compose configuration and
  SHA-256, and service logs under `logs/runs/`; ROS runs also save the rendered
  manifest. These records
  distinguish retained FCU parameters from the bootstrap's empty application
  state. They do not implement a map or a persisted application session.
- Repeated-category rendering and live evaluation cover two visible red buoys
  with independent entity identities and truth topics. Truth remains confined
  to explicit simulation evaluation.

Stricter live checks found and corrected three implementation problems:

1. ROS GetParameters replies carry `response.values`; they are not iterable
   Python Parameters. Diagnostics now converts actual parameter values and
   rejects missing, pending, failed, or mismatched evidence.
2. A forced MAVROS name collapsed loader, router, and UAS nodes into duplicate
   `/mavros` names. Their internal names now remain distinct. The pinned dynamic
   plugin implementation ignores global parameter files, so a supervised
   configurator applies canonical settings once through the correct owners'
   services. Diagnostics independently verifies effective values.
3. Jazzy diagnostic severity is a byte field. Boundary acceptance now normalizes
   it before comparing severity, with a real ROS serialization regression.

The corrected [MAVROS contract](../../docs/contracts/mavros_adapter_contract.md)
is **2.0.0**. Unsupported `timesync_avg_alpha`/`tf.send_fcu` settings were
removed; supported filter gains explicitly freeze the pinned upstream defaults.
They are not claimed equivalent to the former unsupported `0.6` alias. Public
ROS interfaces, source/target IDs, UDP 14552, and disabled dynamic motion TF are
preserved. The camera contract stays **1.0.0**: exact matching (0 ns), maximum
acquisition age 100 ms, and maximum arrival silence 2 s are unchanged. The
evaluator's separate 8 Hz acceptance gate is also unchanged.

## Static checks and builds

`make validate` passed from `Simulation/`, including ordinary/seeded rendering
and Gazebo SDF checks for `one`, `gate`, `multi`, and `repeated_red`.

The four host test suites passed **67 tests**, with **2 explicit ROS-dependent
skips**. Both skipped behaviors were subsequently executed successfully against
actual ROS: configurator construction and DiagnosticStatus serialization. The
Adapter ownership/response suites additionally passed 21 tests in the built
Adapter image. Source checks are architecture evidence, not runtime acceptance.

Commands:

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s Simulation/tests -p 'test_*.py' -v
python3 -m unittest discover -s Simulation/tests/evaluation -v
python3 -m unittest discover -s autonomy/tests -v
```

Clean Adapter and autonomy dependency builds passed; the Adapter was rebuilt
again after the live-discovered source fixes. Simulator and evaluation builds
also passed. Actual image inspection confirms pinned MAVROS/MAVROS Extras,
GeographicLib tools and nonempty `egm96-5.pgm` in Adapter, and only the neutral
bootstrap package among project/MAVROS/Gazebo packages in autonomy.

| Component | Verified version / revision |
|---|---|
| ROS / OS | Jazzy / Ubuntu Noble |
| MAVROS | `2.15.1-1noble.20260903.022619` |
| MAVROS Extras | `2.15.1-1noble.20260903.025450` |
| GeographicLib tools | `2.3-1build1`, EGM96-5 dataset present |
| Gazebo Sim | `8.15.0` |
| ArduPilot | Rover 4.7.0, `1511f27194f1dcc3728270883047bdf022b3fd53` |
| ArduPilot Gazebo plugin | `082a0fe231f6e63bc8d1598f1cba461d9e2ea7f5` |

The running simulator image is `ardupilot-blueboat:4.7.0`. No upstream
revisions, boat dynamics, or MAVLink ports were changed.

| Image | Tested image ID |
|---|---|
| `maritime-sim-adapter:jazzy` | `sha256:7326e91202f7741a9b34276ee16ea7b8626e712abe4597c113d0b43348e57a02` |
| `maritime-autonomy:jazzy` | `sha256:cf8ddf8ce370cdf6e048665652031fa962c5d0293e80921367897b1e18df6922` |
| `maritime-sim-evaluation:jazzy` | `sha256:f917a887da702f96057f585892d6e330b158031b2153c6765642154a21dfc860` |
| `ardupilot-blueboat:4.7.0` | `sha256:d4e6d5b2cfc9b9b65bc47fb9b0631f3cacdecfcb09754f7ab6ea2c4ce72af96a` |

## Full live regression

`make verify-rgbd` passed, including cleanup between each scenario.
Throughput rates below use simulated acquisition timestamps; they are not
wall-clock rates. Gazebo callback cadence is recorded separately in the logs.

| Case | Semantic result |
|---|---|
| `one` | Gazebo exact pairs; 100 ROS exact triples at **30.30 Hz**; depth, calibration, TF and entity truth checks passed. |
| Boundary evaluator | 19 exact triples, decoded connected MAVROS State, fresh source/FCU diagnostics, public TF, truth isolation, and non-commanding bootstrap passed. |
| MAVROS velocity benchmark | Connected telemetry, GUIDED velocity motion, zero-velocity stop, HOLD, and disarm passed. |
| `gate` | Gazebo exact pairs; 100 ROS exact triples at **30.30 Hz**; both entities verified. |
| `multi`, seed 42 | Live entity query verified all four rendered buoy identities. This case is not a claim of all-four-camera detection or mapping. |
| `repeated_red` | Gazebo exact pairs; 100 ROS exact triples at **28.85 Hz**; both visible same-category entities independently evaluated. |
| Camera-only original control | Required parameters, GUIDED target travel, HOLD speed settling, RTL return, and observed disarm smoke passed. |

A separate probe ran **inside the actual autonomy container**: exact RGB-D
triples, fresh FCU diagnostics, MAVROS State graph type, public camera TF, and
bootstrap truth/command isolation passed. Direct State decoding is evidenced by
the evaluator; the bootstrap has no need for a MAVROS message dependency or real
state subscription. Mission readiness remained false throughout these checks.

An unmodified public color frame was captured and visually inspected:
`logs/preimpl-live-camera-one.png` (1280×720, `rgb8`,
`camera_0_optical_frame`, acquisition stamp `124.939000000`). It shows the expected
white category buoy and marker. Visual evidence complements the numerical
depth/calibration assertions; it does not establish mapping success.

## Lifecycle acceptance

Six cases from the local 11-case lifecycle suite passed. Each completed case
verified that the launcher returned failure where expected and left no project
containers, reserved simulator ports, or temporary Xauthority file:

| Case | Result | Elapsed |
|---|---|---:|
| Missing Gazebo camera at startup | Bounded failure and cleanup | 15.9 s |
| Disconnected FCU during Adapter startup | Bounded failure and cleanup | 92.7 s |
| Simulator service exit | Whole-stack failure and cleanup | 74.0 s |
| Adapter camera child exit | Whole-stack failure and cleanup | 67.4 s |
| Autonomy service exit | Whole-stack failure and cleanup | 80.5 s |
| Camera source silence | Stale readiness rejected; whole-stack cleanup | 240.7 s |

FCU silence, INT, TERM, duplicate start, and parameter retention/reset were not
run. The suite was stopped after case six to cap the extra validation. Those
checks remain unchecked in the checklist.

## Branch and worktree cleanup

All 12 superseded local `codex/*` branches were audited before deletion. Their
patches were integrated or superseded; their complete history and original refs
are recoverable from the verified local bundle
`logs/cleanup-2026-10-05/superseded-branches.bundle` and `branches.txt`.
Five worktree registrations pointing to missing `/tmp` directories were pruned.
The only remaining checkout is the project root; local branches are
`Pre_Implementation` and `main`.

The obsolete remote `codex/preimpl-task06` branch was deleted using a lease
against its verified current SHA. The unrelated remote `teleop` branch was
preserved. No merge into `main` or code push was part of this finalization.
Generated logs, archives, frames and EEPROM remain ignored local artifacts.

## Evidence and deferred acceptance

Primary local artifacts (under `Simulation/`):

- `logs/preimpl-final-validate.log`
- `logs/preimpl-final-clean-build.log`, `logs/preimpl-adapter-final-build.log`
- `logs/preimpl-real-ros-tests.log`, `logs/preimpl-real-diagnostic-byte-tests.log`
- `logs/preimpl-final-rgbd.log`, `logs/verify-*.log`, `logs/verify-*-models.txt`
- `logs/preimpl-autonomy-boundary-debug.log`, `logs/preimpl-frame-capture.log`
- `logs/preimpl-final-lifecycle.log`,
  `logs/lifecycle-20261005T032747Z/results.json` (six completed cases)
- `logs/preimpl-final-*-packages.txt`, `logs/preimpl-final-image-ids.txt`,
  `logs/preimpl-final-simulator-versions.txt`
- `logs/runs/*/{identity.txt,compose.yaml,scenario.manifest.json,services.log,failure.log}`

The [reconciled checklist](../../docs/Things_To_Fix_Before_Implementation.md)
leaves hardware implementation, real camera-roster consumers, explicit camera/
FCU clock correlation and state interpolation, fresh map state, actual category
association, and the manually piloted mapping acceptance run unchecked.
Pause/reset and partial-stack recovery remain unsupported. The simulation
foundation does not claim vessel or mission readiness.
