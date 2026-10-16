# Develop buoy positioning methods from a recording

Benchmarking plays the input bag through the same ROS detector and localization
nodes intended for live operation, then records their output in a separate bag.
The detector produces **2D ArUco marker bounding boxes**. The depth and RGB
triangulation algorithms remain placeholders: they publish `not_implemented`
status with no invented coordinates. Localization accuracy scoring is deferred.

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

For both placeholders, expect a result bag containing real detection/status
messages, a CSV with its header only, and no scatter plot. A `complete` pipeline
report means the launch/play/record/export path worked. It does **not** mean a
positioning algorithm or its accuracy has been validated. Runs never overwrite
prior results.

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
| `autonomy/ros_ws/src/maritime_localization/` | Observation/estimate data classes and two method skeletons |
| `autonomy/ros_ws/src/maritime_interfaces/` | Common XY output messages for live and replay nodes |
| `Simulation/tests/evaluation/benchmarking/` | Host launcher, offline runner, tests, replay comparison probe |

Edit `maritime_perception/config/aruco.yaml` for the dictionary/category mapping.
Supported categories are white, red, green, and blue; default IDs are 0–3.
Restart the detector after configuration changes. Python sources/configuration
are mounted from the checkout, so edits take effect on the next invocation.
New dependencies, entry points, or message definitions require `make benchmark-build`.

Methods are ordinary Python classes with `reset()` and
`process(Observation) -> list[PositionEstimate]`. Implement `depth.py` or
`triangulation.py`, then set its `implemented` flag to true. The ROS wrapper
assembles observations and publishes the returned finite XY points in `map`.
There is no separate benchmark implementation of the method. The triangulation
node does not subscribe to depth and its method entry point also rejects depth.

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

The shared ROS localization pipeline was also exercised on `Sample_1`: the
depth placeholder saved 754 detection/localization arrays (737 with assembled
inputs), and triangulation saved 753 arrays (737 with assembled inputs), with
no depth replay for triangulation. Every update reported `not_implemented`;
both result bags finalized with zero coordinates. An interrupted run retained
238 partial updates, exported its CSV, and recorded `interrupted` status. All
temporary nodes, recorders, and players stopped cleanly.
