"""Lossless IMU records and human-readable diagnostics, without ROS imports."""
import json
import math
from dataclasses import dataclass
from types import SimpleNamespace as NS

from ..validation import Unavailable, array, covariance, rotation, timestamp
from .ros_conversion import ros_stamp_ns


CSV_FIELDS = ["t", "ax", "ay", "az", "gx", "gy", "gz", "roll", "pitch", "yaw",
              "stamp_ns", "frame_id", "quaternion_xyzw", "orientation_covariance",
              "angular_velocity_covariance", "linear_acceleration_covariance"]


def quaternion_to_euler_deg(x, y, z, w):
    x, y, z, w = rotation([x, y, z, w]).as_quat()
    roll = math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y))
    pitch = math.asin(max(-1., min(1., 2*(w*y-z*x))))
    yaw = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
    return tuple(math.degrees(a) for a in (roll, pitch, yaw))


def _measurement(value, cov, size, name):
    raw_cov = array(cov, (9,), name + "_covariance")
    if raw_cov[0] == -1:
        return None, None
    measured = array(value, (size,), name)
    # All-zero covariance means unknown, not a perfect measurement.
    checked = covariance(raw_cov.reshape(3, 3), 3, name + "_covariance")
    return tuple(measured), tuple(raw_cov) if checked.any() else None


@dataclass(frozen=True)
class ImuSample:
    stamp_ns: int
    frame_id: str
    quaternion_xyzw: tuple | None
    linear_acceleration: tuple | None
    angular_velocity: tuple | None
    orientation_covariance: tuple | None
    angular_velocity_covariance: tuple | None
    linear_acceleration_covariance: tuple | None

    @property
    def t(self):
        """Display only; use stamp_ns for alignment and serialization."""
        return self.stamp_ns * 1e-9

    @property
    def euler_deg(self):
        return (None, None, None) if self.quaternion_xyzw is None else quaternion_to_euler_deg(*self.quaternion_xyzw)

    ax = property(lambda s: None if s.linear_acceleration is None else s.linear_acceleration[0])
    ay = property(lambda s: None if s.linear_acceleration is None else s.linear_acceleration[1])
    az = property(lambda s: None if s.linear_acceleration is None else s.linear_acceleration[2])
    gx = property(lambda s: None if s.angular_velocity is None else s.angular_velocity[0])
    gy = property(lambda s: None if s.angular_velocity is None else s.angular_velocity[1])
    gz = property(lambda s: None if s.angular_velocity is None else s.angular_velocity[2])
    roll = property(lambda s: s.euler_deg[0])
    pitch = property(lambda s: s.euler_deg[1])
    yaw = property(lambda s: s.euler_deg[2])

    def to_record(self):
        return dict(schema="maritime.imu_sample", version=1,
                    **{name: getattr(self, name) for name in self.__dataclass_fields__})

    @classmethod
    def from_record(cls, data):
        if data.get("schema") != "maritime.imu_sample" or data.get("version") != 1:
            raise Unavailable("unsupported_imu_record")
        stamp_ns = timestamp(data["stamp_ns"])
        def vector(key, size):
            value = data[key]
            return [0.] * size if value is None else array(value, (size,), key).tolist()
        def cov(key, value_key):
            value = data[key]
            if value is not None:
                if data[value_key] is None:
                    raise Unavailable("covariance_without_imu_measurement")
                return value
            return [-1.] + [0.] * 8 if data[value_key] is None else [0.] * 9
        q, a, g = vector("quaternion_xyzw", 4), vector("linear_acceleration", 3), vector("angular_velocity", 3)
        return from_imu_msg(NS(header=NS(stamp=NS(sec=stamp_ns//10**9, nanosec=stamp_ns%10**9), frame_id=data["frame_id"]),
                               orientation=NS(**dict(zip("xyzw", q))),
                               linear_acceleration=NS(**dict(zip("xyz", a))),
                               angular_velocity=NS(**dict(zip("xyz", g))),
                               orientation_covariance=cov("orientation_covariance", "quaternion_xyzw"),
                               angular_velocity_covariance=cov("angular_velocity_covariance", "angular_velocity"),
                               linear_acceleration_covariance=cov("linear_acceleration_covariance", "linear_acceleration")))


def from_imu_msg(msg):
    frame = msg.header.frame_id
    if not isinstance(frame, str) or not frame:
        raise Unavailable("missing_imu_frame")
    q = msg.orientation
    q, cq = _measurement([q.x, q.y, q.z, q.w], msg.orientation_covariance, 4, "orientation")
    if q is not None:
        rotation(q)
    a, g = msg.linear_acceleration, msg.angular_velocity
    a, ca = _measurement([a.x, a.y, a.z], msg.linear_acceleration_covariance, 3, "acceleration")
    g, cg = _measurement([g.x, g.y, g.z], msg.angular_velocity_covariance, 3, "angular_velocity")
    return ImuSample(timestamp(ros_stamp_ns(msg.header.stamp)), frame, q, a, g, cq, cg, ca)


def format_line(s):
    def display(value):
        return "unavailable" if value is None else f"{value:+.3f}"
    return (f"stamp_ns={s.stamp_ns} frame={s.frame_id} | accel [m/s^2] "
            + ",".join(display(v) for v in (s.ax, s.ay, s.az)) + " | gyro [rad/s] "
            + ",".join(display(v) for v in (s.gx, s.gy, s.gz)) + " | rpy [deg] "
            + ",".join(display(v) for v in s.euler_deg))


def to_csv_row(s):
    def encode(name):
        value = getattr(s, name)
        if value is None:
            return ""
        return json.dumps(value, allow_nan=False) if isinstance(value, tuple) else value
    return [encode(name) for name in CSV_FIELDS]
