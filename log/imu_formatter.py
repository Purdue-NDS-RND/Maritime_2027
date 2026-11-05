"""Turn raw MAVROS IMU messages into clean, easy-to-use data.

This file has NO ROS imports, so it can be imported and tested anywhere.
The ROS-specific part lives in imu_listener.py.
"""

import math
from dataclasses import dataclass

# Column order used for CSV output (and the order of fields in ImuSample).
CSV_FIELDS = ["t", "ax", "ay", "az", "gx", "gy", "gz", "roll", "pitch", "yaw"]


@dataclass(frozen=True)
class ImuSample:
    """One cleaned-up IMU reading."""

    t: float      # timestamp in seconds (from the message header)
    ax: float     # linear acceleration, m/s^2 (z is about 9.8 at rest because of gravity)
    ay: float
    az: float
    gx: float     # angular velocity (rotation rate), rad/s
    gy: float
    gz: float
    roll: float   # orientation, degrees
    pitch: float
    yaw: float


def quaternion_to_euler_deg(x, y, z, w):
    """Convert a quaternion into (roll, pitch, yaw) in degrees.

    Quaternions are how ROS stores orientation, but they are hard for
    humans to read. Roll/pitch/yaw angles are much easier to understand.
    """
    # Roll: rotation around the x-axis
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))

    # Pitch: rotation around the y-axis (clamped to avoid math errors near +/-90 deg)
    sin_pitch = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    pitch = math.asin(sin_pitch)

    # Yaw: rotation around the z-axis (heading)
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def from_imu_msg(msg):
    """Build an ImuSample from a sensor_msgs/msg/Imu message."""
    stamp = msg.header.stamp
    a = msg.linear_acceleration
    g = msg.angular_velocity
    q = msg.orientation

    roll, pitch, yaw = quaternion_to_euler_deg(q.x, q.y, q.z, q.w)

    return ImuSample(
        t=stamp.sec + stamp.nanosec * 1e-9,
        ax=a.x, ay=a.y, az=a.z,
        gx=g.x, gy=g.y, gz=g.z,
        roll=roll, pitch=pitch, yaw=yaw,
    )


def format_line(s):
    """One human-readable line, good for printing or logging."""
    return (
        f"t={s.t:.3f}s | "
        f"accel [m/s^2] x={s.ax:+6.2f} y={s.ay:+6.2f} z={s.az:+6.2f} | "
        f"gyro [rad/s] x={s.gx:+6.3f} y={s.gy:+6.3f} z={s.gz:+6.3f} | "
        f"roll={s.roll:+7.2f} pitch={s.pitch:+7.2f} yaw={s.yaw:+7.2f} deg"
    )


def to_csv_row(s):
    """The sample as a list of values, in CSV_FIELDS order."""
    return [f"{getattr(s, name):.6f}" for name in CSV_FIELDS]
