# Pre-implementation migration verification

**Run:** 2026-09-15T04:54:09Z  
**Revision under test:** `c0c470cf333dcc47a79e9850564bf5f63c8829c4` plus the uncommitted diagnostics and evaluator-invocation repairs recorded below.  
**Environment:** local Ubuntu host, Docker, ROS Jazzy/Noble, Gazebo Harmonic, software rendering, `SCENARIO=one`, ROS domain 0. Hardware Adapter and hardware tests were deliberately deferred and were not built or run.

## Configuration under test

- Simulation Adapter: `maritime-sim-adapter:jazzy`; FCU endpoint `udp://:14552@`; MAVLink v2, source system 255, target 1/1, root `/mavros`.
- Simulator: `ardupilot-blueboat:4.7.0`; SITL output remained UDP 14552.
- Autonomy: the explicitly named simulation-only bootstrap placeholder with `ADAPTER_ENVIRONMENT=simulation` and `MARITIME_PREIMPLEMENTATION_PLACEHOLDER=1`; mission readiness is false and it is not autonomy, perception, mapping, navigation, or vessel-readiness evidence.
- Public camera surface: `/sensors/camera_0/color/image_raw`, `/sensors/camera_0/depth/image_rect_raw`, and `/sensors/camera_0/color/camera_info`; expected frame chain is `base_link -> camera_0_link -> camera_0_optical_frame`.

## Build and static evidence

| Result | Evidence |
| --- | --- |
| PASS | `make validate` from `Simulation/`: scenario rendering, camera/buoy structure, and Docker-backed Gazebo SDF validation passed. |
| PASS | Clean-layer `docker compose -f container/compose.yaml --profile ros build --no-cache adapter autonomy`: Adapter rebuilt its three packages; autonomy rebuilt only `maritime_bringup`. |
| PASS | Adapter clean layer installed `ros-jazzy-mavros 2.15.1-1noble.20260903.022619`, `ros-jazzy-mavros-extras 2.15.1-1noble.20260903.025450`, and verified `/usr/share/GeographicLib/geoids/egm96-5.pgm`. |
| PASS | Focused suites: root Compose boundaries 3/3, Simulation scenario renderer 9/9, Simulation Adapter contracts 18/18, and bootstrap boundary 4/4. |
| DEFERRED | Hardware Adapter image, transport, cameras, timing evidence, and hardware tests were not built or verified. |

## Live simulation evidence

`SOFTWARE_RENDERING=1 SCENARIO=one make run` created the RGB-D scenario, started Gazebo/SITL, observed the FCU heartbeat through the Simulation Adapter, and reached healthy simulator, Adapter, and bootstrap containers. The Adapter passively observed MAVLink v2 on the dedicated SITL path. The public boundary smoke passed:

```
BOUNDARY PASS: public camera and FCU data are present; truth TF is excluded from shared navigation TF
```

Two launch-time defects were found and repaired before the successful health gate: the diagnostics node wrote its command-client map to the read-only ROS `Node.clients` property, and it used the pre-Jazzy `AsyncParameterClient.service_is_ready()` name. The implementation now uses `command_clients` and `services_are_ready()`, with a focused contract test.

Evaluator targets also now use `--no-deps`. Without that flag, `docker compose run` recreated the running RGB-D scenario using default Compose environment values (`WORLD=blueboat_waves.sdf`, `CAMERA_ENABLED=0`), making the test invalid. The corrected targets attach only to an already-running selected scenario.

### Acceptance failures retained

| Result | Command / observation |
| --- | --- |
| FAIL | RGB-D evaluator against the correctly running scenario received only 24 exact RGB/depth/CameraInfo triples in its 45-second window; it failed before the unchanged 8.00 Hz requirement could be met. The source was active, but Adapter diagnostics reported rejected unmatched color anchors. The 8.00 Hz minimum was not reduced. |
| FAIL | `make mavros-smoke` connected, reached MANUAL, armed, issued its bounded RC pulse, and attempted neutral/release/disarm cleanup, but did not observe 0.10 m ground-truth motion within 8 seconds. It therefore failed rather than claiming command acceptance. |
| PASS | `make boundary-smoke` verified public camera/MAVROS data and excluded ground-truth TF from the shared navigation TF tree. |
| BLOCKED | No real perception/state/mapping application exists. The manually piloted repeated-category mapping acceptance run is not applicable until that stated prerequisite exists. |

Relevant generated artifacts and retained SITL state are under `Simulation/logs/`, including `generated-worlds/active.sdf`, `generated-worlds/active.manifest.json`, and `mav.parm`. They are runtime outputs and are not committed.

## Checklist matrix

| Checklist section | Status | Evidence / remaining condition |
| --- | --- | --- |
| 1. Freeze Adapter contracts | PASS (simulation contracts) | Versioned MAVROS, camera, and scenario contract suites pass; hardware application remains deferred. |
| 2. Move MAVROS | PARTIAL | Simulation Adapter ownership and bootstrap separation build and launch; Hardware Adapter is deferred. |
| 3. Isolate evaluation | PASS (static/boundary) | Evaluator is explicit and simulation-guarded; command acceptance is separately failed above. |
| 4. Normalize camera boundary | FAIL | Public names/frames pass, but live synchronized RGB-D throughput does not meet acceptance. |
| 5. Repeated-category scenarios | PASS (static) | Renderer/manifest tests pass; no mapping application exists for live mapping acceptance. |
| 6. Category assets | PASS (static) | Asset/category validation passes. |
| 7. Bringup/readiness/persistence/shutdown | PARTIAL | Liveness, FCU, truth isolation, retained SITL state, and shutdown pass; RGB-D and movement acceptance fail. |
| 8. Boundary/acceptance tests | PARTIAL | Static and public-boundary tests pass; RGB-D and command movement acceptance fail. |
| 9. Operational guidance | PASS | Documentation reflects Simulation Adapter ownership, deferred hardware, and bootstrap limits. |
| 10. Final integration verification | FAIL | This report records the prerequisite-satisfied RGB-D and movement failures; the migration is not complete. |

No checklist box was marked complete by this run: the checklist remains conservative until every prerequisite-satisfied acceptance item passes.

## Cleanup

`make down` removed simulator, Adapter, autonomy, and temporary evaluator containers while retaining `Simulation/logs/` and SITL parameter state. A subsequent `docker compose -f container/compose.yaml ps -a` was empty; no matching `ardupilot-blueboat` or `maritime-` containers remained. The final Git status/diff check is recorded with the scoped repairs below.
