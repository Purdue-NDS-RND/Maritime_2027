"""Read actual camera/MAVROS topics and report source flow without inventing GPS tracks."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shlex
import time

import numpy as np

from ..replay import line, write_json
from ..validation import Unavailable
from .hardware_topics import load_profile, profile_assessment, recorder_arguments, ros_qos
from .rosbag_audit import CameraAudit, header_key, plain


class SourceMonitor:
    def __init__(self, profile, *, max_camera_keys=256):
        if type(max_camera_keys) is not int or not 2 <= max_camera_keys <= 4096:
            raise Unavailable("invalid_source_monitor_capacity")
        self.profile, self.max_keys = profile, max_camera_keys
        self.camera = CameraAudit(profile)
        self.evicted = 0
        self.duplicate_records_discarded = 0
        self.quality = Counter()
        self.latest_origin = self.latest_timesync = None
        self.static_children = set()
        self.topics = {item["topic"]: dict(type=item["type"], count=0, first_receive_ns=None,
            last_receive_ns=None, frame_ids=[], child_frame_ids=[], header_count=0,
            header_duplicates=0, header_backwards=0, decode_errors=0) for item in profile["roles"].values()}

    def observe(self, role, message, received_ns):
        item = self.profile["roles"][role]
        topic = self.topics[item["topic"]]
        topic["count"] += 1
        if topic["first_receive_ns"] is None:
            topic["first_receive_ns"] = received_ns
        topic["last_receive_ns"] = received_ns
        try:
            if hasattr(message, "header"):
                stamp, frame = header_key(message)
                old = topic.get("last_header_ns")
                topic["header_duplicates"] += old is not None and stamp == old
                topic["header_backwards"] += old is not None and stamp < old
                topic["last_header_ns"] = stamp
                topic["header_count"] += 1
                if frame not in topic["frame_ids"] and len(topic["frame_ids"]) < 20:
                    topic["frame_ids"].append(frame)
            if hasattr(message, "child_frame_id") and message.child_frame_id not in topic["child_frame_ids"]:
                if len(topic["child_frame_ids"]) < 20:
                    topic["child_frame_ids"].append(message.child_frame_id)
            self.camera.add(item["topic"], message)
            for index in (self.camera.images, self.camera.infos, self.camera.metadata):
                # Retain two copies to keep a duplicate key ambiguous, while a
                # stuck/repeated header cannot grow one cache entry indefinitely.
                for key, values in index.items():
                    if len(values) > 2:
                        self.duplicate_records_discarded += len(values)-2
                        index[key] = values[:2]
                while len(index) > self.max_keys:
                    del index[next(iter(index))]
                    self.evicted += 1
            if role == "odometry":
                self.quality["odometry_samples"] += 1
                self.quality["zero_pose_covariance"] += not any(message.pose.covariance)
                self.quality["zero_twist_covariance"] += not any(message.twist.covariance)
            elif role == "imu":
                q = message.orientation
                values = np.asarray([q.x, q.y, q.z, q.w])
                self.quality["invalid_imu_quaternion"] += not (np.all(np.isfinite(values)) and abs(np.linalg.norm(values)-1) < .01)
            elif role == "gnss":
                self.quality["gnss_no_fix"] += message.status.status < 0
            elif role == "fcu_state":
                self.quality["fcu_disconnected_samples"] += not message.connected
            elif role == "gps_origin":
                self.latest_origin = plain(message)
            elif role == "timesync":
                self.latest_timesync = plain(message)
            elif role == "tf_static":
                for transform in message.transforms:
                    if len(self.static_children) < 100:
                        self.static_children.add(transform.child_frame_id)
        except Exception:
            topic["decode_errors"] += 1

    def summary(self, now_ns, published_types=None):
        topics = {}
        for name, item in self.topics.items():
            value = dict(item)
            if value["count"]:
                seconds = (value["last_receive_ns"]-value["first_receive_ns"])*1e-9
                value["mean_received_hz"] = (value["count"]-1)/seconds if seconds > 0 else None
                value["last_receive_age_s"] = (now_ns-value["last_receive_ns"])*1e-9
            else:
                value.update(mean_received_hz=None, last_receive_age_s=None)
            if published_types is not None:
                kinds = set(published_types.get(name, []))
                value["publisher_types"] = sorted(kinds)
                if kinds and kinds != {value["type"]}:
                    value["type"] = ",".join(sorted(kinds))
            topics[name] = value
        camera_recent = self.camera.summary([])
        camera_recent["odometry_brackets_evaluated"] = False
        return dict(schema="maritime.hardware_source_check", version=1, source_mode="hardware",
            topic_profile=profile_assessment(self.profile, topics), topics=topics,
            camera_recent=camera_recent, camera_cache_limit_per_stream=self.max_keys,
            camera_cache_evictions=self.evicted, quality=dict(self.quality), gps_origin=self.latest_origin,
            camera_duplicate_records_discarded=self.duplicate_records_discarded,
            timesync=self.latest_timesync, static_transform_children=sorted(self.static_children),
            normalized_events_emitted=0, geolocation_ready=False, physical_accuracy_validated=False,
            outstanding_contracts=["camera_lens_mode_calibration", "camera_body_mount", "height_and_target_plane",
                "exposure_clock_mapping", "map_origin_reset_and_heading", "navigation_covariance_and_correlation",
                "manual_pixel_or_detector_reference"],
            limits="Read-only source check, not sensor fusion or a normalized processing node. Rates/age are observed values, not accepted limits. Camera matching covers only the retained bounded window; host arrival is not exposure time.")


def run_live(profile, output, duration_s, ros_args):
    if not 0 < duration_s <= 300:
        raise Unavailable("source_check_duration_must_be_between_0_and_300_seconds")
    path = Path(output)
    if path.exists():
        raise Unavailable("source_check_output_must_be_new")
    try:
        import rclpy
        from rclpy.node import Node
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise Unavailable("source_check_requires_sourced_native_ros_and_message_packages") from exc
    monitor = SourceMonitor(profile)
    rclpy.init(args=ros_args)
    node = None
    try:
        node = Node("perception_hardware_source_check")
        subscriptions = []
        for role, item in profile["roles"].items():
            kind = get_message(item["type"])
            subscriptions.append(node.create_subscription(kind, item["topic"],
                lambda message, role=role: monitor.observe(role, message, time.time_ns()), ros_qos(item["qos"])))
        path.mkdir(parents=True, exist_ok=False)
        write_json(path/"topic_profile.json", profile)
        started = last_snapshot = time.monotonic()
        with (path/"source_checks.jsonl").open("x") as snapshots:
            interrupted = False
            try:
                while rclpy.ok() and time.monotonic()-started < duration_s:
                    rclpy.spin_once(node, timeout_sec=.1)
                    if time.monotonic()-last_snapshot >= 1:
                        snapshots.write(line(monitor.summary(time.time_ns())))
                        last_snapshot = time.monotonic()
            except KeyboardInterrupt:
                interrupted = True
            types = {item["topic"]: [p.topic_type for p in node.get_publishers_info_by_topic(item["topic"])]
                     for item in profile["roles"].values()}
            summary = monitor.summary(time.time_ns(), types)
            summary["interrupted"] = interrupted
            write_json(path/"summary.json", summary)
            return summary
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--ros", action="store_true", help="Subscribe to the observed hardware topics")
    mode.add_argument("--print-record-command", action="store_true")
    parser.add_argument("--profile", default="builtin:mavros_imx519")
    parser.add_argument("--duration-s", type=float, default=15.)
    parser.add_argument("--output", help="New source-check directory")
    parser.add_argument("--bag-output", help="New bag directory for the printed recording command")
    parser.add_argument("--qos-config", help="Override the recorder QoS YAML when remapping profile topics")
    args, ros_args = parser.parse_known_args()
    if ros_args and (not args.ros or ros_args[0] != "--ros-args"):
        parser.error("unrecognized arguments: " + " ".join(ros_args))
    profile = load_profile(args.profile)
    if args.print_record_command:
        if not args.bag_output:
            parser.error("--bag-output is required")
        print(shlex.join(recorder_arguments(profile, args.bag_output, args.qos_config)))
    else:
        if not args.output:
            parser.error("--output is required")
        print(json.dumps(run_live(profile, args.output, args.duration_s, ros_args), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
