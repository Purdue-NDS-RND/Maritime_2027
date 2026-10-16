# Develop buoy positioning methods from a recording

For the report-based persistent **RGB-only map**, use `METHOD=rgb_mapping`.
See [RGB buoy mapping](RGB_BUOY_MAPPING.md) for commands, timing requirements,
map exports, lifecycle and verification.

Benchmarking plays the input bag through the same ROS detector and localization
nodes intended for live operation, then records their output in a separate bag.
The detector produces **2D ArUco marker bounding boxes**. Both depth and temporal RGB triangulation produce buoy XY estimates in the
MAVROS local `map` frame. Localization accuracy scoring is deferred.

Run these commands from `Simulation/`. Names are case-sensitive: the current
user recording is `Sample_1`.

## Build and test

```bash
make benchmark-build
make benchmark-test
```

The build adds OpenCV, `cv_bridge`, and `vision_msgs` to the autonomy image. A
separate `maritime-benchmark:jazzy` image adds bag-reading tools. The default
autonomy service still runs the bootstrap placeholder; launch the detector
explicitly. Building does not restart running simulation services.

Tests exercise generated marker images, repeated categories, perspective,
empty observations, exact source headers, real ROS transport, replacement of
pending images, and an actual MCAP recording. Pose APIs are blocked during a
detection test. A bag containing an unknown truth-message type verifies that
the offline runner does not deserialize truth messages.

## Run a ROS benchmark

```bash
make benchmark RECORDING=Sample_1 METHOD=depth
make benchmark RECORDING=Sample_1 METHOD=triangulation
```

Each command starts the detector, selected localizer, and output recorder;
waits for their subscriptions; plays the recording once; drains pending outputs;
then stops its own processes and exports the results. Normal playback speed is
1. Use `RATE=0.5` to slow it down or `REPLAY_DOMAIN_ID=98` to select another
isolated ROS domain. Stop with Ctrl-C to preserve a partial result and an
`interrupted` report. The source recording is mounted read-only.

You can also use `make record`: select **Browse recordings**, choose `Sample_1`,
then **Run ROS localization benchmark**. The main menu has a benchmark-tools
build action as well.

Each run creates `logs/benchmarks/Sample_1/<method>-<UTC time>/` containing:

| File | Contents |
| --- | --- |
| `bag/` | Recorded detection arrays and `/localization/buoys` updates |
| `estimates.csv` | Source timestamp, frame, method, category, track ID, x/y metres, input pose/depth timestamps |
| `scatter.png` | XY scatter plot, created only when estimates exist |
| `report.json`, `summary.json` | Pipeline completion, method status, input/output counts, assumptions |
| `detector.yaml`, `provenance.json` | Configuration, Git revision/dirty state, image ID, source hashes |
| `source-dataset.json`, `source-quality.json` | Original recording identity and quality |
| `nodes.log`, `player.log`, `recorder.log` | Runtime evidence and errors |

A successful observation has status `ok`; it may contain zero points when no
usable depth or triangulation geometry exists. A CSV and scatter plot contain
only accepted estimates. `complete` means launch/play/record/export succeeded;
it does **not** establish position accuracy. Runs never overwrite prior results.

The result recorder is ready before playback. The supervisor briefly publishes
the recording's initial clock value during setup, then the player owns `/clock`.
Only RGB, calibration, vessel odometry, mounting transforms, and (for the depth
method) depth are played. No simulator truth is supplied to algorithm nodes.

## Optional direct offline detection

```bash
make benchmark-offline RECORDING=Sample_1
```

This reads every saved RGB image sequentially, without playback or Gazebo.
The ROS node uses the same detector code. Offline processing does not drop
frames to keep up with wall time. The input is mounted read-only and the
container has no network. Each run prints a fresh output directory:

```text
logs/benchmarks/Sample_1/detections-<UTC time>/
    detections.jsonl  # One result per image, including empty box lists
    detector.yaml    # Configuration used for this run
    report.json      # Counts, processing times, source recording quality
    provenance.json  # Image ID, Git revision/dirty state, source file hashes
    previews/        # Annotated image every 30 frames
```

Frame results contain the original image timestamp/frame, bag timestamp,
image dimensions, and boxes (`marker_id`, `category`, `center_x`, `center_y`,
`width`, `height`). Coordinates are source-image pixels. The box surrounds
the marker face, not the entire buoy. No corners, range, rotation, or 3D pose
are exported. Repeated IDs remain separate boxes: IDs identify categories,
not physical buoys. Unmapped IDs are excluded from results and previews.

Previous results and recordings are never overwritten. An interrupted/failed
run retains an incomplete report. Reported detector timings exclude image
conversion and bag I/O. Counts are not precision, recall, or position accuracy.

## Run the ROS detector against replay

