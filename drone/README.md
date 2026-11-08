# Drone sensing and perception

Implemented on `feature/cv-raycast`: a source-independent pixel/state -> ENU observation
-> correlated uncertainty -> physical-instance tracking -> WGS84 JSON pipeline, with
seeded synthetic survey generation, withheld evaluation and deterministic recording/replay.
The default tracker is static/random-walk. No constant-velocity or moving-object claim
is made. Real camera/FCU acquisition, trained detection, ROS runtime, Docker, Jetson and
physical accuracy remain unvalidated. The IMU recorder now feeds the processing/replay
boundary when paired with verified same-time navigation. Existing GCS import and boat
behavior are unchanged.

Read [LLM.md](LLM.md), [TASKS.md](TASKS.md) and [AGENTS.md](AGENTS.md) for context/scope.
The deployed sensor direction remains fixed Arducam IMX519 + ordinary GNSS, without RTK.

## Setup and deterministic demonstrations

Run from the repository root. Python 3.12 on Linux x86_64 was exercised; pinned SciPy
and pyproj require Python >=3.11. This dependency set is not a claim of compatibility
with the Jetson's eventual JetPack/ROS/Python combination.

Use **uv exclusively** to create environments, install Python packages and run Python
commands for this workstream. Run every command below from the repository root. Use an
unused environment path if `.venv` already belongs to other work, and substitute that
path consistently. No environment activation is needed.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r drone/requirements-test.txt -e ./drone
```

For a non-editable package installation, omit `-e` in the install command. The repository
retains its pinned requirements and ROS `setup.py` packaging. There is no uv project or
lockfile here, so use `uv pip install` and the explicit interpreter with `uv run
--no-project`; do not assume `uv sync` is configured. The explicit interpreter prevents
an unrelated active environment from being selected. `git`, `docker`, `ros2`, `colcon`
and shell utilities retain their native commands; uv manages the Python environment.

One command generates measurements, executes the actual production pipeline and evaluates
its reports against a separate truth file:

```bash
uv run --no-project --python .venv/bin/python python -m perception_synthetic.demo --adapter synthetic --scenario stationary --output simulation/logs/perception/stationary-demo
```

The independent analytic case has a nadir camera and targets at ENU (0,0), (1,0), (0,1):

```bash
uv run --no-project --python .venv/bin/python python -m perception_synthetic.demo --adapter synthetic --scenario analytic --output simulation/logs/perception/analytic-demo
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
uv run --no-project --python .venv/bin/python python -m maritime_perception.replay --session simulation/logs/perception/stationary-demo/session --output simulation/logs/perception/stationary-replay
```

`--adapter synthetic` is mandatory for generation. Replay is explicitly a recorded-input
entry point. There is no automatic switch from unavailable hardware to synthetic inputs.
Missing calibration, unknown required covariance, missing heading/height quality or bad
timing produces explicit rejection/unavailability. A rejected measurement never becomes
a fresh GPS observation; retained tracks may still be explicitly predicted/stale.

## IMU input and navigation integration

The [IMU recorder guide](../log/README.md) covers actual ROS topic recording and uv setup.
The formatter/output/listener are installed with this drone package. JSONL records retain
integer `stamp_ns`, `frame_id`, quaternion XYZW, body angular rate, acceleration and each
covariance's known/unknown/unreported meaning. CSV and degree angles are diagnostics.
Never reconstruct processing timestamps from the legacy floating-point `t` column.

The processing core accepts `imu_state` events in addition to `vehicle_state` and `frame`:
`data` contains `imu` (a recorded `maritime.imu_sample`), `navigation` (the existing
source-neutral state fields), and `contract` (the checks below). `add_imu_state` replaces
only attitude/angular rate with IMU values, converts rates into ENU, validates the joint
pose model, then calls the existing pose-history/projection/tracking path. Exposure-time
interpolation still uses the existing bounded pose resolver. Both replay entry points
accept this event. Old sessions keep their original behavior.

`navigation` supplies position, ENU velocity, position reference, quality, origin/epoch,
clock, shared-model ID, and full sample/shared **joint pose** covariance. Its old quaternion
and angular rate are replaced. The joint covariance must describe this exact combined
estimate, including position-attitude correlation and common heading/GNSS errors; it is
not made by adding correlated FCU outputs or zeroing missing fields. The total angular
block must cover at least the reported IMU orientation covariance in the ENU tangent.
MAVROS default covariance settings do not establish this model's validity.

| Contract key | Required meaning before enabling |
| --- | --- |
| `expected_frame_id` | Measured IMU body frame ID (commonly `base_link`); FLU body axes align with the pipeline's body |
| `orientation_covariance_frame` | Explicit `body` (rotate into ENU) or `survey_enu`; established from the actual source/model |
| `conventions_verified` | True only after verifying quaternion body-to-ENU direction, body alignment and earth-referenced heading |
| `clock_verified` | True only when IMU header nanoseconds and navigation are already in the same `survey_utc` clock, with clock errors represented in session settings |
| `covariance_decomposition_verified` | True only for a justified full joint pose model split into sample and named shared errors |

The boolean checks are explicit caller assertions, not automatic sensor verification.
Navigation must retain `frame_id=survey_enu`, `body_frame=FLU`, valid position/heading/height,
and a fixed WGS84 origin. A MAVROS frame named `map` is not automatically that origin.
Do not relabel it without establishing its transform, datum and reset behavior.

To integrate actual recordings, prepare an ordinary navigation/frame session in the
[existing core contract](maritime_perception/contracts.py) and a measured `imu_contract.json`
with the five keys above. Use only states with exactly matching IMU timestamps:

```bash
uv run --no-project --python .venv/bin/python python -m maritime_perception.adapters.imu_session --session simulation/logs/perception/navigation-session --imu simulation/logs/perception/imu/samples.jsonl --contract simulation/logs/perception/imu_contract.json --output simulation/logs/perception/imu-session
uv run --no-project --python .venv/bin/python python -m maritime_perception.replay --session simulation/logs/perception/imu-session --output simulation/logs/perception/imu-result
```

These paths represent recordings/configuration you must provide, not bundled physical
fixtures. The join streams through ordered data, rejects duplicates/missing matches and
publishes a new session only after validation. It preserves the source configuration's
synthetic/hardware provenance, copies IMU records and records source checksums. It does
not copy truth into processing input or invent calibration/navigation. Old Euler-only CSV
cannot satisfy this contract; record the JSONL path.

The exact join deliberately refuses a one-nanosecond mismatch. Unsynchronized real streams
need a separately validated timestamp/alignment and joint-correlation model before use;
there is no nearest/latest-sample fallback. This is not a complete live camera/GNSS node.
An application owning a valid same-time navigation provider can connect directly:

```python
from maritime_perception.adapters.imu_input import PipelineImuSink
from maritime_perception.adapters.imu_output import ImuOutput

