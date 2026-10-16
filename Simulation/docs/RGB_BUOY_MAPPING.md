# RGB-only persistent buoy mapping

This implements the bearing-only version of `Maritime_Buoy_Localization_Final_Report.pdf`:
2D detections → calibrated world bearings → robust multi-view initialization →
persistent per-buoy XY EKFs. It starts with an empty map each session. No depth,
marker dimensions, ArUco pose/PnP, known buoy positions, or simulator truth enter
the mapper. MAVROS vessel poses provide metric motion, position, and attitude;
camera intrinsics and mounting TF are still required. This is landmark mapping
with externally supplied boat pose, not monocular visual odometry or SLAM.

## Use it

From `Simulation/`:

```bash
make benchmark-build
make benchmark RECORDING=Sample_1 METHOD=rgb_mapping
```

RGB mapping is the default for `make benchmark` and the shared pipeline launch on
this branch. The earlier methods require an explicit `METHOD`.

Or run `make record`, browse a recording, select **Run ROS localization benchmark**,
then **RGB persistent map**. The benchmark starts the same detector and mapper
used live, plays only RGB/calibration/odometry/static-TF inputs, records results,
and exports them. A source bag with no depth topic is supported and tested.

**Timing matters for this method.** Unlike the earlier experimental baselines,
this mapper interpolates vessel pose at image acquisition time. Camera and pose
stamps must share a clock, or have an independently established constant offset:

```bash
make benchmark RECORDING=your_run METHOD=rgb_mapping POSE_TIME_OFFSET_S=-123.5
```

The convention is **pose source stamp + offset = image stamp**. The example
number is illustrative. Do not copy it for `Sample_1`, infer synchronization from
callback arrival, or tune an offset to make buoy positions look correct. A
constant offset cannot repair clock drift or resets. The offset is stored in the
report and observation records; source bags and headers remain unchanged.
`Sample_1` was recorded with simulation-time images and epoch-time MAVROS poses;
zero offset cannot produce acquisition-time associations. Without a verified
clock relationship this run should report missing inputs, not a plausible map.
No Adapter/MAVROS clock settings have been changed by this implementation.

For live topics, in an environment with the autonomy ROS workspace sourced:

```bash
ros2 launch maritime_localization pipeline.launch.py method:=rgb_mapping
```

For two calibrated cameras:

```bash
ros2 launch maritime_localization pipeline.launch.py method:=rgb_mapping \
  camera:=camera_0 second_camera:=camera_1
```

For manual replay add `use_sim_time:=true` and run the bag player on the same
isolated domain. Do not start another player alongside `make benchmark`.
Optional `pose_topic:=/state/odometry` selects a project relay instead of the
current `/mavros/local_position/odom` default. Frame checks remain enforced.
`mapper_parameters:=/absolute/path/config.yaml` supplies ROS parameters; an
example is installed at `share/maritime_localization/config/rgb_mapping.yaml`.
Every `MappingSettings` field is exposed as `rgb_mapping.<field>` on the mapper.
Benchmark runs use and record the defaults.

## Files you get

`Simulation/logs/benchmarks/<recording>/rgb_mapping-<run>/` contains:

| Artifact | Meaning |
| --- | --- |
| `bag/` | Detections, accepted XY updates, semantic map, bearing/association records, costmap, markers, diagnostics |
| `final_map.json` | Latest metric records, session ID, state, covariance, evidence counts and provenance |
| `map_history.csv` | Time series of all metric records, including tentative/stale states |
| `observations.csv` | World bearings, camera origins, uncertainty, pose brackets, offset, and assignment decisions |
| `estimates.csv`, `scatter.png` | **Confirmed, newly updated** XY points for the existing benchmark interface |
| `report.json`, `summary.json`, `provenance.json` | Settings, played inputs, counters, source revision/hashes and exact image ID |
| `nodes.log`, `player.log`, `recorder.log` | Runtime evidence and errors |

A tentative map can exist before there are confirmed scatter points. Empty XY
output can mean unresolved geometry or unconfirmed identity. Inspect map states,
observations, diagnostics and `inputs_ready_arrays` rather than interpreting an
empty scatter as detector failure. Complete replay is not an accuracy pass.

## How it works

1. The existing detector publishes only box centers/extents and category labels.
   Marker IDs are category labels; repeated red buoys receive different world IDs.
2. The mapper undistorts each box center using that camera's calibration. Full
   vessel attitude and the body-to-optical mount transform rotate the ray into
   `map`; its horizontal azimuth supplies a planar bearing. No fixed buoy height
   or known camera-to-buoy distance is assumed. Near-vertical rays are rejected.
3. A bounded pose history interpolates translation and quaternion SLERP. A frame
   can wait up to 0.5 s of wall time for its enclosing poses and calibration/TF.
   The maximum pose bracket gap is 0.3 s; extrapolation is forbidden. Sixty pending
   frames and 1,000 pose samples bound memory. Delayed frames older than the last
   processed frame are explicitly rejected. No old posterior is silently updated.
4. One manager owns all cameras and IDs. It predicts wrapped bearing residuals,
   gates category and geometry, scores residual and innovation variance, and uses
   Hungarian assignment with unmatched alternatives. Competing global assignments
   within the configured cost margin are deferred. Near-track inconsistent
   observations cannot immediately create a duplicate permanent buoy. An unresolved
   tracklet stays camera-local; metric tracks can receive either camera's evidence.
