# log/: IMU data pipeline

Reads IMU data from MAVROS, cleans it up, and sends it to the terminal and/or a CSV file.

```
/mavros/imu/data ──► imu_listener.py ──► imu_formatter.py ──► imu_output.py ──► terminal / CSV / memory
                     (receives)          (cleans)             (decides where it goes)
```

| File | Job | Needs ROS? |
|---|---|---|
| `imu_listener.py` | ROS 2 node. Subscribes to `/mavros/imu/data` and passes each message along. | Yes |
| `imu_formatter.py` | Converts a raw IMU message into a clean `ImuSample` (accel, gyro, roll/pitch/yaw in degrees). | No |
| `imu_output.py` | Sends each `ImuSample` to its destinations: terminal (throttled), CSV, and `latest`. | No |

All commands below are run from the **repo root**, the folder that *contains* `log/`.

---

## 1. Quick check (no ROS, no drone)

This confirms the formatter and output files work using a fake IMU message:

```bash
python3 -c "
from types import SimpleNamespace as N
from log.imu_formatter import from_imu_msg
from log.imu_output import ImuOutput
msg = N(header=N(stamp=N(sec=1, nanosec=0)),
        linear_acceleration=N(x=0.0, y=0.0, z=9.81),
        angular_velocity=N(x=0.0, y=0.0, z=0.0),
        orientation=N(x=0.0, y=0.0, z=0.7071068, w=0.7071068))
out = ImuOutput()
out.handle(from_imu_msg(msg))
print('OK: formatter + output working')
"
```

**Expected output:**
```
t=1.000s | accel [m/s^2] x= +0.00 y= +0.00 z= +9.81 | gyro [rad/s] x=+0.000 y=+0.000 z=+0.000 | roll=  +0.00 pitch=  +0.00 yaw= +90.00 deg
OK: formatter + output working
```

---

## 2. Full check (live data through MAVROS)

### Prerequisites
- ROS 2 with MAVROS installed.
- In **every new terminal**, load ROS first:
  ```bash
  source /opt/ros/<distro>/setup.bash   # run `ls /opt/ros` to find <distro> (e.g. humble, jazzy)
  ```
- Something for MAVROS to talk to:
  - **Simulation:** the ArduPilot simulator (SITL) must already be running.
  - **Real drone:** flight controller plugged in over USB.

### Terminal 1: start MAVROS (leave running)
```bash
./mavros_boot.sh sim        # or: ./mavros_boot.sh device
```

### Terminal 2: set stream rates and check topics
```bash
./check_streams.sh          # replace with the stream-check script's actual filename
```
Wait for:
```
[PASS] ✅ All required MAVROS streams are live
```
If any line shows ❌, fix that before continuing.

### Terminal 3: run the IMU listener
```bash
python3 -m log.imu_listener
```
**Expected:** one clean line of IMU data printed about once per second. When the drone is sitting still and level, `az` should be about **+9.81** (gravity), and roll and pitch should be about **0**.

To also save every sample to a CSV:
```bash
python3 -m log.imu_listener --ros-args -p csv_path:=log/imu_log.csv
```
Stop with **Ctrl+C**. The CSV is closed automatically. Check it with:
```bash
head log/imu_log.csv
```

### Optional parameters
| Parameter | Default | Meaning |
|---|---|---|
| `topic` | `/mavros/imu/data` | IMU topic to subscribe to |
| `csv_path` | `""` (off) | File to save every sample to |
| `print_period_s` | `1.0` | Seconds between terminal prints (`0` = don't print) |

Example: `python3 -m log.imu_listener --ros-args -p print_period_s:=0.2`

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `No module named 'log'` | Running from the wrong folder | `cd` to the folder that contains `log/` |
| `No module named 'rclpy'` / `ros2: command not found` | ROS not loaded in this terminal | Run the `source` command above |
| `Permission denied` on a `.sh` file | Script not executable | `chmod +x *.sh` |
| Listener runs but prints nothing | MAVROS not running, stream rates not set, or no sim/drone | Redo Terminals 1–2; check `ros2 topic hz /mavros/imu/data` |
| `ros2 topic echo` shows data but the listener doesn't | QoS mismatch | The listener must use `qos_profile_sensor_data` (it does by default) |

Useful commands while everything is running:
```bash
ros2 node list                      # should show /mavros and /imu_listener
ros2 topic hz /mavros/imu/data      # should be ~20 Hz
ros2 topic info /mavros/imu/data    # Subscription count ≥ 1 when the listener is running
```
