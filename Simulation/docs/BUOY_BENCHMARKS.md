# Buoy detection and Bearing EKF mapping benchmarks

The localization benchmark runs **Bearing EKF Buoy Mapping** (`bearing_ekf`):
RGB boxes → calibrated world bearings → robust multi-view initialization →
persistent per-buoy XY EKFs. The former depth and basic triangulation methods
have been removed. The offline detector remains available for inspecting boxes.

See the [localization package README](../../autonomy/ros_ws/src/maritime_localization/README.md)
for every input/output topic, parameter, file responsibility, filter equation,
and track state. See [mapping design and clock recovery](RGB_BUOY_MAPPING.md)
for timing assumptions, map artifacts, limits and historical results.

## Build and test

Run from `Simulation/`:

```bash
make validate
make benchmark-build
make benchmark-test
```

The autonomy image installs the production detector, mapper, and custom ROS
interfaces. The benchmark image adds bag playback/recording and plotting.
Rebuild after changing dependencies, entry points, message definitions or
installed assets. Python source edits are mounted from the checkout.

## Run a ROS localization benchmark

```bash
make benchmark RECORDING=Sample_1
# Explicit equivalent:
make benchmark RECORDING=Sample_1 METHOD=bearing_ekf
```

Each run starts the production detector, buoy mapper and output recorder, waits
for subscriptions, plays the recording once, drains pending outputs, stops its
processes and exports the results. `RATE=0.5` slows playback;
`REPLAY_DOMAIN_ID=98` changes the isolated domain (default 97). The replay domain
must differ from the source capture domain. Ctrl-C preserves partial results
with an interrupted report. Source recordings are mounted read-only and previous
results are never overwritten.

You can also use `make record`, select **Browse recordings**, choose a complete
recording, then **Run ROS localization benchmark**. There is no method-selection
prompt: this always runs Bearing EKF Buoy Mapping. The menu accepts a verified
clock offset, playback speed and isolated domain. A benchmark build action is
available in the main menu.

Only RGB, camera calibration, vessel odometry and static mounting TF are played.
The mapper has no depth/truth input. `POSE_CLOCK=auto` preserves compatible
source clocks or recovers a replay clock bridge from recorded FCU time
references. Normalized poses, when needed, appear on
`/benchmark/vessel/odometry`. `POSE_CLOCK=source` requires compatible source
stamps; `POSE_CLOCK=recorded-reference` forces recovery. A verified nonzero
`POSE_TIME_OFFSET_S` overrides automatic recovery; do not combine it with forced
reference recovery. Convention: **pose stamp + offset = image-clock stamp**.

The recorder is ready before playback. During startup the supervisor briefly
holds `/clock` at the bag's initial time, then hands ownership to the player.
The mapper still uses acquisition-time pose brackets, never callback arrival or
the latest pose as a fallback. Clock-reference residuals are not a measured
bound on image acquisition-time accuracy.

## Results

Runs create `logs/benchmarks/<recording>/bearing_ekf-<UTC time>/`:

| Artifact | Meaning |
| --- | --- |
| `bag/` | Detections, fresh XY estimates, semantic map, bearing decisions, costmap, markers and diagnostics; normalized poses if recovery was used. |
| `final_map.json` | Last metric map, session ID, lifecycle, covariance and evidence. |
| `map_history.csv` | Metric-map history, including tentative/stale records. |
| `observations.csv` | Bearings, camera origins, uncertainty, pose brackets, offset and association decisions. |
| `estimates.csv`, `scatter.png` | Confirmed fresh XY updates. Scatter is only created when estimates exist. |
| `clock-alignment.json`, `pose-clock.csv` | Clock bridge and source/normalized stamp pairs when recovery is used. |
| `report.json`, `summary.json` | Completion, input/output counts, statuses, parameters and assumptions. |
| `detector.yaml`, `provenance.json` | Detector configuration, revision/dirty state, image ID and source hashes. |
| `source-dataset.json`, `source-quality.json` | Source recording identity and quality. |
| `nodes.log`, `player.log`, `recorder.log` | Runtime evidence and errors. |

`status=ok` means input assembly succeeded, even if geometry is unresolved or
identity is unconfirmed. A tentative map can exist before confirmed scatter
points. Inspect map states, observation decisions and diagnostics. Completion
means replay and export succeeded; it does not establish position accuracy.
The retained result-message/CSV depth timestamp field is unused and zero for
this mapper; it allows older saved results to remain readable.

## Launch against live topics or a manual replay

Inside a sourced autonomy ROS environment:

```bash
ros2 launch maritime_localization pipeline.launch.py
# For a separately managed player on the same isolated domain:
ros2 launch maritime_localization pipeline.launch.py use_sim_time:=true
```

Defaults are `camera:=camera_0` and
`pose_topic:=/mavros/local_position/odom`. The executable is `buoy_mapper`, node
`/localization/buoy_mapper`; parameters use `bearing_ekf.<setting>`. Supply a file
with `mapper_parameters:=/absolute/path/config.yaml`. Input clocks and frame IDs
must satisfy the mapper's contracts. Do not start an extra player alongside
`make benchmark`.

For the managed live teleop/viewer workflow, see
[Live RGB mapping](../../autonomy/docs/LIVE_RGB_MAPPING.md). The default
Simulation service still runs the guarded bootstrap; detection/mapping are
explicitly launched.

## Optional offline detection

```bash
make benchmark-offline RECORDING=Sample_1
```

This reads every saved RGB image sequentially using the same box detector,
without ROS playback or localization. It filters all other bag topics before
deserialization. Outputs live in `logs/benchmarks/<recording>/detections-<run>/`:
`detections.jsonl`, `report.json`, saved `detector.yaml`, provenance and annotated
`previews/` (normally every 30 frames).

Each frame record contains source image timestamp/frame, bag timestamp, image
dimensions and boxes (`marker_id`, category, center, width, height). Boxes bound
marker faces rather than entire buoys. Marker IDs identify categories, not
physical buoys. No marker corners, range, PnP or 3D pose are exported. Detection
timings exclude conversion and bag I/O; counts do not establish precision,
recall, or localization accuracy.

For detector-only ROS inspection, run these in separate terminals:

```bash
make detect RECORDING=Sample_1
make replay RECORDING=Sample_1 START_PAUSED=1
```

Both default to domain 97; use matching `REPLAY_DOMAIN_ID` values to change it.
The detector publishes `/perception/camera_0/detections` and an optional
`/perception/camera_0/debug/image`. Successfully processed empty scenes produce
empty arrays. Processing failures are logged without substituting empty arrays.
One image is active with at most one replaceable pending image, so ROS delivery
may process fewer frames than offline inspection. Headers retain source time.
`replay_probe.py` compares delivered ROS boxes with offline records at source
timestamps and reports missing frames separately from disagreements.

## Development and verification

Runtime code belongs in `autonomy/ros_ws/src/maritime_localization/`; detection
belongs in `maritime_perception/`; message schemas in `maritime_interfaces/`.
Replay supervision, clock recovery, export and evaluation stay in
`Simulation/tests/evaluation/benchmarking/`.

The tests cover calibrated rays/distortion, robust initialization, independent
EKF evidence, repeated categories, global association/ambiguity, occlusion and
reacquisition, covariance, bounded memory, acquisition-time interpolation,
reset/fault handling, clock recovery and complete ROS replay/export. The
end-to-end fixture has no depth topic and contains a false truth topic that is
excluded from played inputs. It checks a confirmed stable world ID and known XY
geometry. These are software checks using controlled inputs; physical-camera
accuracy, on-water uncertainty calibration and mission readiness remain separate.
