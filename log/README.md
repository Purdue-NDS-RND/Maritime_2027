# MAVROS IMU recording and perception integration

The five IMU commits `22dc30e` through `e2e25fe` added a useful formatter/listener/output
split, but the original CSV dropped quaternion, frame, covariance and exact timestamps.
It also treated unreported ROS measurements as valid and referenced absent startup scripts.
The maintained implementation now lives in `drone/maritime_perception/adapters/imu_*.py`.
`log/` retains compatibility imports; `__init__.py` replaces the misspelled `init.py`.
Install the drone package first. The installed listener also works outside the checkout.

| Component | Purpose |
| --- | --- |
| `imu_formatter` | Validated IMU record, exact nanoseconds, quaternion and covariance; degrees only for display |
| `imu_output` | Throttled terminal, CSV, replayable JSONL, optional processing callback |
| `imu_listener` | Read-only ROS 2 subscriber with sensor-data QoS and explicit rejected-message diagnostics |
| `imu_input.PipelineImuSink` | Connect samples and a verified same-time navigation provider to the processing core |
| `imu_session` | Join recorded IMU and same-time navigation; feed the existing replay CLI |

No IMU-only GPS estimate is produced. Accelerations are not integrated into position.
The same flight-controller estimate is not fused twice as independent data.

## Portable setup and checks

From the repository root, follow [drone setup](../drone/README.md#setup-and-deterministic-demonstrations)
using uv and Python 3.12. Then run:

```bash
uv run --no-project --python .venv/bin/python python -m pytest -q drone/tests/test_imu.py
```

These tests use structural ROS message doubles, not a running ROS/DDS system or FCU.

## Record actual MAVROS messages

MAVROS and the FCU connection must already be configured on the host. This repository
does **not** contain `mavros_boot.sh` or `check_streams.sh`; use the team's actual host
setup. This listener does not configure message rates, arm, command or launch the vehicle.

Use a compatible ROS environment whose Python meets the drone package's >=3.11 requirement.
The exercised portable runtime is Python 3.12; Humble/Jetson compatibility is unverified.
For a Jazzy host, use its system Python so binary `rclpy` can be imported:

```bash
source /opt/ros/jazzy/setup.bash
uv venv --python /usr/bin/python3 --system-site-packages .venv-ros
uv pip install --python .venv-ros/bin/python -r drone/requirements.txt -e ./drone
ros2 topic list -t
ros2 topic info -v /mavros/imu/data
ros2 topic hz /mavros/imu/data
mkdir -p simulation/logs/perception/imu
uv run --no-project --python .venv-ros/bin/python python -m maritime_perception.adapters.imu_listener --ros-args -p jsonl_path:=simulation/logs/perception/imu/samples.jsonl -p csv_path:=simulation/logs/perception/imu/samples.csv
```

Use a new recording filename each run. Existing files are refused, not truncated.
Parent directories must exist; write failures are visible. Ctrl+C closes both files.
`uv run --no-project --python .venv-ros/bin/python python -m log.imu_listener` is the
checkout compatibility entry point. `ros2 run maritime_perception perception_imu` is
available after a compatible colcon build (not executed here).

| Parameter | Default | Meaning |
| --- | --- | --- |
| `topic` | `/mavros/imu/data` | Fused attitude stream; verify the actual namespace |
| `jsonl_path` | empty | Versioned `maritime.imu_sample` records for processing |
| `csv_path` | empty | Diagnostic CSV; original ten columns retained with exact fields appended |
| `print_period_s` | `1.0` | Terminal interval; `0.0` disables printing |

Rates depend on FCU/MAVROS configuration; 20 Hz is not guaranteed. In a verified FLU
frame, available accelerometer specific force is about +9.81 m/s² on Z at rest and level.
The fused topic may carry cached acceleration from a different message; its header does
not establish separate accelerometer sample time. Acceleration is diagnostic only here.
An absent field (`covariance[0] == -1`) stays unavailable; all-zero covariance stays unknown.
Unknown-covariance values may be displayed/recorded but are refused by the geolocation bridge.
Euler yaw is ROS mathematical yaw in degrees, not a certified compass/true-north bearing.

## Connect to geolocation

Follow [the integration contract and replay commands](../drone/README.md#imu-input-and-navigation-integration).
MAVROS already converts FCU NED/FRD data to ENU/FLU on the fused IMU topic; do not apply
that conversion again. The actual installed source, body alignment, north reference,
clock behavior and covariance model still require measurement/verification.

Primary references checked during review:
[ROS Imu definition](https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/msg/Imu.msg),
[MAVROS IMU plugin](https://github.com/mavlink/mavros/blob/ros2/mavros/src/plugins/imu.cpp), and
[MAVROS IMU parameters](https://github.com/mavlink/mavros/blob/ros2/docs/plugins/std/imu.md).
Plugin covariance parameters are configured assumptions, not measured accuracy certificates.