# pipeline, navigation_at and measured_contract are owned by the sensor application.
sink = PipelineImuSink(pipeline, navigation_at, measured_contract)
output = ImuOutput(on_sample=sink)  # handle(from_imu_msg(message)) in its subscriber
```

Invalid pairs produce pipeline diagnostics and no fresh pose. IMU alone supplies neither
GNSS position nor trustworthy camera height. SP-01/SP-02/SP-04/SP-06/SP-41/SP-42/SP-44
remain open for physical contracts and asynchronous/live acquisition.

## First tests with manual pixels and real recordings

The [pipeline report](../docs/perception_reports/Maritime_Pipeline_Report.docx) explains
current components and visuals. The [completion plan](../docs/perception_reports/Maritime_Pipeline_Completion_Plan.docx)
separates implementation work, owner-answerable questions and experimental tests.
These are source-pinned snapshots of commit `999f1ac`; this README and the topic documents
remain the living references. No physical acceptance or new runtime behavior is implied.

Start with the analytic and stationary commands above. Inspect `evaluation.json`,
`result/reports.jsonl`, `result/observations.jsonl` and rejection diagnostics. Then change
only one input at a time. Target GPS coordinates are evaluation references, not raycast
inputs; supplying those as results would bypass the algorithms being tested.

### Inject a chosen pixel through the existing replay contract

After running the analytic demo above, this creates a separate, explicitly synthetic
session containing one manually chosen pixel per frame. It copies vehicle states and
calibration unchanged, excludes truth, and refuses to overwrite an existing session.
Run from the repository root:

```bash
uv run --no-project --python .venv/bin/python python - <<'PYTHON'
import json
from pathlib import Path

