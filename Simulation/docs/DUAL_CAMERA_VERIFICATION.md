# Camera boat verification

Validation was performed on 2026-10-17 on `feature/dual-camera-boat`.
This is simulation/software evidence, not hardware or mission acceptance.
The RGB-only mapper's estimation equations and thresholds were unchanged.

| Check | Evidence | Result |
| --- | --- | --- |
| Source, Compose, SDF and dynamics-preserving payload checks | `logs/dual-camera-final-validate.log`; 4 model tests | PASS |
| Menu and explicit launch bypass | 11 `test_run_menu.py` tests | PASS |
| Adapter contract, including both yaw signs and camera-parent rejection | 21 `test_task06_contract.py` tests | PASS |
| RGB-only mapping/replay, dual-view shared track, legacy single-camera inputs | `logs/dual-camera-final-benchmark-tests.log`, 63 tests | PASS |
| Final roster-based launch without image discovery, duplicate roster rejection | `logs/dual-camera-roster-tests.log`, 2 tests | PASS |
| Real MCAP single/dual recordings, missing second camera rejection | `logs/dual-camera-final-recording-tests.log`, 12 tests | PASS |
| Live mapping clock, viewer and legacy launch | `logs/dual-camera-live-tools-tests.log`, 9 tests | PASS |
| Monitor launcher/configuration | `logs/dual-camera-monitor-validate.log` | PASS |
| Full forward-camera RGB-D, scene, MAVROS and control regression | `BOAT_MODEL=single SIM_IMAGE=ardupilot-blueboat:dual-camera make verify-rgbd`; `logs/dual-camera-single-regression.log` | PASS |
| Shared RViz preset with single camera | `logs/dual-camera-single-rviz-probe.log` | PASS |
| Shared RViz preset with dual camera | `logs/dual-camera-rviz-probe.log` | PASS |
| Dual gate RGB-D, mount transforms and side-marker visibility | `logs/dual-camera-sensor-smoke.log` | PASS: camera_0 16.17 Hz, camera_1 14.39 Hz |
| Dual boat GUIDED travel, HOLD, RTL and disarm | `logs/dual-camera-control-smoke.log` | PASS |
| Live shared map under boat motion | `logs/dual-camera-live-mapping-probe.json` | PASS: 526 assembled arrays, confirmed track with both source cameras |
| Moving dual capture and RGB-only replay | `logs/dual-camera-moving-clean.log`; `logs/dual-camera-moving-replay.log` | PASS: 19.76/10.75 Hz recorded RGB-D; 514 replay arrays, 505 assembled inputs, 4 XY updates |
| Lifecycle acceptance | `logs/dual-camera-lifecycle.log`, `logs/dual-camera-lifecycle-followup.log`, `logs/dual-camera-lifecycle-combined.json` | PASS: all 11 cases across the initial run and targeted follow-up |
| Final installed Adapter roster to common live pipeline | `logs/dual-camera-final-gate-smoke.log`, `logs/dual-camera-final-mapping-probe.json` | PASS: 30.30/30.07 Hz with mapping active; 449 assembled frames, detections from both cameras, one mapper |
| Dual camera in direct harsh-water harbor | `logs/dual-camera-harbor-smoke.log`; generated world/manifest assertions | PASS: both 30.30 Hz; harbor pose y=3 m and 0.25 m waves preserved |

Rates above use acquisition timestamps in simulated time, matching the existing
8 Hz exact RGB-D gate. All successful runtime claims inspect data/TF/control
semantics, not only container health. RViz probes check the calibrated planes,
frusta, private TF, native camera subscription and static-TF cache recovery.

The dual synthetic fixture projects one known buoy into two RGB views at the
actual -45/+45 degree orientations. The normal detectors and single mapper
produce one confirmed track near the known position with both source cameras.
It supplies neither depth nor truth to the mapper. The moving real recording
also produces map/scatter/history artifacts; its final track becomes stale when
the buoy leaves view. Those positions are software outputs, not independent
accuracy measurements. Clock recovery retains the existing recorded-reference
alignment and provisional timing uncertainty assumptions.

The final simulator test image `ardupilot-blueboat:dual-camera` reuses the
installed pinned ArduPilot/Gazebo/wave binaries and rebuilds the changed payloads
and scripts. All four source-pin labels and the upstream boat SDF SHA-256
`fc651a9d4aff258fe675d94aeb24b91d82439cc441f99b00f921e316fbc3de57`
were verified. The structural audit removes the added visuals/sensors and
compares the entire remaining boat XML with that source. Adapter, autonomy,
Monitor and mapping tools were rebuilt. The normal simulator Dockerfile contains
both model-generation steps for a future complete build; the broad base-image
rebuild was stopped after a cache miss to avoid rebuilding unchanged toolchains.

A combined live mapping + RViz + control + full recorder trial failed the saved
second-camera exact-triple gate (2.56 Hz); its failed quality report remains in
`logs/recordings/dual-camera-gate-validation/`. Isolated recording passed both
streams, and the moving clean capture passed while retaining reported transport
losses. This does not certify loss-free or arbitrary-load recording. Use the
capture-then-replay workflow and inspect each camera's saved quality summary.
No rate, timing, estimator or acceptance thresholds were relaxed.

The initial lifecycle run passed nine cases, then its autonomy-container boundary
probe failed before the double-start assertion. That harness previously discarded
the failing probe output. It now saves stdout/stderr before asserting the same
return code and semantic PASS marker. The targeted rerun passed with 49 exact
RGB-D triples and preserved the active stack on a rejected second launch.
Parameter retention, explicit wipe, and original EEPROM restoration also passed.
The initial failure remains recorded; no production behavior or acceptance
threshold was changed to obtain the follow-up result.

The validated local simulator image is also tagged `ardupilot-blueboat:4.7.0`,
so the standard launch command reuses the tested assets. The previous image is
preserved as `ardupilot-blueboat:pre-dual-camera-20261017`; tagging adds no copy
of its layers. No image or cache cleanup was performed.
