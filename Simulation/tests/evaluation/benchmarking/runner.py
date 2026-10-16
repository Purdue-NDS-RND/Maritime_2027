"""Sequential offline detection; reads camera images, never simulator truth."""

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

import cv2
from cv_bridge import CvBridge
import numpy as np
from rclpy.serialization import deserialize_message
import rosbag2_py
from sensor_msgs.msg import Image
import yaml

from maritime_perception.aruco import ArucoBoxDetector, annotate


def run(dataset, destination, config_path, image_topic, preview_every):
    metadata = json.loads((dataset / "dataset.json").read_text())
    if metadata["status"] != "complete":
        raise ValueError("Use a finalized recording")
    config = yaml.safe_load(config_path.read_text())["/**"]["ros__parameters"]
    detector = ArucoBoxDetector(config["aruco_dictionary"], config["marker_ids"],
                                config["marker_categories"])
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(dataset / "bag"), storage_id="mcap"),
                rosbag2_py.ConverterOptions("cdr", "cdr"))
    topics = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
    if topics.get(image_topic) != "sensor_msgs/msg/Image":
        raise ValueError(f"Missing sensor_msgs/msg/Image topic: {image_topic}")
    # Exclude all state, depth and truth before deserialization.
    reader.set_filter(rosbag2_py.StorageFilter(topics=[image_topic]))
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "detector.yaml").write_bytes(config_path.read_bytes())
    report = {
        "schema_version": 1, "status": "running", "method": "detections",
        "recording": metadata["name"], "image_topic": image_topic,
        "dataset_metadata_sha256": hashlib.sha256((dataset / "dataset.json").read_bytes()).hexdigest(),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "source_quality": json.loads((dataset / "quality.json").read_text()),
        "opencv_version": cv2.__version__,
        "note": "Detector-only run: 2D marker boxes, without localization or accuracy scoring.",
    }
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    bridge = CvBridge()
    frame_count = nonempty = 0
    categories = Counter()
    durations = []
    started = time.perf_counter()
    try:
        with (destination / "detections.jsonl").open("x") as output:
            while reader.has_next():
                _, serialized, bag_time = reader.read_next()
                message = deserialize_message(serialized, Image)
                image = bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
                before = time.perf_counter()
                boxes = detector.detect(image)
                durations.append((time.perf_counter() - before) * 1000)
                timestamp_ns = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
                record = {
                    "timestamp_ns": timestamp_ns, "bag_timestamp_ns": bag_time,
                    "frame_id": message.header.frame_id,
                    "image_width": message.width, "image_height": message.height,
                    "boxes": [asdict(box) for box in boxes],
                }
                output.write(json.dumps(record) + "\n")
                frame_count += 1
                nonempty += bool(boxes)
                categories.update(box.category for box in boxes)
                if preview_every and (frame_count - 1) % preview_every == 0:
                    preview = destination / "previews"
                    preview.mkdir(exist_ok=True)
                    if not cv2.imwrite(str(preview / f"{frame_count:06d}.jpg"), annotate(image, boxes)):
                        raise OSError("Could not write preview image")
        if not frame_count:
            raise ValueError("The selected image topic contains no frames")
        report["status"] = "complete"
    except BaseException as error:
        report.update(status="incomplete", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report.update(
            frames_processed=frame_count, frames_with_detections=nonempty,
            detections_by_category=dict(categories), elapsed_wall_s=time.perf_counter() - started,
            detector_median_ms=float(np.median(durations)) if durations else None,
            detector_p95_ms=float(np.percentile(durations, 95)) if durations else None,
        )
        (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "source_quality"}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--image-topic", default="/sensors/camera_0/color/image_raw")
    parser.add_argument("--method", choices=("detections", "depth", "triangulation"), default="detections")
    parser.add_argument("--preview-every", type=int, default=30, help="Save an annotated frame every N frames; 0 disables")
    args = parser.parse_args()
    if args.method != "detections":
        parser.error(f"Use make benchmark METHOD={args.method} for ROS positioning; this tool exports detections only")
    if args.preview_every < 0:
        parser.error("preview-every must be nonnegative")
    run(args.dataset, args.output, args.config, args.image_topic, args.preview_every)


if __name__ == "__main__":
    main()
