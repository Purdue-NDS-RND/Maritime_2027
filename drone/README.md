# Drone sensing and perception

Implemented on `feature/cv-raycast`: a source-independent pixel/state -> ENU observation
-> correlated uncertainty -> physical-instance tracking -> WGS84 JSON pipeline, with
seeded synthetic survey generation, withheld evaluation and deterministic recording/replay.
The default tracker is static/random-walk. No constant-velocity or moving-object claim
is made. Real camera/FCU acquisition, trained detection, ROS runtime, Docker, Jetson and
physical accuracy remain unvalidated. Existing GCS import and boat behavior are unchanged.

Read [LLM.md](LLM.md), [TASKS.md](TASKS.md) and [AGENTS.md](AGENTS.md) for context/scope.
The deployed sensor direction remains fixed Arducam IMX519 + ordinary GNSS, without RTK.

## Setup and deterministic demonstrations

Run from the repository root. Python 3.12 on Linux x86_64 was exercised; pinned SciPy
and pyproj require Python >=3.11. This dependency set is not a claim of compatibility
with the Jetson's eventual JetPack/ROS/Python combination.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r drone/requirements-test.txt ./drone
```

For development, install editable instead: `.venv/bin/python -m pip install -e ./drone`.
An alternative exercised setup is `uv venv --python python .venv`, then
`uv pip install --python .venv/bin/python -r drone/requirements-test.txt -e ./drone`.
Use a new virtual environment rather than overwriting an existing project environment.

One command generates measurements, executes the actual production pipeline and evaluates
its reports against a separate truth file:

```bash
.venv/bin/python -m perception_synthetic.demo --adapter synthetic --scenario stationary --output simulation/logs/perception/stationary-demo
```

The independent analytic case has a nadir camera and targets at ENU (0,0), (1,0), (0,1):

```bash
.venv/bin/python -m perception_synthetic.demo --adapter synthetic --scenario analytic --output simulation/logs/perception/analytic-demo
```

Output directories must be new or empty. Choose a new path on subsequent runs; the tool
does not delete previous evidence. Scenario JSON paths can replace the built-in names.
The scenarios, seeds, noise, GNSS offsets, target geometry and timing are in
[perception_synthetic/scenarios](perception_synthetic/scenarios).

The stationary survey uses three same-class targets, a moving/turning camera, noisy raw
pixels and antenna poses, a fixed +0.7 m East/-0.4 m North GNSS offset, temporary misses,
duplicate detections, a wrong calibration resolution, an invalid pixel and a final
unbracketed exposure. The camera is a synthetic pinhole/plumb_bob model, not measured
IMX519 calibration. Targets are point references at a flat water surface, without
freeboard, reflections, waves or real rolling-shutter effects.

Each run writes:

| Path under output | Contents |
| --- | --- |
| `session/config.json` | Calibration, fixed origin, clocks, water, covariance and processing settings; no scene targets |
| `session/measurements.jsonl` | Source-neutral timestamped vehicle-state and frame/pixel events |
| `session/truth.json` | Generator/evaluator-only target positions and identity correspondences |
| `result/reports.jsonl` | Validated, versioned geographic track reports, including predictions/staleness |
| `result/observations.jsonl` | Projected measurements and uncertainty factors before tracking |
| `result/replay_errors.jsonl` | Events rejected before a valid report epoch can be established |
| `result/manifest.json` | Input/output/code checksums and runtime package versions |
| `evaluation.json` | Error, identity, rejection, uncertainty and freshness summary with assumptions |

Processing imports neither synthetic scene code nor truth. Replay needs only config and
measurements, and works after removing truth:

```bash
.venv/bin/python -m maritime_perception.replay --session simulation/logs/perception/stationary-demo/session --output simulation/logs/perception/stationary-replay
```

`--adapter synthetic` is mandatory for generation. Replay is explicitly a recorded-input
entry point. There is no automatic switch from unavailable hardware to synthetic inputs.
Missing calibration, unknown required covariance, missing heading/height quality or bad
timing produces explicit rejection/unavailability. A rejected measurement never becomes
a fresh GPS observation; retained tracks may still be explicitly predicted/stale.

## Tests and implementation boundaries

Verified on 2026-11-04: 74 drone tests and 11 existing GCS workspace tests passed.
Both demo commands ran and reports were inspected. The analytic case recovered all
three points exactly; the noisy case emitted 61 reports, retained 3 confirmed identities
with 0 switches/fragmentations/mixed identities, and had 0.817358 m p95 absolute error
with the configured GNSS offset. Minimum final shared covariance eigenvalue exceeded
2.25 m^2. Three invalid-input cases were rejected and 2 observations were marked ambiguous.
Predicted/stale states appeared during gaps; all 3 final tracks were stale after the
deliberately unbracketed exposure. Error statistics use pure confirmed tracks.

A separate non-editable pip build/install and packaged analytic demo passed outside
the checkout. Recorded replay was byte-identical, including in a different process/hash
seed; truth was absent in one replay test. Python/XML parsing, maintained Markdown file
links and strict-shell syntax passed. ROS's unavailable-runtime failure was exercised;
Docker/ROS/colcon/DDS/Jetson, actual detector inference and physical trials did not run.

```bash
.venv/bin/python -m pytest drone/tests -q
.venv/bin/python -m unittest discover -s gcs/tests -p test_workspace.py -v
.venv/bin/python -m compileall -q drone/maritime_perception drone/perception_synthetic drone/launch
bash -n drone/container/entrypoint.sh
```

Tests include analytical geometry (not only matching forward/inverse round trips),
frames/mounts/lever arms/preprocessing, distortion, bounded SLERP pose lookup, resets,
quality/timestamps, PROJ's published reference and equatorial WGS84 cases, covariance
Monte Carlo checks, ellipse scaling/orientation, persistent identities/misses/ambiguity,
shared-error retention, report corruption, and process-independent replay. Numerical
Gaussian tests validate their assumptions only. See living topic docs for dated results.

The numerical core is in [maritime_perception](maritime_perception), and synthetic source
adapters/scenarios/evaluation are separately in [perception_synthetic](perception_synthetic).
The projector uses OpenCV plus a narrow analytic plane intersection because IPM and
image_geometry/tf2 require a ROS environment absent here. SciPy supplies SLERP/rotations,
linear solves and assignment; PROJ supplies geodesy. SP-34's full IPM/Jetson evaluation
remains open, rather than treating this fallback as evidence that IPM was integrated.

Shared error uses named common unit-normal factors, not a bias estimator. For each
observation, P = R_independent + sum(B B^T). Track updates propagate both R and B;
association uses the covariance of the track/measurement difference. A common translation
therefore does not shrink with frame count. Pose-sample IDs preserve correlations when
observations reuse samples. The first-order model assumes named sources are mutually
independent and each named source is constant over its declared session/sample. Real
GNSS drift, unknown temporal correlations and model/reference bias require measured
models before deployment. The output is conditional on association and never claims
physically validated coverage. Full retained factors grow with session length; this is a
bounded-survey/replay prototype, not a validated long-running onboard service.

## Optional detector and ROS paths

[UltralyticsDetector](maritime_perception/adapters/ultralytics_detector.py) accepts only
an existing local weights file. It preserves frame metadata and outputs source-image
box centres. Ultralytics is optional and not installed by the core requirements. Neither
inference nor water-object weights were exercised. Default box-centre references are
marked unvalidated and the geolocator rejects them until a reference policy is verified.
Detector score is never converted into position variance.

[ROS conversions](maritime_perception/adapters/ros_conversion.py) are unit-tested without
ROS using structural messages. Odometry requires an explicitly verified ENU/FLU/body
contract and covariance decomposition: total covariance minus declared shared covariance
must be PSD. No shared term is silently added to a posterior already containing it.
Zero/unknown source covariance must not be certified as precise. Real FCU transport,
clock mapping, epoch detection and heading/height quality need a hardware adapter.

The thin ROS node replays recorded events through the same PerceptionPipeline and
publishes validated JSON on `/drone/perception/report` as `std_msgs/String`, while writing
reports to disk. It is not a live hardware subscriber or radio protocol. In a sourced,
compatible ROS environment, install core dependencies and build this ament package in
a colcon workspace, then:

```bash
ros2 launch maritime_perception replay.launch.py session:=/absolute/session output:=/absolute/new_ros_output
```

Compare its `reports.jsonl` with pure replay. Verify actual ROS message packages, QoS,
launch installation and normal completion before claiming integration. No ROS imports,
launch execution, colcon build or DDS exchange ran in the implementation environment.

## Docker evaluation commands (not executed here)

CPU image, from repository root:

```bash
docker build -f drone/container/Dockerfile -t maritime-perception:cpu drone
docker run --rm --network none maritime-perception:cpu python -m pytest tests -q
mkdir -p simulation/logs/perception/docker
docker run --rm --network none -v "$PWD/simulation/logs/perception/docker:/output" maritime-perception:cpu
```

Desktop ROS Jazzy evaluation image; no GPU/camera/FCU devices are exposed:

```bash
docker build -f drone/container/Dockerfile.ros -t maritime-perception:ros-desktop drone
docker run --rm --network none -v "$PWD/simulation/logs/perception/stationary-demo/session:/session:ro" -v "$PWD/simulation/logs/perception/new-ros-output:/output" maritime-perception:ros-desktop ros2 launch maritime_perception replay.launch.py session:=/session output:=/output
```

Create an empty host output directory first. These images are build candidates, not
executed evidence or a selected Jetson combination. Host drivers/firmware stay outside
the app. No GCS importer, radio transport, flight control or boat routing was changed.

## Replace synthetic inputs progressively

| Current input | Recorded / Gazebo replacement | Hardware replacement and acceptance |
| --- | --- | --- |
| Generated pixels/detections | Annotated frames or detector output with original stamps | Arducam + local trained YOLO weights; reference-pixel errors measured |
| Synthetic K/D/mount/lever arms | Replay camera metadata; calibrated Gazebo camera/mount | Measured mode/focus-specific calibration and physical offsets; never use synthetic calibration |
| Generated antenna pose/attitude | Timestamped fused odometry in the same origin/epoch | Verified FCU GNSS/IMU state, heading source, quality and reset detection |
| Configured clocks | Recorded source/arrival clocks; explicitly bridged simulation clock | Measured exposure time, offset/drift/jitter; no callback-time substitution |
| Flat synthetic water height | Recorded surveyed level; declared simulation surface | Measured water datum/height model, deck offset, drift/wave uncertainty |
| Declared white/shared covariance | Replay calibrated source/correlation model | Receiver/FCU residual measurements and verified covariance decomposition |
| Withheld target truth | Gazebo truth only in evaluator; surveyed replay references | Independent measured reference with quantified uncertainty |
| JSON file reports | File replay or optional ROS publication | GCS importer/radio delivery separately agreed and tested |

The core consumes identical config/state/frame contracts in each case. Gazebo/FCU/Arducam
acquisition bridges remain replacements to implement and validate, not existing drivers.
