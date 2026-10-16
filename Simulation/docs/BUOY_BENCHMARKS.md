# Develop buoy positioning methods from a recording

The working stage detects **2D ArUco marker bounding boxes**. Depth positioning
and temporal RGB triangulation have interfaces only; selecting either method
fails with an explicit "not implemented" error. Localization accuracy scoring
is deferred.

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

## Process a recording offline

```bash
make benchmark RECORDING=Sample_1
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
| `Simulation/tests/evaluation/benchmarking/` | Host launcher, offline runner, tests, replay comparison probe |

Edit `maritime_perception/config/aruco.yaml` for the dictionary/category mapping.
Supported categories are white, red, green, and blue; default IDs are 0–3.
Restart the detector after configuration changes. Python sources/configuration
are mounted from the checkout, so edits take effect on the next invocation.
New dependencies or entry points require `make benchmark-build`.

Methods are ordinary Python classes with `reset()` and
`process(Observation) -> list[PositionEstimate]`. Observations describe boxes,
image time/frame, calibration, optional registered depth, and optional camera
pose in a named reference frame. The triangulation entry point rejects depth.
There is no plugin registration framework. Start in `depth.py` or
`triangulation.py` and extend the runner when implementing the method.

Before enabling methods, add exact RGB/depth matching and validated calibration
to input assembly. Vessel-pose use also requires validated time correspondence
and transforms. Camera headers currently use simulation time and MAVROS headers
use Unix time; `use_sim_time` does not align them. Triangulation needs camera
motion and cross-frame association. Estimating motion solely from RGB would
require visual odometry. The current runner assembles detection inputs only.

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
