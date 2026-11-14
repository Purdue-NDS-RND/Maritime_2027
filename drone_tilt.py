"""Read-only Maritime bench diagnostic for live MAVROS or navigation.jsonl.

With no arguments, listen for live MAVROS IMU data. The incoming quaternion
is assumed to rotate the selected ROS body frame (x forward, y left, z up) into a Z-up reference.
Verify that the reported body axes match the physical rig before using labels.
"""

import argparse
import json
import math
from pathlib import Path
import sys
import time

IMU_TOPIC = "/mavros/imu/data"
ODOM_TOPIC = "/mavros/local_position/odom"
AXES = ("x", "y", "z", "w")


def attitude(quaternion, deadband_deg):
    """Give signed orientation and report the physical low sides of the body."""
    norm = math.hypot(*quaternion)
    if not math.isfinite(norm) or abs(norm - 1.0) > 0.01:
        raise ValueError("invalid quaternion (expected a finite, near-unit x,y,z,w)")
    x, y, z, w = (component / norm for component in quaternion)

    # World Z components of the body forward, left and up axes (matrix row 3).
    forward_z = 2 * (x * z - w * y)
    left_z = 2 * (y * z + w * x)
    up_z = 1 - 2 * (x * x + y * y)

    pitch_deg = math.degrees(math.atan2(-forward_z, math.hypot(left_z, up_z)))
    tilt_deg = math.degrees(math.atan2(math.hypot(forward_z, left_z), up_z))
    # At vertical pitch there is no unique Euler roll or yaw.
    roll_deg = yaw_deg = None
    if math.hypot(left_z, up_z) > 1e-8:
        roll_deg = math.degrees(math.atan2(left_z, up_z))
        yaw_deg = math.degrees(math.atan2(2 * (x * y + w * z), 1 - 2 * (y * y + z * z)))

    if up_z <= 1e-8:
        direction = "vertical or inverted"
    elif tilt_deg <= deadband_deg:
        direction = "level"
    else:
        # In body coordinates, (-forward_z, -left_z) points downhill.
        bearing = math.degrees(math.atan2(-left_z, -forward_z)) % 360
        sectors = ("nose down", "nose and left low", "left side low", "tail and left low",
                   "nose up", "tail and right low", "right side low", "nose and right low")
        direction = sectors[int((bearing + 22.5) // 45) % len(sectors)]

    return dict(roll_deg=roll_deg, pitch_deg=pitch_deg, yaw_deg=yaw_deg,
                tilt_deg=tilt_deg, direction=direction)


def make_sample(args, quaternion, covariance, stamp_ns, body_frame,
                reference_frame=None, bag_receive_ns=None):
    if body_frame != args.body_frame:
        raise ValueError(f"expected body frame {args.body_frame!r}, got {body_frame!r}")
    if args.source == "imu" and covariance[0] == -1:
        raise ValueError("IMU reports orientation unavailable")
    result = attitude(quaternion, args.deadband_deg)
    return dict(
        topic=args.topic,
        stamp_ns=stamp_ns,
        bag_receive_ns=bag_receive_ns,
        body_frame=body_frame,
        reference_frame=reference_frame,
        quaternion_xyzw=quaternion,
        covariance_reported_nonzero=any(covariance),
        **result,
    )


def display(sample, jsonl):
    if jsonl:
        print(json.dumps(sample, allow_nan=False), flush=True)
        return

    def signed_angle(name):
        value = sample[name]
        return "undefined" if value is None else f"{value:+.1f}°"

    print(f"{sample['stamp_ns']}  {sample['direction']:<21} "
          f"tilt={sample['tilt_deg']:.1f}°  roll={signed_angle('roll_deg')}  "
          f"pitch={signed_angle('pitch_deg')}  yaw={signed_angle('yaw_deg')}",
          flush=True)


def read_export(args):
    valid = skipped = 0
    with args.nav_jsonl.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record["topic"] != args.topic:
                    continue
                msg = record["message"]
                header = msg["header"]
                stamp = header["stamp"]
                stamp_ns = stamp["sec"] * 1_000_000_000 + stamp["nanosec"]
                if args.source == "imu":
                    orientation, covariance = msg["orientation"], msg["orientation_covariance"]
                    body_frame, reference_frame = header["frame_id"], None
                else:
                    pose = msg["pose"]
                    orientation, covariance = pose["pose"]["orientation"], pose["covariance"]
                    body_frame, reference_frame = msg["child_frame_id"], header["frame_id"]
                sample = make_sample(
                    args, [orientation[axis] for axis in AXES], covariance, stamp_ns,
                    body_frame, reference_frame, record.get("bag_receive_ns"),
                )
            except (ValueError, KeyError, IndexError, TypeError) as error:
                skipped += 1
                print(f"Line {line_number}: {error}", file=sys.stderr)
                continue

            display(sample, args.jsonl)
            valid += 1

    print(f"{args.topic}: {valid} valid samples, {skipped} skipped", file=sys.stderr)
    return 0 if valid else 1


def listen(args):
    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Imu
    except ImportError:
        print("Live mode needs ROS 2 Humble sourced and the Jetson's ROS Python environment.",
              file=sys.stderr)
        return 1

    last_valid = time.monotonic()
    next_display = last_valid
    last_error = None

    def on_message(msg):
        nonlocal last_valid, next_display, last_error
        if args.source == "imu":
            q, covariance = msg.orientation, msg.orientation_covariance
            body_frame, reference_frame = msg.header.frame_id, None
        else:
            q, covariance = msg.pose.pose.orientation, msg.pose.covariance
            body_frame, reference_frame = msg.child_frame_id, msg.header.frame_id

        stamp = msg.header.stamp
        try:
            sample = make_sample(
                args, [getattr(q, axis) for axis in AXES], covariance,
                stamp.sec * 1_000_000_000 + stamp.nanosec, body_frame, reference_frame,
            )
        except ValueError as error:
            if str(error) != last_error:
                last_error = str(error)
                print(f"Skipping sample: {last_error}", file=sys.stderr)
            return

        last_valid = time.monotonic()
        last_error = None
        if last_valid >= next_display:
            display(sample, args.jsonl)
            next_display = last_valid + (0 if args.jsonl else 0.5)

    from rclpy.executors import ExternalShutdownException

    rclpy.init()
    node = None
    try:
        node = rclpy.create_node("drone_tilt_check")
        message_type = Imu if args.source == "imu" else Odometry
        node.create_subscription(message_type, args.topic, on_message, qos_profile_sensor_data)
        print(f"Listening on {args.topic} (Ctrl+C to stop)", file=sys.stderr)
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
            if time.monotonic() - last_valid >= 10:
                print(f"No valid samples on {args.topic} for 10 seconds.", file=sys.stderr)
                return 1
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nav-jsonl", type=Path, help="Read the Maritime export instead of live ROS.")
    parser.add_argument("--source", choices=("imu", "odom"), default="imu",
                        help="Orientation source (default: imu).")
    parser.add_argument("--topic", help="Override the MAVROS topic for the chosen source.")
    parser.add_argument("--body-frame", default="base_link",
                        help="Expected ROS body frame with verified FLU axes (default: base_link).")
    parser.add_argument("--deadband-deg", type=float, default=3.0,
                        help="Tilt at or below this angle is displayed as level (default: 3).")
    parser.add_argument("--jsonl", action="store_true",
                        help="Write every valid sample as timestamped JSON to standard output.")
    args = parser.parse_args()
    if not 0 <= args.deadband_deg < 90:
        parser.error("--deadband-deg must be at least 0 and below 90")
    if args.topic is None:
        args.topic = IMU_TOPIC if args.source == "imu" else ODOM_TOPIC

    if args.nav_jsonl is None:
        return listen(args)
    try:
        return read_export(args)
    except OSError as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
