# Maritime Student B progress — November 14, 2026

## What we completed

- Installed ROS 2 Jazzy Base on Ubuntu 24.04. Verified that `ROS_DISTRO` reported `jazzy` and that ROS could display the `sensor_msgs/msg/Imu` message definition.
- Installed MAVROS and verified that ROS found it under `/opt/ros/jazzy`. The ArduPilot launch file, `apm.launch`, listed its arguments, including `fcu_url` and `tgt_system`.
- Reviewed CUASC’s [MAVROS boot script](https://github.com/Purdue-NDS-RND/CUASC_2026/blob/main/mavros_boot.sh), [stream-rate script](https://github.com/Purdue-NDS-RND/CUASC_2026/blob/main/set_stream_rate.sh), and [stream checker](https://github.com/Purdue-NDS-RND/CUASC_2026/blob/main/check_mavros_streams.sh) for the Pixhawk setup.
- Encountered a serial-port permission error on `/dev/ttyACM0`. The troubleshooting step was to check the device’s group and, if it was `dialout`, add the Ubuntu user to that group and log out and back in.
- Created and checked [`drone_tilt.py`](https://github.com/Purdue-NDS-RND/Maritime_2027/blob/feature/cv-raycast/drone_tilt.py) with synthetic orientation samples and offline input examples. The first Git push was rejected because the remote branch had newer work. After syncing the branch, we verified that the script was on GitHub in `feature/cv-raycast`.

A successful live Pixhawk connection and matching physical tilt readings still need to be recorded. The ROS and MAVROS installation checks establish that the software is available.

## What the tilt script measures

The script reads the Pixhawk’s estimated orientation from `/mavros/imu/data` and converts its quaternion into roll, pitch, yaw, and total tilt in degrees. It labels directions such as `nose down` and `right side low`, and uses a 3° level threshold by default. It also accepts a saved Maritime `navigation.jsonl` export. Use `--source odom` to inspect fused odometry separately or `--jsonl` to save timestamped output with the original quaternions.

For the bench test, mark the forward, left, and up axes of the temporary setup. MAVROS applies the flight controller-to-ROS conversion. With correctly aligned body axes, lowering the nose should give positive pitch and lowering the right side should give positive roll. Repeat the direction checks after the final Pixhawk mount is installed. [MAVROS coordinate frames](https://github.com/mavlink/mavros/blob/ros2/docs/frames.md) · [ROS axis conventions](https://github.com/ros-infrastructure/rep/blob/master/rep-0103.rst)

## Reproduce the live bench check

Use the Pixhawk disarmed. If it runs ArduPilot and the CUASC USB settings match your setup, start MAVROS in one terminal. This launch uses system ID `1` by default. Verify the device path and current system ID if it fails to connect.

```bash
source /opt/ros/jazzy/setup.bash
ros2 launch mavros apm.launch fcu_url:=/dev/ttyACM0:115200
```

Leave MAVROS running and open a second terminal.

```bash
source /opt/ros/jazzy/setup.bash
timeout 10s ros2 topic echo /mavros/state --once --qos-reliability best_effort
timeout 10s ros2 topic echo /mavros/imu/data --once --qos-reliability best_effort
```

Look for `connected: true`, `armed: false`, and an IMU sample with an orientation quaternion. If connected and the IMU topic is silent, try CUASC’s `set_stream_rate.sh` and check the topic again. The full CUASC checker also checks local pose and landed state.

```bash
cd ~/Maritime_2027
uv run --no-project --python /usr/bin/python3 python drone_tilt.py
```

Hold the setup level, then lower the nose, tail, right side, and left side one at a time. Save the observed labels and angles as evidence for the temporary setup.

## What remains for Student B

| Check | Evidence still needed |
| --- | --- |
| Live navigation (Section 24) | Record the Pixhawk model and firmware, GNSS receiver, working launch settings, and samples for IMU, fused odometry, GNSS, origin, and time sync. |
| Frames and resets (Section 11) | Verify the drone body axes, how MAVROS `map` aligns to survey east/north/up, what defines the origin and heading, and what changes after a reconnect. Identify the position reference point and altitude datum. |
| Final mounting (Sections 14–15) | With HW and Samuel, measure the camera rotation, camera and antenna offsets from the body reference, and lens height above the target plane. The final mounting positions are open. |
| Image timing (Section 12) | Measure when the camera exposed each image in the navigation clock. The walkthrough reports zero verified exposure times in the saved run. |
| Pose uncertainty (Section 13) | Establish the fused pose’s uncertainty using independent measurements. The walkthrough reports 2,382 odometry samples with all-zero covariance, so it remains unknown from that run. |
| Measured replay (Sections 16–18) | Convert verified fused odometry into the survey frame and pair it with the camera geometry and exposure timing for the replay with Student A and Samuel. |

For buoy geolocation, the coordinate chain runs from the camera optical frame to the drone body frame and then into the survey frame using the drone pose at exposure time. The bench test can verify how the reported attitude responds to physical movement while the camera mount and survey alignment are still open.