For manual development of the full pipeline, use the shared launch file inside
a sourced ROS workspace or autonomy image:

```bash
ros2 launch maritime_localization pipeline.launch.py method:=depth use_sim_time:=true
```

Start bag playback separately on the same domain. For live topics, launch the
**same file and nodes** with `use_sim_time:=false`. `pose_topic` defaults to
`/mavros/local_position/odom`; `camera` defaults to `camera_0`. Live input
transport/configuration must match the deployed Adapter. No simulator or bag
reader is part of either algorithm node. The default simulation service still
runs its original bootstrap; this launch is explicit.

To inspect only the detector, without the localization wrapper:

In terminal one:

```bash
make detect RECORDING=Sample_1
```

In terminal two:

```bash
make replay RECORDING=Sample_1 START_PAUSED=1
```

Press Space in the replay terminal to start. The detector uses domain 97 and
simulation time. Supply `REPLAY_DOMAIN_ID=98` to **both** commands to change
the domain. The launcher matches the player's host IPC, UID/GID, and saved
shared-memory profile. Only the transport file is mounted into the detector;
it cannot read the bag or manifest. Its only sensor subscription is the RGB image.

| Topic | Type | Contents |
| --- | --- | --- |
| `/perception/camera_0/detections` | `vision_msgs/msg/Detection2DArray` | Marker boxes and category labels |
| `/perception/camera_0/debug/image` | `sensor_msgs/msg/Image` | Image with rectangles and labels |

For viewing, run `make -C ../Monitor rviz-sim ROS_DOMAIN_ID=97` and add an
**Image** display for `/perception/camera_0/debug/image` with best-effort
reliability. Ctrl-C stops the detector; stop playback separately.

The node preserves source image headers. It publishes an empty array when a
successfully processed image contains no recognized markers, and logs failures
without substituting empty observations. One image can be active with at most
one pending image; newer arrivals replace that pending image. ROS processing
can therefore handle fewer frames than offline processing. Shutdown logs
received, processed, replaced, and failure counts.

The standard detection message includes hypothesis pose fields. They remain
unused defaults, not measured poses. `Detection2D.id` stays empty, box rotation
is zero, and category score 1 means binary recognition rather than calibrated
confidence. No PnP, known-size marker range, or ArUco pose estimation is used.

## Where to develop

| Location | Responsibility |
| --- | --- |
| `autonomy/ros_ws/src/maritime_perception/` | Shared box detector, ROS wrapper, message conversion, parameter YAML |
| `autonomy/ros_ws/src/maritime_localization/` | Shared geometry, depth positioning, temporal RGB tracking/triangulation, ROS wrapper |
| `autonomy/ros_ws/src/maritime_interfaces/` | Common XY output messages for live and replay nodes |
| `Simulation/tests/evaluation/benchmarking/` | Host launcher, offline runner, tests, replay comparison probe |

Edit `maritime_perception/config/aruco.yaml` for the dictionary/category mapping.
Supported categories are white, red, green, and blue; default IDs are 0–3.
Restart the detector after configuration changes. Python sources/configuration
are mounted from the checkout, so edits take effect on the next invocation.
New dependencies, entry points, or message definitions require `make benchmark-build`.

Methods are ordinary Python classes with `reset()` and
`process(Observation) -> list[PositionEstimate]`. The implementations are in `depth.py` and
`triangulation.py`. The ROS wrapper
assembles observations and publishes the returned finite XY points in `map`.
There is no separate benchmark implementation of the method. The triangulation
node does not subscribe to depth and its method entry point also rejects depth.

## Positioning methods

**Depth:** sample the central quarter of each box's width and height. Ignore
nonfinite, zero, negative, or out-of-range depth. Require at least three valid
pixels and 50% valid coverage, and reject patches whose 90th-to-10th percentile
spread exceeds 0.5 m. Take the median optical-Z depth, undistort the box center,
back-project through camera intrinsics, and apply camera-to-`map` mounting and
vessel pose. Depth is optical Z, not radial range. Supported distortion models
are `plumb_bob`, `rational_polynomial`, and `equidistant`.

Depth outputs independent measurements with empty track IDs. It does not smooth
points, merge repeated categories, or infer a hidden buoy center from the visible
marker surface. The saved scatter therefore shows measurement spread.

**RGB triangulation:** assume stationary targets. Associate categories using
rotation-compensated world bearings, then predicted bearings once a track has a
3D point. Matches must be mutual nearest neighbors with a 0.5 degree margin;
ambiguous matches are skipped. Identical marker IDs never identify a track.
Keep spatial keyframes every 0.15 m, at most 40 per track. Fit a 3D point by
minimizing squared perpendicular distance to viewing rays and export its XY.
Require at least three distinct camera positions, 1 m baseline, and 5 degrees
parallax from the same pair,
well-conditioned geometry, forward intersections, and at most 1 degree
angular residual in every view. Accepted ranges are 0.2–80 m for both methods.
Pure rotation and travel directly toward a target cannot provide useful range.

