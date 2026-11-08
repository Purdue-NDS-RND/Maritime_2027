"""Audit ROS 2 bag topic flow and timestamp continuity without running inference."""
import argparse
from collections import Counter
import json
from pathlib import Path

import yaml

from ..replay import write_json
from ..validation import Unavailable
from .ros_conversion import ros_stamp_ns


def audit_bag(bag, storage_id=None):
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise SystemExit("Bag audit unavailable: source compatible ROS 2 with rosbag2_py and message packages") from exc
    bag = Path(bag)
    if storage_id is None:
        metadata = yaml.safe_load((bag/"metadata.yaml").read_text())
        storage_id = metadata["rosbag2_bagfile_information"]["storage_identifier"]
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage_id), rosbag2_py.ConverterOptions("", ""))
    types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    topics, classes = {}, {}
    while reader.has_next():
        topic, raw, received = reader.read_next()
        info = topics.setdefault(topic, dict(type=types[topic], count=0, serialized_bytes=0,
            first_receive_ns=received, last_receive_ns=received, receive_backwards=0,
            header_count=0, header_backwards=0, header_duplicates=0, frame_ids=[], decode_errors=0))
        if received < info["last_receive_ns"]:
            info["receive_backwards"] += 1
        info["count"] += 1
        info["serialized_bytes"] += len(raw)
        info["last_receive_ns"] = received
        try:
            if topic not in classes:
                classes[topic] = get_message(types[topic])
            message = deserialize_message(raw, classes[topic])
            if hasattr(message, "header"):
                stamp = ros_stamp_ns(message.header.stamp)
                old = info.get("last_header_ns")
                info["header_backwards"] += old is not None and stamp < old
                info["header_duplicates"] += old is not None and stamp == old
                info["header_count"] += 1
                info.setdefault("first_header_ns", stamp)
                info["last_header_ns"] = stamp
                frame = message.header.frame_id
                if frame not in info["frame_ids"] and len(info["frame_ids"]) < 20:
                    info["frame_ids"].append(frame)
        except Exception:
            # Topic bytes/counts remain useful when custom message definitions are absent.
            info["decode_errors"] += 1
    for info in topics.values():
        seconds = (info["last_receive_ns"]-info["first_receive_ns"])*1e-9
        info["receive_span_s"] = seconds
        info["mean_received_hz"] = (info["count"]-1)/seconds if seconds > 0 else None
    return dict(schema="maritime.rosbag_audit", version=1, storage_id=storage_id, topics=topics,
                physical_accuracy_validated=False,
                limits="Bag receive times, header times and camera PTS may use different clocks. No synchronization, calibration or GPS accuracy is certified.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag", required=True, help="Complete bag directory including metadata and all splits")
    parser.add_argument("--storage-id")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.output).exists():
        raise Unavailable("audit_output_must_be_new")
    summary = audit_bag(args.bag, args.storage_id)
    write_json(args.output, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