5. Unresolved tracklets retain spatially/angularly diverse keyframes (at most 40,
   preserving the oldest baseline). At most twice per second per track, a robust
   `soft_l1` nonlinear angular least-squares solve starts from useful forward-ray
   intersections. It requires at least four selected views, a 1 m baseline and
   5° parallax from a useful pair, at least 75% inliers, forward ranges between
   0.3 and 80 m, residuals within 2°, information conditioning below 1,000, and
   largest initial standard deviation at most 2 m. These are experiment defaults,
   not calibrated mission acceptance limits. Weak motion stays unresolved.
6. The fit creates a **tentative** metric record once. Initialization measurements
   are consumed; the optimizer is never fused back into that filter as independent
   evidence. Three later selected, consistent bearing EKF updates confirm it.
   Joseph covariance updates, process uncertainty, pose covariance and configurable
   noise floors prevent unbounded confidence from redundant adjacent images.
7. Confirmed IDs survive occlusion. Unobserved tracks become stale after 5 s of processed image time and
   remain in the map; unresolved tracklets expire after 5 s without observation.
   Five sustained near-track contradictions mark an inconsistent track and stop
   normal updates. A coherent residual shift across at least three uniquely
   categorized mapped buoys defers the whole frame. A session restart is needed
   to recover from a latched pose/frame/calibration/clock discontinuity. If all
   image input stops, the last source-time map is retained with its original
   timestamp and a diagnostic warns after 2 s of wall time, including paused replay.

Map-session UUIDs scope `buoy-N` IDs. Tracks carry XY/full 2×2 covariance, category,
source cameras, first/last seen and last update times, raw/selected counts,
confirmation evidence and bounded source observation IDs. ArUco categories are
currently deterministic (probability 1); existence confidence is a documented
age/evidence heuristic, not a calibrated probability or learned classifier.

## ROS outputs

| Topic | Type / purpose |
| --- | --- |
| `/localization/buoys` | `BuoyEstimateArray`: confirmed fresh updates; compatibility with existing CSV/scatter |
| `/mapping/buoys` | `BuoyMap`: authoritative metric tracks, session, lifecycle, covariance; reliable transient-local |
| `/mapping/observations` | `BearingObservationArray`: source acquisition time, pose brackets and association decisions |
| `/mapping/costmap` | `OccupancyGrid`: rebuilt occupied footprints from confirmed/stale/inconsistent tracks |
| `/mapping/markers` | `MarkerArray`: world IDs, categories, lifecycle and 3σ covariance ellipses for RViz |
| `/mapping/diagnostics` | `DiagnosticArray`: input timeouts, late frames, ambiguity, initialized/confirmed counts, solver/update outcomes and latency |

The default grid is 100×100 m at 0.1 m resolution centered at the FCU map origin.
Unobserved cells remain **unknown**, occupied regions include the configured
0.35 m physical footprint and a 3σ uncertainty allowance. It is rebuilt so track
refinement leaves no ghost footprints. This grid does not establish navigable
water, dynamic obstacle coverage, or validated clearance. Mapping publishes no
boat controls and does not enable the guarded autonomy bootstrap.

## Organization and limits

Shared runtime code lives in `autonomy/ros_ws/src/maritime_localization/`:

- `bearing.py`: bearing math, robust initializer and Joseph EKF.
- `mapping.py`: one world-track manager, assignment, lifecycle and bounded history.
- `timing.py`: acquisition-time pose history and reset checks.
- `mapping_node.py`: ROS input assembly, diagnostics, semantic/map/visual outputs.
- `geometry.py`: calibration and rigid transforms shared with the earlier methods.

Replay/evaluation code stays under `Simulation/tests/evaluation/benchmarking/`.
The earlier `depth` and `triangulation` baselines remain selectable for comparison;
`rgb_mapping` never subscribes to, plays, reads or falls back to their depth input.

The report's optional historical refinement, joint pose estimation, moving-target
tracker and autonomous routing are not part of this RGB-only mapper. Physical
camera integration and on-water noise/footprint calibration remain unvalidated.
A box center approximates a buoy center; changing marker-surface offsets, tilt,
shared heading bias and clock error can bias the result. Independent landmark
EKFs do not model all pose/landmark correlations. Noise floors and conservative
pose inflation help, but do not prove covariance calibration. Persistent same-color
occlusion/alignment can remain ambiguous, and a bounded track capacity may require
a new session. The mapper detects abrupt pose resets with speed/turn
bounds; a smooth unannounced origin shift cannot be reliably distinguished from
real vessel motion using this interface alone.

## Verification

```bash
make validate
make benchmark-build
make benchmark-test
python3 -m unittest discover -s tests -p test_recording_menu.py -v
```

The end-to-end RGB test creates a bag containing RGB, calibration, a moving vessel
pose and mounting TF **with no depth topic**, launches the production detector and
mapper, records the production messages, and checks a confirmed stable world ID,
known XY geometry, semantic-map/covariance export and scatter output. Unit tests
cover repeated categories and changed detection order, overlap/reacquisition,
outliers, ambiguous assignment, weak geometry, timing mismatch, pose interpolation,
clock/origin reset, memory bounds, and covariance coverage on synthetic random
noise. These establish software behavior in controlled data, not on-water accuracy
or measured Jetson throughput. Simulator truth remains evaluation-only.

Validation of this implementation: `make validate`, 70 benchmark tests, 34
mapper tests against the installed autonomy image without runtime-source mounts,
and 11 recording-menu tests passed. The no-depth RGB replay fixture produced
one confirmed buoy at the known XY location, with stable identity and positive
covariance; a deliberately false truth topic in its source bag was not played.
An actual `Sample_1` replay at zero clock offset produced 754 waiting-input
outputs, zero ready frames and zero coordinates, and correctly marked the run
incomplete. Its report retained the clock-alignment rejection reasons. This is
input-gate evidence, not an accuracy result for that recording.
