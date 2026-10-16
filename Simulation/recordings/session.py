"""Container-side recording, dataset checks, and ordinary rosbag2 playback.

The recorder/player remain the standard ROS tools. This helper only saves
clock observations, handles shutdown, and checks the resulting dataset.
"""

import argparse
from collections import Counter
import csv
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import yaml


ROOT = Path("/recording")
CAMERA_TOPICS = (
    "/sensors/camera_0/color/image_raw",
    "/sensors/camera_0/depth/image_rect_raw",
    "/sensors/camera_0/color/camera_info",
)
MIN_RGBD_HZ = 8.0


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def stamp_ns(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def topic_config(root=ROOT):
    config = yaml.safe_load((root / "topics.yaml").read_text())
    manifest = json.loads((root / "scenario.manifest.json").read_text())
    truth_topics = []
    for buoy in manifest["buoys"]:
        expected = f"/blueboat/ground_truth/{buoy['name']}/odometry"
        if buoy["truth_topic"] != expected or expected in truth_topics:
            raise ValueError("scenario truth topics must identify distinct buoy entities")
        truth_topics.append(expected)
    config["required"] += truth_topics
    return config


def rgbd_summary(stamps):
    common = stamps[0] & stamps[1] & stamps[2]
    matched = sum(common.values())
    duration = (max(common) - min(common)) / 1e9 if common else 0
    return {
        "matched": matched,
        "rate_hz": (matched - 1) / duration if duration > 0 else 0.0,
        "unmatched": {topic: sum(values.values()) - matched
                      for topic, values in zip(CAMERA_TOPICS, stamps)},
    }


def inspect_bag(root=ROOT):
    """Read the actual bag, without depending on a live ROS graph."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    config = topic_config(root)
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(root / "bag"), storage_id="mcap"),
                rosbag2_py.ConverterOptions("", ""))
    types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    topics = {}
    stamps = [Counter() for _ in CAMERA_TOPICS]
    static_transforms = set()
    start = end = None
    first_position = last_position = None
    path_length = 0.0
    header_ranges = {}
    classes = {}
    for topic, type_name in types.items():
        if topic in CAMERA_TOPICS or topic.endswith("/odometry") or topic in (
            "/tf_static", "/mavros/local_position/odom", "/mavros/imu/data",
        ):
            classes[topic] = get_message(type_name)
    while reader.has_next():
        topic, data, timestamp = reader.read_next()
        start = timestamp if start is None else min(start, timestamp)
        end = timestamp if end is None else max(end, timestamp)
        stats = topics.setdefault(topic, {"count": 0, "max_gap_s": 0.0, "last": timestamp})
        stats["count"] += 1
        stats["max_gap_s"] = max(stats["max_gap_s"], (timestamp - stats["last"]) / 1e9)
        stats["last"] = timestamp
        if topic not in classes:
            continue
        message = deserialize_message(data, classes[topic])
        if hasattr(message, "header"):
            stamp = stamp_ns(message.header.stamp)
            bounds = header_ranges.setdefault(topic, [stamp, stamp])
            bounds[0], bounds[1] = min(bounds[0], stamp), max(bounds[1], stamp)
            if topic in CAMERA_TOPICS:
                stamps[CAMERA_TOPICS.index(topic)][stamp] += 1
        if topic == "/tf_static":
            static_transforms.update((tf.header.frame_id, tf.child_frame_id) for tf in message.transforms)
        if topic == "/blueboat/ground_truth/odometry":
            position = (message.pose.pose.position.x, message.pose.pose.position.y)
            if first_position is None:
                first_position = position
            if last_position is not None:
                path_length += math.dist(last_position, position)
            last_position = position
    for stats in topics.values():
        del stats["last"]
    errors = [f"No messages: {topic}" for topic in config["required"] if topic not in topics]
    for transform in (("base_link", "camera_0_link"), ("camera_0_link", "camera_0_optical_frame")):
        if transform not in static_transforms:
            errors.append(f"Missing camera transform: {transform[0]} -> {transform[1]}")
    rgbd = rgbd_summary(stamps)
    if rgbd["rate_hz"] < MIN_RGBD_HZ:
        errors.append(f"Exact RGB-D rate {rgbd['rate_hz']:.2f} Hz is below {MIN_RGBD_HZ:.2f} Hz")
    for topic in config["required"]:
        if topic in topics and not topic.endswith("tf_static") and topics[topic]["max_gap_s"] > 2:
            errors.append(f"Stream gap over 2 seconds: {topic}")
    log_path = root / "recorder.log"
    losses = re.findall(r"Number of messages lost on the transport layer: (\d+)",
                        log_path.read_text() if log_path.exists() else "")
    return {
        "passed": not errors, "errors": errors,
        "duration_s": (end - start) / 1e9 if start is not None else 0.0,
        "size_bytes": sum(path.stat().st_size for path in root.rglob("*.mcap")),
        "topics": topics, "rgbd": rgbd, "header_time_ranges_ns": header_ranges,
        "reported_transport_losses": max(map(int, losses), default=0),
        "boat_displacement_m": math.dist(first_position, last_position) if first_position else 0.0,
        "boat_path_length_m": path_length,
    }


def new_node():
    import rclpy
    from rclpy.signals import SignalHandlerOptions

    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    return rclpy.create_node("recording_session")


def record(duration):
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock

    metadata_path = ROOT / "dataset.json"
    metadata = json.loads(metadata_path.read_text())
    config = topic_config()
    (ROOT / "qos.yaml").write_text(yaml.safe_dump(config["qos"]))
    node = new_node()
    process = None
    stopped = False
    clock = {"last": None, "sampled_at": 0, "reset": False}

    def stop(_signal, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        with (ROOT / "clock.csv").open("w") as clock_file, (ROOT / "recorder.log").open("w") as log:
            writer = csv.writer(clock_file)
            writer.writerow(["simulation_ns", "system_receipt_ns", "monotonic_receipt_ns"])

            def observe_clock(message):
                simulation = stamp_ns(message.clock)
                if clock["last"] is not None and simulation < clock["last"]:
                    clock["reset"] = True
                clock["last"] = simulation
                monotonic = time.monotonic_ns()
                if monotonic - clock["sampled_at"] >= 100_000_000:
                    writer.writerow([simulation, time.time_ns(), monotonic])
                    clock_file.flush()
                    clock["sampled_at"] = monotonic

            subscription = node.create_subscription(Clock, "/clock", observe_clock, qos_profile_sensor_data)
            deadline = time.monotonic() + 20
            print("Waiting for simulation clock and required topics...", flush=True)
            while not stopped:
                rclpy.spin_once(node, timeout_sec=0.1)
                present = {topic for topic, _ in node.get_topic_names_and_types()}
                missing = set(config["required"]) - present
                if clock["last"] and not missing:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Required simulation streams unavailable: {sorted(missing)}; clock={clock['last']}")
            if stopped:
                raise RuntimeError("stopped before recording began")
            command = ["ros2", "bag", "record", "--storage", "mcap",
                       "--storage-preset-profile", "zstd_fast", "--use-sim-time",
                       "--max-cache-size", "268435456", "--disable-keyboard-controls",
                       "--qos-profile-overrides-path", str(ROOT / "qos.yaml"),
                       "--output", str(ROOT / "bag"), "--topics",
                       *config["required"], *config["optional"]]
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 20
            while not stopped:
                rclpy.spin_once(node, timeout_sec=0.1)
                if process.poll() is not None:
                    raise RuntimeError("rosbag recorder exited; see recorder.log")
                subscribed = all(any(info.node_name == "rosbag2_recorder"
                                     for info in node.get_subscriptions_info_by_topic(topic))
                                 for topic in config["required"])
                if subscribed:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("recorder did not subscribe to all required streams; see recorder.log")
            metadata["status"] = "recording"
            write_json(metadata_path, metadata)
            print("Recording. Drive using teleop or QGroundControl; Ctrl-C finishes this recording only.", flush=True)
            deadline = time.monotonic() + duration if duration else float("inf")
            while not stopped and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.1)
                if clock["reset"]:
                    raise RuntimeError("simulation clock moved backwards; recording is incomplete")
                if process.poll() is not None:
                    raise RuntimeError("rosbag recorder exited unexpectedly; see recorder.log")
            if clock["reset"]:
                raise RuntimeError("simulation clock moved backwards; recording is incomplete")
            process.send_signal(signal.SIGINT)
            result = process.wait(timeout=30)
            if result not in (0, -signal.SIGINT):
                raise RuntimeError(f"recorder failed with exit {result}; see recorder.log")
        print("Checking saved messages and RGB-D timestamp matches...", flush=True)
        report = inspect_bag()
        write_json(ROOT / "quality.json", report)
        metadata["status"] = "complete"
        print(f"Dataset checks: {'PASS' if report['passed'] else 'FAIL'}; "
              f"exact RGB-D {report['rgbd']['rate_hz']:.2f} Hz", flush=True)
        print(f"Unmatched RGB/depth/info: {list(report['rgbd']['unmatched'].values())}", flush=True)
        for error in report["errors"]:
            print(f"  {error}", flush=True)
        return 0 if report["passed"] else 1
    except Exception as error:
        metadata["status"] = "incomplete"
        metadata["error"] = str(error)
        print(f"ERROR: {error}", flush=True)
        return 1
    finally:
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        node.destroy_node()
        rclpy.shutdown()
        write_json(metadata_path, metadata)
        if "RECORDING_UID" in os.environ:
            for path in ROOT.rglob("*"):
                os.chown(path, int(os.environ["RECORDING_UID"]),
                         int(os.environ["RECORDING_GID"]), follow_symlinks=False)


def replay(rate, start_paused):
    import rclpy

    config = topic_config()
    node = new_node()
    # Allow discovery to find existing publishers before introducing a bag clock.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    conflicts = [topic for topic in config["required"] if node.count_publishers(topic)]
    node.destroy_node()
    rclpy.shutdown()
    if conflicts:
        raise RuntimeError(f"replay domain already has input publishers: {conflicts}; choose another REPLAY_DOMAIN_ID")
    command = ["ros2", "bag", "play", str(ROOT / "bag"), "--clock", "100",
               "--rate", str(rate), "--read-ahead-queue-size", "100",
               "--qos-profile-overrides-path", str(ROOT / "qos.yaml"),
               "--topics", *config["required"], *config["optional"]]
    if start_paused:
        command.append("--start-paused")
    os.execvp(command[0], command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("record", "replay"))
    parser.add_argument("--duration", type=float)
    parser.add_argument("--rate", type=float, default=1)
    parser.add_argument("--start-paused", action="store_true")
    args = parser.parse_args()
    if args.command == "record":
        raise SystemExit(record(args.duration))
    replay(args.rate, args.start_paused)


if __name__ == "__main__":
    main()