source = Path("simulation/logs/perception/analytic-demo/session")
target = Path("simulation/logs/perception/manual-pixel-session")
target.mkdir(parents=True, exist_ok=False)
config = json.loads((source / "config.json").read_text())
config["survey_id"] = "synthetic_manual_pixel"
(target / "config.json").write_text(json.dumps(config, indent=2) + "\n")
with (target / "measurements.jsonl").open("w") as output:
    for raw in (source / "measurements.jsonl").read_text().splitlines():
        event = json.loads(raw)
        if event["kind"] == "frame":
            frame = event["data"]
            frame["detections"] = [{
                "id": frame["id"] + "_manual", "class_id": "buoy",
                "pixel_uv": [700.0, 480.0],
                "pixel_covariance": [[0.25, 0.0], [0.0, 0.25]],
                "reference_method": "water_centre",
            }]
        output.write(json.dumps(event, allow_nan=False) + "\n")
PYTHON
uv run --no-project --python .venv/bin/python python -m maritime_perception.replay --session simulation/logs/perception/manual-pixel-session --output simulation/logs/perception/manual-pixel-result
```

In this specific synthetic calibration, the camera is at ENU `(0,0,4)`, attitude is
identity, the fixed optical mount maps image right toward South, `fx=fy=600`, the
principal point is `(640,480)`, and water is at `Up=0`. Pixel `(700,480)` must therefore
project to `(East,North)=(0,-0.4)` metres. `(640,480)` gives `(0,0)`; `(640,330)` gives
`(1,0)`. These expectations depend on the declared mount, not an assumed IMX519 orientation.
The documented example was executed on 2026-11-04: four reports, one confirmed identity,
final ENU `(0,-0.4000000000000001,0)`, and no replay errors. This is a noiseless-pose
software check, not a measured accuracy result.

The nonzero pixel covariance is a synthetic assumption. `water_centre` is justified here
by the planar point target; that string does not validate a real buoy reference method.

Inspect the last report's `tracks`, `position_enu_m`, `position_wgs84` and `uncertainty`.
A changed measurement file invalidates the original scenario's evaluator correspondences;
use these analytic checks or a separately updated evaluator. Do not reuse old truth as
though it described edited observations. All generated sessions/results stay ignored.

### Establish the first real recording

Collect a read-only camera/telemetry recording before building a live adapter. The core
already exports JSON reports; the highest-value missing interfaces are upstream:

| Stream or fact | Record or establish | Why it blocks a valid physical test |
| --- | --- | --- |
| FCU and host inventory | Actual controller/firmware, GNSS receiver, available USB/serial/network interface, JetPack/Python/ROS versions | Select one supported acquisition path without assuming the boat's setup applies |
| Vehicle state | Position, full quaternion including earth-referenced heading, velocity/angular rate, source timestamps, quality and any covariance | Raw IMU alone cannot anchor object GPS; capture rates, units, frames and reset behavior |
| Camera | Original images, image IDs, resolution/mode/focus/exposure, available sensor and arrival timestamps | Calibration and exposure-time pose must describe these exact pixels |
| Geometry | Intrinsics/distortion, optical-to-body rotation, lens/body/antenna offsets, target-plane height | A real image plus arbitrary pose/calibration cannot establish physical geolocation error |
| Error and timing | Unknown fields explicitly marked; measured or justified uncertainty model and clock mapping | Do not set unknown covariance to zero or certify arrival time as exposure time |

If ROS is already installed, `ros2 topic list -t` and selected `ros2 topic info -v`,
`ros2 topic echo` and `ros2 topic hz` observations can inventory the *actual* interfaces.
If telemetry is available only as MAVLink, retain a read-only telemetry log and document
its message fields; do not assume ROS topics or request a new flight/arming sequence.
Preserve raw records even when fields are unknown. The production projection should
reject unavailable requirements until the adapter/calibration contract is established.

For the first physical geometry experiment, use a stationary mounted camera over a flat
measured target grid on land. Manually annotate the planar target centres, measure camera
height/orientation and local target offsets, calibrate the chosen image mode, and replay
with timestamps and declared uncertainty. Flat ground temporarily plays the modeled
surface; this isolates geometry before moving-camera timing, buoy freeboard or detector
errors. Test centre and edge targets, then rotate the rig and repeat. Absolute GPS truth
is unnecessary for a relative-grid test.

An arbitrary configured WGS84 origin can exercise geodetic serialization in an explicitly
labeled synthetic/bench fixture. It cannot validate absolute GPS accuracy. Vehicle fixes
are converted into fixed-origin ENU with `GeodeticConverter.to_enu(latitude, longitude,
ellipsoid_height)`; never insert latitude/longitude degrees into `position_enu_m`. Keep
origin uncertainty and GNSS common errors. Real target GPS/reference coordinates remain
outside processing inputs. Mixed real pixels/fake state are a software smoke test only.
Do not silently select synthetic mode/calibration after a hardware failure.

The first integration deliverable is one replayable short session: original images,
raw telemetry, timestamps/clock evidence, calibration/mount/height measurements, annotated
pixels and a separate measured target grid. A live ROS adapter, trained YOLO, flight,
radio and GCS importer are later increments; none is needed to start this land test.

## Tests and implementation boundaries

IMU review (2026-11-08): the original 74 drone tests and 30 additional IMU tests pass.
The added end-to-end case processes a 90-degree heading through the real plane projector,
tracker and WGS84 encoder, recovering the analytical `(0.4,0)` m point and retaining the
2.25 m² shared GNSS floor. IMU/session replay is byte-identical. Tests cover ROS unavailable/
unknown covariance, bad quaternions/frames/times/quality, anisotropic covariance rotation,
recording overwrite protection, sensor-data QoS and subscriber startup/shutdown via doubles.
Both original demos, 11 existing GCS workspace tests, Python/XML/link/shell checks and a
non-editable package installation outside the checkout also pass. The installed IMU CLI
fails explicitly when ROS is missing; no synthetic input is selected instead.
These are software checks. No live ROS/DDS, MAVROS/FCU, camera, Jetson or physical trial ran.

Verified on 2026-11-04: 74 drone tests and 11 existing GCS workspace tests passed.
Both demo commands ran and reports were inspected. The analytic case recovered all
three points exactly; the noisy case emitted 61 reports, retained 3 confirmed identities
with 0 switches/fragmentations/mixed identities, and had 0.817358 m p95 absolute error
with the configured GNSS offset. Minimum final shared covariance eigenvalue exceeded
2.25 m^2. Three invalid-input cases were rejected and 2 observations were marked ambiguous.
Predicted/stale states appeared during gaps; all 3 final tracks were stale after the
deliberately unbracketed exposure. Error statistics use pure confirmed tracks.

A separate non-editable package build/install and packaged analytic demo passed outside
the checkout. Recorded replay was byte-identical, including in a different process/hash
seed; truth was absent in one replay test. Python/XML parsing, maintained Markdown file
links and strict-shell syntax passed. ROS's unavailable-runtime failure was exercised;
Docker/ROS/colcon/DDS/Jetson, actual detector inference and physical trials did not run.

```bash
uv run --no-project --python .venv/bin/python python -m pytest drone/tests -q
uv run --no-project --python .venv/bin/python python -m unittest discover -s gcs/tests -p test_workspace.py -v
uv run --no-project --python .venv/bin/python python -m compileall -q drone/maritime_perception drone/perception_synthetic drone/launch
bash -n drone/container/entrypoint.sh
```

The uv-only commands were also exercised with uv 0.13.5 and a fresh Python 3.12.14
virtual environment: both demos, manual-pixel replay, byte-identical stationary replay,
74 drone tests, 11 GCS workspace tests, compileall and shell syntax checks passed.
The Docker/ROS candidates were updated for uv but were not built or executed here.

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
docker run --rm --network none maritime-perception:cpu uv run --no-project --python /opt/perception-venv/bin/python python -m pytest tests -q
mkdir -p simulation/logs/perception/docker
docker run --rm --network none -v "$PWD/simulation/logs/perception/docker:/output" maritime-perception:cpu
```

Desktop ROS Jazzy evaluation image; no GPU/camera/FCU devices are exposed:

```bash
docker build -f drone/container/Dockerfile.ros -t maritime-perception:ros-desktop drone
docker run --rm --network none -v "$PWD/simulation/logs/perception/stationary-demo/session:/session:ro" -v "$PWD/simulation/logs/perception/new-ros-output:/output" maritime-perception:ros-desktop ros2 launch maritime_perception replay.launch.py session:=/session output:=/output
```

Both Dockerfiles copy pinned uv 0.13.5 from the official Astral image and use uv for
Python environment/dependency installation. ROS system packages still use apt and colcon.
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