Tracks expire after three seconds on the source image clock; capacity is 128.
IDs are local to a run and can change after occlusion or ambiguous association.
A camera/reference frame change or backwards image clock clears history.
These are simple baseline association rules: nearby same-color buoys, abrupt
view changes, moving buoys, and noisy vessel poses can cause missed or incorrect
matches. Triangulation estimates refer to the observed box-center target; moving
marker faces can violate the stationary-point approximation.

Defaults live in the small `DepthSettings` and `TriangulationSettings` dataclasses.
They are also ROS parameters named `depth.<setting>` or
`triangulation.<setting>` on `buoy_localizer`. The benchmark uses defaults and
saves them as `algorithm_parameters` in `report.json`; source hashes capture
local edits. For example, change `min_baseline_m` in `TriangulationSettings`,
then rerun the benchmark; Python edits do not need a rebuild. Live `ros2 run`
can override with `--ros-args -p method:=triangulation
-p triangulation.min_baseline_m:=0.75` and the appropriate topic remappings.

Synthetic tests recover known XY points with transformed cameras and lens
distortion, keep repeated categories separate when detection order changes,
and reject pure rotation, parallel/behind-camera rays, ambiguous matches,
invalid depth, and mixed surfaces. Both methods are also exercised through
real ROS launch/play/record/export with a moving-camera fixture.

Current agreed assumptions:

- Output points use the MAVROS local `map` frame, in metres. Pose position **and
  orientation** come from `/mavros/local_position/odom`; the camera mounting
  transform is composed with that pose. No truth-derived pose is used.
- Inputs use their latest received values. There is no timestamp matching,
  interpolation, or clock conversion. Original image, pose, and depth stamps
  are retained. Camera simulation time and MAVROS Unix time remain different.
- The 2D box center approximates the buoy center. Algorithms receive no ArUco
  corners, physical marker size, or ArUco pose solution.
- Replay normally runs at 1x. Delivered/processed/output counts are reported;
  a repeated run is not promised to process an identical subset of images.
- `map` and simulator truth coordinates appear close in `Sample_1`, but exact
  alignment remains provisional. No position-accuracy score is computed yet.

`/localization/buoys` is `maritime_interfaces/msg/BuoyEstimateArray`. Its header
uses the source observation time and output coordinate frame. Each point has
category, optional physical track ID, and x/y in metres. Array status is `ok`,
`not_implemented`, `waiting_for_inputs`, or `error`; `inputs_ready` distinguishes
successful input assembly from missing inputs. A marker category is never used
as a physical track ID. An empty successful observation differs from an
unimplemented method. Run state is reset by launching fresh nodes for each bag.

Future scoring belongs in this simulation evaluator and may read recorded
truth. Detectors and positioning methods must never consume truth. Distinguish
marker-surface positions from buoy centers. Simulated markers rotate toward
the boat, so their surface centers/corners are not fixed world points even
when buoy centers remain stationary. Repeated IDs require real association.

## Measured evidence

`Sample_1`: all 755 RGB frames processed offline, 471 frames with recognized
markers, 415 red boxes and 341 green boxes. Annotated previews were inspected.
The recording's 754 exact RGB-D triples and 148 reported transport losses remain
visible in the report; offline processing cannot recover absent messages.

A full-speed ROS replay produced 754 detection arrays and 754 debug images.
Every received detection matched its offline boxes and source header exactly.
One of the 755 recorded RGB frames was not represented in received results;
this check does not attribute that difference to a particular pipeline stage.
This is delivery/processing evidence, not detection accuracy.

`replay_probe.py` compares ROS outputs with saved offline `detections.jsonl`
at source timestamps, reporting frame counts separately from disagreements.

The initial placeholder runs verified recording and interruption handling. Both
methods are now implemented; current algorithm verification is described below.

With the implemented methods, `Sample_1` produced 756 depth measurements and
141 triangulated measurements in full-speed ROS runs. Both finalized result
bags, CSVs, and scatter plots with no algorithm errors; initial updates waited
for calibration/pose/TF. Frame counts can vary with asynchronous delivery.

Depth medians were approximately red `(6.66, 1.35)` m and green `(6.64, -1.57)` m.
Triangulation was visibly less stable and biased: medians in that run were red
`(5.91, 1.03)` m and green `(4.81, -1.75)` m. The saved scenario layout places
buoy model origins at `(7, 1.5)` and `(7, -1.5)` m, while the observed marker
surfaces are offset and rotate. This is a sanity comparison, **not** an accuracy
score: truth-frame alignment and camera/pose timing remain unvalidated. Do not
interpret geometric acceptance gates as a guarantee of accurate localization.
