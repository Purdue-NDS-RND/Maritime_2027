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

Run from the repository root. Python 3.10 and 3.12 on Linux x86_64 are exercised.
Requirements select explicit Python 3.10 pins for host ROS/GI environments and retain
the existing pins on Python >=3.11. Native Jetson/ROS/Argus execution remains unverified.

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

Python 3.10 compatibility (2026-11-08): a fresh x86_64 install passes 161 drone tests
and 11 GCS workspace tests; the Python 3.12 environment also passes 161 drone tests.
Analytic demo, delayed replay (4 reports/12 observations), total state loss (zero
observations, expected nonzero exit), and camera dry-run pass on 3.10. ARM64 Python
3.10 binary-wheel dependency resolution succeeds; native ARM/ROS/GI/Argus execution
has not run here. Record package versions with data; byte-identical replay is tested
within a runtime, not promised across the two dependency profiles.

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

## Arducam IMX519 image capture

The user selected the [16 MP IMX519 module with M12 wide-angle lens](https://www.uctronics.com/16mp-imx519-camera-module-with-m12-lens-wide-angle-color-rolling-shutter-for-raspberry-pi-and-openhd.html).
The acquisition structure was reviewed against CUASC_2026 `image_grabber.py`, its
compressed grabber, detector and launch/config files at commit
`e50d6e2e42e0e6eeac150e8b7c94be0d0474a42d`. The maintained implementation is
[adapters/image_grabber.py](maritime_perception/adapters/image_grabber.py).
It captures without requiring trained weights, navigation or an armed vehicle.

The two imported [calibration files](maritime_perception/config) are preserved byte-for-byte.
`arducam_info.yaml` contains raw 3840x2160 K/D and a different rectified P;
`kalibr.yaml` converts the same K/D to pinhole/radtan with k3=0. They are one historical
calibration, not two independent measurements. Their provenance is recorded in
`calibration_provenance.json`. Lens, focus and sensor-mode applicability to the selected
M12 camera remains unverified. No mount, covariance or timing calibration is inferred.

### Host requirements and first capture

Use the Jetson's actual compatible IMX519 driver/Argus installation. The Raspberry Pi/
OpenHD listing does not establish support for a particular Jetson carrier, cable or
JetPack release. Host camera drivers remain outside the app. Inspect available modes
and source controls on that host:

```bash
v4l2-ctl -d /dev/video0 --list-formats-ext
gst-inspect-1.0 nvarguscamerasrc
```

These commands require host V4L2/GStreamer tooling. On a compatible Ubuntu host, native
dependencies for the capture backend are installed separately from the uv environment:

```bash
sudo apt-get install python3-gi python3-gst-1.0 gstreamer1.0-tools gstreamer1.0-plugins-base gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 v4l-utils
uv run --no-project --python /usr/bin/python3 python -V
```

The system Python must be **>=3.10** and match the host GI/ROS binary bindings;
the GStreamer video-info API requires GStreamer >=1.20. Python 3.10 selects NumPy
1.26.4, SciPy 1.15.3, OpenCV 4.11.0.86 and pyproj 3.6.1. Keeping NumPy below 2 on
this profile avoids introducing NumPy 2 into the older host stack; actual native
imports still need verification. Python >=3.11 keeps the original NumPy/SciPy/OpenCV/
pyproj pins. Do not use --ignore-requires-python or assume a downloaded uv interpreter
can import ROS/GI built for another ABI. The final JetPack/ROS/Python matrix remains
SP-01; portable tests do not establish native Jetson acceptance. From the repository root:

```bash
uv venv --python /usr/bin/python3 --system-site-packages .venv-camera
uv pip install --python .venv-camera/bin/python -r drone/requirements-test.txt -e ./drone
uv run --no-project --python .venv-camera/bin/python python -m maritime_perception.adapters.image_grabber --config drone/maritime_perception/config/imx519_capture.json --dry-run
uv run --no-project --python .venv-camera/bin/python python -m maritime_perception.adapters.image_grabber --config drone/maritime_perception/config/imx519_capture.json --output simulation/logs/perception/camera-run-01 --max-frames 30 --save-interval-s 0
```

For ROS on the observed Python 3.10 host, first source its installed distribution
(for example `source /opt/ros/humble/setup.bash` for Humble). Reuse the already created
`.venv-ros`; its previous failed install did not install the project. After updating
`feature/cv-raycast`, install and verify in that environment:

```bash
uv pip install --python .venv-ros/bin/python -r drone/requirements-test.txt -e ./drone
uv run --no-project --python .venv-ros/bin/python python -c 'import rclpy, maritime_perception; print("Project and ROS OK")'
uv run --no-project --python .venv-ros/bin/python python -m maritime_perception.async_test --help
```

Check each command succeeds before running the next. `No module named
maritime_perception` after an unsatisfiable-dependencies error is a failed-install
consequence, not a separate ROS failure. Retain `.venv` Python 3.12 for portable tests.

The sample requests the legacy 3840x2160/17 FPS mode, 1/1000 s shutter and rectification.
Those requests must match a mode supported by the actual driver; they are not measured
hardware performance. `--dry-run` validates calibration and prints controls without GI,
ROS or a camera, so it also works in the portable `.venv` environment.

Use a new output directory each run. The recorder saves PNGs (or explicitly selected
JPEGs), checksums, `frames.jsonl` and `capture_config.json`, including effective K/D,
calibration identity, requested controls and original source/arrival timing. Disk/encoder
errors stop capture visibly. Ctrl+C, count/duration completion and startup failures release
the pipeline. The one-buffer appsink drops old frames instead of building a backlog;
slow publication, rectification or disk writes can drop captures and must be measured.

### Controls at execution

All controls are startup CLI options or keys in a JSON `--config` file. CLI values override
the file. Settings are fixed for a capture session; restart with a new directory to change
them. Sensor FPS, processing/publication rate and recording interval are separate controls.

| Option(s) | Meaning |
| --- | --- |
| `--sensor-id`, `--sensor-mode` | Argus camera index and explicit mode; mode `-1` allows driver selection |
| `--width`, `--height`, `--fps` | Requested capture caps; FPS accepts `17`, `29.97` or `30000/1001` |
| `--output-width`, `--output-height` | Software resize after capture/optional rectification; both required together |
| `--publish-hz` | Maximum application processing/publication rate, at most requested sensor FPS |
| `--shutter-speed` | Reciprocal seconds: `1000` means 1/1000 s, converted to 1,000,000 ns for Argus |
| `--exposure-us` | Alternative fixed integration time in microseconds; `1000` also means 1/1000 s |
| `--exposure-min-us`, `--exposure-max-us` | Alternative AE exposure range; cannot combine with fixed exposure/shutter |
| `--gain` or `--gain-min`, `--gain-max` | Fixed or automatic-range sensor analog gain, as a scalar multiplier |
| `--digital-gain` or `--digital-gain-min`, `--digital-gain-max` | Fixed or range ISP digital gain, not dB |
| `--wb-mode`, `--ae-lock`, `--awb-lock` | Argus white-balance enum and AE/AWB locks; defaults auto WB, unlocked |
| `--exposure-compensation`, `--antibanding` | Argus compensation in stops and antibanding enum |
| `--tnr-mode`, `--tnr-strength`, `--ee-mode`, `--ee-strength` | Noise reduction and edge enhancement; strength `-1` leaves the plugin default |
| `--calibration` | ROS YAML, Kalibr YAML, `builtin:arducam_info.yaml`, `builtin:kalibr.yaml`, or `none` |
| `--calibration-roi X Y WIDTH HEIGHT` | Explicit crop region in reference calibration pixels, then resize to capture caps |
| `--rectify`, `--no-rectify`, `--rectify-alpha` | Correct distortion once, or retain raw pixels; alpha 0..1 controls rectified field of view |
| `--preview-width`, `--preview-height` | Optional ROS preview with its own correctly resized CameraInfo |
| `--image-format`, `--jpeg-quality`, `--save-interval-s` | PNG/JPEG recording and sampling interval; interval `0` saves each processed frame |
| `--read-timeout-s`, `--startup-timeout-s`, `--max-frames`, `--duration-s` | Failure bounds and optional run limits |

Unspecified gain/exposure (`0`) leaves those source ranges at driver defaults. Gain values
must be >=1 when supplied; exposure cannot exceed the requested frame period. Unsupported
sensor/driver limits may still reject or clip requests. Metadata separates requested
settings from actual exposure/gain, which this backend leaves **unknown** rather than
claiming they were achieved. Focus controls are not assumed for the selected M12 lens.

For example, capture at the historical mode but deliver 1920x1080 images with automatically
updated intrinsics, a 2 ms shutter and fixed gains:

```bash
uv run --no-project --python .venv-camera/bin/python python -m maritime_perception.adapters.image_grabber --adapter argus --width 3840 --height 2160 --output-width 1920 --output-height 1080 --fps 17 --publish-hz 4 --exposure-us 2000 --gain 2 --digital-gain 1 --wb-mode 6 --rectify --output simulation/logs/perception/camera-1080-output
```

Changing actual capture mode to 1920x1080 may change sensor crop/binning. A resolution
mismatch therefore requires either that mode's own calibration, `--calibration none`
for uncalibrated raw acquisition, or an explicitly verified reference ROI. For a measured
full-field resize of the old calibration, the declaration would be
`--width 1920 --height 1080 --calibration-roi 0 0 3840 2160`. Do not use that declaration
for a cropped sensor mode. Full 16 MP capture similarly needs a 4656x3496 calibration or
an established mode transform. Software output resizing does not require that assumption.

Raw images use raw K/D. Rectification computes new K, clears D and publishes `image_rect`;
it never labels corrected pixels as raw. Resize/crop transforms use OpenCV pixel centres.
The preview has its own K/P/dimensions. With `--calibration none`, CameraInfo K[0] is zero
and rectification is refused. The supplied historical P is never substituted for raw K.

### ROS publication and the processing boundary

After sourcing compatible ROS, append `--ros` to a capture command to publish
`/camera/image_raw` or `/camera/image_rect`, `/camera/camera_info` and
`/camera/frame_metadata`; optional preview topics are `/camera/preview/image` and
`/camera/preview/camera_info`. Image topics use best-effort depth 1. `--output` is optional
in ROS mode. `--ros-args` remappings can follow the capture arguments. Installed entry
point: `ros2 run maritime_perception image_grabber ... --ros`. A colcon launch is also
provided: `ros2 launch maritime_perception image_grabber.launch.py config:=/absolute/capture.json`.
The desktop ROS Docker candidate contains GI and software GStreamer plugins; it does not
provide a Jetson driver/Argus stack or imply a successful image build.

The backend uses GI/appsink directly instead of OpenCV VideoCapture, preserving buffer
PTS/running time, duration, negotiated caps and host arrival times while respecting row
stride. Each run gets a distinct source-clock ID. ROS image headers carry host arrival
time and explicitly matching metadata; they are **not verified exposure timestamps**.
`detections_to_frame` pairs an exact capture metadata record and restores its source PTS
instead of overwriting it with the detection header. Never pair with the latest metadata.

In-process capture returns `CapturedFrame.image`, `.camera_info` and `.metadata`;
`.detection_frame(origin_id)` supplies the existing detector/frame contract, including
image domain, effective calibration ID and an identity pixel transform. Detection can run
directly on these BGR pixels using the existing local-weights adapter. The geolocation
configuration must describe the same effective camera model and measured mount/uncertainty.

PTS is not automatically UTC, exposure midpoint or IMU time. The capture metadata retains
`stamp_semantics=gstreamer_running_time_unverified`; processing rejects it until SP-06
establishes clock mapping, exposure semantics/delay and rolling-shutter error treatment.
Actual exposure/gain and rolling-shutter readout remain unknown. No GPS output, guessed
mount/covariance or synthetic camera is substituted after hardware failure. Explicit
`--adapter videotest --calibration none --width 640 --height 480 --fps 10` is available
for a labeled software GStreamer smoke run, not camera or optical acceptance.

Primary control/runtime references:
[NVIDIA Argus/GStreamer](https://docs.nvidia.com/jetson/archives/r35.6.1/DeveloperGuide/SD/Multimedia/AcceleratedGstreamer.html),
[Arducam IMX519/Jetson modes](https://docs.arducam.com/Nvidia-Jetson-Camera/Nvidia-Jetson-Orin-Series/NVIDIA-Jetson-AGX-Orin/Quick-Start-Guide/),
[GStreamer appsink](https://gstreamer.freedesktop.org/documentation/app/appsink.html).
The product listing was not retrievable during review; no additional SKU compatibility
or field-of-view claim is inferred from it.

## Asynchronous testing and ROS 2 bags

The [completion plan](../docs/perception_reports/Maritime_Pipeline_Completion_Plan.docx)
now prioritizes one camera/pixel owner and one FCU/state/timing owner, with Samuel owning
geometry/acceptance and the SW/Gazebo lead supplying simulation/GCS interfaces. First
prove normalized message flow and explicit invalid-data handling; physical GPS accuracy
requires the later measured contracts. A raw IMU topic alone is not the navigation input.
Prefer the authoritative full FCU pose/velocity estimate when available rather than
building new raw IMU/GNSS fusion or blocking on the exact IMU/navigation join.

### Portable asynchronous smoke test

The installed `perception_async_test` command and module below feed the existing core in
arrival order. Frames wait in a bounded, timestamp-sorted queue for bracketing states;
missing future pose times out with diagnostics. There is no latest-pose fallback or
fixed-lag smoother. State samples remain ordered; late/duplicate states and frames are
rejected. A short reorder hold tolerates frame arrival reordering within that window.
Defaults of 0.5 s wait, 0.05 s reorder hold and 32 pending frames are test settings, not
measured deployment limits. The numerical core still enforces its own pose-gap policy.

After the standard uv setup, run from the repository root using new output directories:

```bash
uv run --no-project --python .venv/bin/python python -m perception_synthetic.demo --adapter synthetic --scenario analytic --output simulation/logs/perception/async-source
uv run --no-project --python .venv/bin/python python -m maritime_perception.async_test --session simulation/logs/perception/async-source/session --output simulation/logs/perception/async-normal --jitter-ms 8 --require-observations
uv run --no-project --python .venv/bin/python python -m maritime_perception.async_test --session simulation/logs/perception/async-source/session --output simulation/logs/perception/async-loss --drop-state-every 1 --require-observations
```

The last command intentionally exits nonzero: all states are removed, so no usable
observation may appear. Inspect `summary.json`, `diagnostics.jsonl`, `arrivals.jsonl`,
`reports.jsonl` and `observations.jsonl`. Seeded jitter is reproducible. Additional options
include `--frame-delay-ms`, `--state-delay-ms`, `--drop-frame-every`, `--seed`, `--wait-s`,
`--reorder-s` and `--max-pending`. The normal analytic run yielded 4 reports/12 observations,
zero pending frames and a 0.11 s maximum pose wait with the default 20/80 ms frame/state
delays. This is virtual-arrival software testing, not measured DDS or camera latency.

### Live ROS test endpoints

On a compatible sourced ROS host, the same script can listen to normalized
`std_msgs/String` events on `/drone/perception/input` and publish reports on
`/drone/perception/report`. Each input string contains the existing `{"kind":...,"data":...}`
envelope for `vehicle_state`, `imu_state` or `frame`. Separate source adapters publish
these records; the listener does not automatically convert arbitrary raw bags into GPS.
Use one authoritative state stream and exact image metadata pairing. Source clock
mappings and image exposure semantics must already be supplied for usable geolocation.

In two terminals, using the compatible ROS environment from the capture guide:

```bash
uv run --no-project --python .venv-camera/bin/python python -m maritime_perception.async_test --ros-live --config simulation/logs/perception/async-source/session/config.json --output simulation/logs/perception/async-ros --duration-s 30 --require-observations
uv run --no-project --python .venv-camera/bin/python python -m maritime_perception.async_test --ros-publish --session simulation/logs/perception/async-source/session --duration-s 20
```

The fixture publisher waits two seconds for discovery and sends synthetic normalized
inputs with controlled arrival delays. This can test real DDS wiring on your host before
hardware adapters exist. It preserves synthetic provenance. Native ROS execution has not
run here; endpoint lifecycle tests use doubles. The test node uses host timing for waits
and report publication, not a bag's wall-clock epoch; do not enable `use_sim_time` on this
test node. A Gazebo source adapter still must map its source clock explicitly. Historical
bag/fixture exposure-to-now age is not live sensor latency. Restart the test for a new
origin, estimator epoch or playback loop; already-processed history is never rewritten.

### First useful bag

Record 30 to 60 seconds on the bench with the camera and flight controller, then a
separate stationary/slow-motion sequence. Begin with a calibrated software output size
such as 1280x720 at 2 processed frames/s to keep raw BGR recording near 5.5 MB/s before
telemetry/serialization overhead. Full 3840x2160 BGR at 17 FPS is about 423 MB/s; measure
storage and drops before attempting it. Keep the primary image and its matching K/D,
not a preview substituted with full-resolution calibration.

Inventory actual names/types/QoS with `ros2 topic list -t` and `ros2 topic info -v TOPIC`.
Record the selected raw **or** rectified image, matching CameraInfo, frame metadata,
fused pose/velocity, IMU, available GNSS/estimator health, TF and normalized inputs/reports.
The following is an example only after confirming those names on the actual system:

```bash
ros2 bag record -s sqlite3 -o simulation/logs/perception/bench-bag --qos-profile-overrides-path drone/maritime_perception/config/rosbag_qos.yaml /camera/image_rect /camera/camera_info /camera/frame_metadata /mavros/imu/data /mavros/local_position/odom /tf /tf_static /drone/perception/input /drone/perception/report
```

Adapt the provided QoS file and add the actual health/GNSS topics. Check topic counts
and gaps after recording; QoS compatibility alone does not prove delivery. Record `/clock`
for a Gazebo bag, and use recorder `--use-sim-time` only for that intended clock domain
after `/clock` is active. Do not mix real-time and simulation bags into one session.
Stop cleanly so metadata is written. Keep the whole bag directory, metadata and every
split; a zipped directory is suitable to share along with config/calibration and versions.

The audit reports topic counts/bytes/rates, header gaps/duplicates/backwards times and
frame IDs. SQLite snapshots can be inspected read-only even if the uploaded directory
omits metadata. Complete directories check the declared splits, total and per-topic
counts/types, start/duration and per-file statistics; mismatches are rejected before
export. A standalone `.db3` is evidence only for that file if its manifest lists others.
`--counts-only` needs no ROS installation. Decoding uses the sourced native ROS/message
packages; unknown definitions retain byte/count statistics and increment decode errors.

```bash
uv run --no-project --python .venv-camera/bin/python python -m maritime_perception.adapters.rosbag_audit --bag simulation/logs/perception/bench-bag --output simulation/logs/perception/bench-bag-audit.json
ros2 bag info simulation/logs/perception/bench-bag
ros2 bag play simulation/logs/perception/bench-bag --rate 0.5 --topics /drone/perception/input
```

Start the ROS listener before the last command. It works only if normalized input events
are present in the bag; raw-only recordings need the students' adapters. Replay only
perception topics. Bag receive timestamps, ROS headers and camera PTS are distinct facts;
a bag does not establish exposure synchronization, origin, covariance, heading or height.
Preserve calibration/config files, camera control requests, runtime versions, mounting/
water measurements and annotation/reference data beside the bag. See the first real
recording below for observed flow and the remaining physical acceptance limits.

### Import the first hardware bag

The user supplied `hardware-bag-02.zip` on 8 November 2026. Its single SQLite database
passes integrity inspection and contains about 97.6 seconds of telemetry. It contains
47 rectified 1280x720 images, 62 CameraInfo records and 62 metadata records. Every
recorded image has a unique exact companion pair. Fifteen metadata records lack an
image; no cause is established by the bag. Metadata source spacing has a median
0.941 s (about 1.06 processed frames/s), below the requested 2 Hz. The initial ZIP omitted
`metadata.yaml`; the user subsequently supplied the matching version-5 manifest. Its
single declared file, 11,020 total messages, all 13 topic entries/counts/types, starting
time, 97.575138678 s duration and per-file statistics match the database. No additional
declared splits are missing. The image gap is already present in the recorded counts;
supplying the manifest does not recover the 15 absent images.

Keep `metadata.yaml` beside `hardware-bag-02_0.db3` in the bag directory. The audit now
hashes the manifest and reports `source.metadata_consistency_verified` and
`source.archive_completeness_verified` as true for this complete matching recording.
These refer to the declared archive, not lossless sensor delivery, calibration or
position accuracy. A single selected split of a multi-file bag retains false completion
flags; its counts are not compared with whole-bag totals. Partial old manifests with
missing statistics retain unknown consistency instead of gaining verification.

IMU and GNSS each have 1,952 messages and odometry has 1,951, at about 20 Hz.
The bag includes a latched GPS origin and three static MAVROS frame-convention
transforms, but no camera-mount transform. All 1,951 odometry pose/twist covariances
are zero. There are no identical IMU/odometry header stamps. This supports source
adapter and asynchronous replay development, not an exact-time IMU join or a verified
navigation error model. GPS-origin presence alone does not establish its relationship
to local `map`, camera offsets or the target-plane height.

Run from the repository root in the existing system-Python ROS environment. Choose
fresh output paths; no new packages beyond the existing ROS/project install are needed:

```bash
source /opt/ros/humble/setup.bash
export RUN=simulation/logs/perception/team-test-01
uv run --no-project --python .venv-ros/bin/python python -m maritime_perception.adapters.rosbag_audit \
  --bag "$RUN/hardware-bag-02" \
  --export-camera "$RUN/hardware-import-01" \
  --output "$RUN/hardware-bag-audit-01.json"
```

The export contains `images/`, `frames.jsonl`, raw `navigation.jsonl` and `audit.json`.
Frame records retain the original capture ID, source PTS/clock, ROS header, calibration,
requested controls and unverified exposure flags, plus exact CameraInfo and PNG SHA256.
Association uses exact `(ROS header nanoseconds, frame_id)` keys; missing, duplicate
or inconsistent companions are reported and excluded. It never pairs the latest metadata.
Supported image exports are BGR8, RGB8 and mono8, including padded rows.
Raw MAVROS/TF records retain their field names and receive timestamps. Nonfinite raw
sensor values become JSON null. This is an input dataset for annotation/detector and
source-adapter tests; it is not a normalized `config.json`/`measurements.jsonl` session.
It does not change clocks, assert calibration validity, invent covariance or emit GPS
tracks. Read `camera.exact_triplet_count`, `camera.metadata_without_image_count`,
`topics.*.decode_errors` and `navigation.zero_pose_covariance_count` in the audit.

For a desktop without ROS, inspect flow only (a `.db3` file path also works):

```bash
uv run --no-project --python .venv/bin/python python -m maritime_perception.adapters.rosbag_audit \
  --bag simulation/logs/perception/team-test-01/hardware-bag-02 --counts-only \
  --output simulation/logs/perception/team-test-01/hardware-bag-counts-01.json
```

The new exporter was exercised on the actual database using a portable Humble CDR
decoder: all messages decoded and 47 PNGs/checksums/source metadata were verified.
Production decoding still uses native ROS, not a new required decoder dependency.
All 182 drone tests pass on Python 3.10 and 3.12, including missing/duplicate companions,
split handling, metadata count/type/time mismatches, padded RGB export, typed ROS
sequences and retained unknown covariance.
Native CLI/export execution on the Jetson remains to be checked by the team.

The image publisher now uses `array('B')` for ROS Image data. Humble's generated
uint8-sequence setter accepts this directly, avoiding Python per-byte validation for
each full-resolution and preview message. Desktop checks preserve byte content; only
a new Jetson run can establish rate/delivery improvement. This does not establish the
cause of the 15 missing bag images. To isolate preview overhead during that run, add
`--preview-width 0 --preview-height 0` to the capture command. The existing source
resolution, output resolution, FPS, shutter/exposure and gain options remain available.

Student A can annotate measured target points in these exported images immediately.
Student B can inspect raw navigation timing/origin/covariance without recapturing data.
Samuel/HW must provide camera-to-body rotation/translation, measured lens-to-target
height, target dimensions and applicable lens/mode calibration. Exposure-clock mapping
and a justified navigation/shared-error model are still needed for physical ENU/GPS
reports. Arrival-header odometry brackets in the audit are diagnostic, not exposure
synchronization. Do not independently fuse correlated IMU, odometry and GNSS outputs.

Primary references: [ROS 2 rosbag2 recording QoS and clocks](https://github.com/ros2/rosbag2),
[native Python reader example](https://github.com/ros2/rosbag2/tree/jazzy/rosbag2_examples/rosbag2_examples_py).

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

Camera integration (2026-11-08): 147 drone tests pass, including 43 new camera cases,
and 11 existing GCS workspace tests pass. Tests compare the imported models, raw versus
rectified rays, explicit mode transforms, pixel-centre resizing/preview, control units
and conflicts, padded buffers, source timestamps, recording round trips and errors,
GStreamer startup/read failures and ROS publication/shutdown. Camera/GStreamer/ROS tests
use doubles: no native GI/GStreamer, Argus, actual ROS/DDS, Jetson or camera trial ran.
The installed package was also exercised outside the checkout: packaged ROS/Kalibr
calibration loading, configurable dry run, command registration and explicit missing-GI
failure pass. Python/XML/local-link checks and strict shell syntax pass.
The hardware/runtime/calibration checks in the capture guide remain necessary.

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
