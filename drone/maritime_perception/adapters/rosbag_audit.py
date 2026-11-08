"""Inspect sensor flow and export exact camera companions, without inference."""
import argparse
from array import array
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import fields, is_dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from ..replay import line, write_json
from ..validation import Unavailable
from .bag_source import bag_storage, native_decoder, native_records, sqlite_records, sqlite_sources
from .ros_conversion import ros_stamp_ns


IMAGE_TOPICS = ("/camera/image_rect", "/camera/image_raw")
INFO_TOPIC = "/camera/camera_info"
META_TOPIC = "/camera/frame_metadata"


def plain(message):
    """Keep raw ROS fields; never turn navigation messages into accepted states."""
    if hasattr(message, "get_fields_and_field_types"):
        return {name: plain(getattr(message, name)) for name in message.get_fields_and_field_types()}
    if is_dataclass(message):
        return {f.name: plain(getattr(message, f.name)) for f in fields(message) if not f.name.startswith("_")}
    if isinstance(message, np.ndarray):
        return plain(message.tolist())
    if isinstance(message, np.generic):
        return plain(message.item())
    if isinstance(message, dict):
        return {key: plain(value) for key, value in message.items()}
    if isinstance(message, (tuple, list, array)):
        return [plain(value) for value in message]
    if isinstance(message, float) and not math.isfinite(message):
        return None
    return message


def header_key(message):
    return ros_stamp_ns(message.header.stamp), message.header.frame_id


def camera_info(message):
    keys = ("width", "height", "distortion_model", "d", "k", "r", "p", "binning_x", "binning_y", "roi")
    return {key: plain(getattr(message, key)) for key in keys}


def distribution(values):
    if not values:
        return dict(count=0, min=None, median=None, max=None)
    return dict(count=len(values), min=min(values), median=float(np.median(values)), max=max(values))


class CameraAudit:
    def __init__(self):
        self.images, self.infos, self.metadata = (defaultdict(list) for _ in range(3))
        self.invalid_metadata = 0

    def add(self, topic, message):
        if topic in IMAGE_TOPICS:
            self.images[header_key(message)].append(dict(topic=topic, width=int(message.width),
                height=int(message.height), encoding=message.encoding, step=int(message.step),
                bytes=len(message.data)))
        elif topic == INFO_TOPIC:
            self.infos[header_key(message)].append(camera_info(message))
        elif topic == META_TOPIC:
            try:
                item = json.loads(message.data)
                if (type(item["ros_header_stamp_ns"]) is not int or item["ros_header_stamp_ns"] < 0
                    or type(item["stamp_ns"]) is not int or item["stamp_ns"] < 0
                    or not isinstance(item["frame_id"], str) or not isinstance(item["id"], str)):
                    raise ValueError("invalid capture metadata")
                self.metadata[(item["ros_header_stamp_ns"], item["frame_id"])].append(item)
            except (ValueError, KeyError, TypeError):
                self.invalid_metadata += 1

    def pairs(self):
        paired, conflicts = {}, 0
        for key in self.images.keys() & self.infos.keys() & self.metadata.keys():
            if any(len(index[key]) != 1 for index in (self.images, self.infos, self.metadata)):
                continue
            image, info, metadata = self.images[key][0], self.infos[key][0], self.metadata[key][0]
            size = [image["width"], image["height"]]
            domain = "rectified" if image["topic"] == "/camera/image_rect" else "raw"
            if (size != [info["width"], info["height"]] or size != metadata.get("input_image_size")
                or domain != metadata.get("image_domain") or not metadata.get("calibration_id")):
                conflicts += 1
                continue
            paired[key] = (metadata, info)
        return paired, conflicts

    def summary(self, odom_stamps):
        paired, conflicts = self.pairs()
        metadata = [m for items in self.metadata.values() for m in items]
        source_stamps = defaultdict(list)
        for m in metadata:
            source_stamps[str(m.get("clock_id"))].append(m["stamp_ns"])
        source_steps = [b-a for stamps in source_stamps.values() for a, b in zip(stamps, stamps[1:])]
        gaps = []
        for stamp, _ in paired:
            i = bisect_left(odom_stamps, stamp)
            if i < len(odom_stamps) and odom_stamps[i] == stamp:
                gaps.append(0)
            elif 0 < i < len(odom_stamps):
                gaps.append(odom_stamps[i]-odom_stamps[i-1])
        return dict(image_count=sum(map(len, self.images.values())),
            camera_info_count=sum(map(len, self.infos.values())), metadata_count=len(metadata),
            exact_triplet_count=len(paired), invalid_metadata_count=self.invalid_metadata,
            conflicting_geometry_count=conflicts,
            duplicate_header_keys={name: sum(len(items)>1 for items in index.values())
                for name, index in [("image", self.images), ("camera_info", self.infos), ("metadata", self.metadata)]},
            metadata_without_image_count=sum(len(v) for k, v in self.metadata.items() if k not in self.images),
            image_without_metadata_count=sum(len(v) for k, v in self.images.items() if k not in self.metadata),
            image_without_camera_info_count=sum(len(v) for k, v in self.images.items() if k not in self.infos),
            source_step_ns=distribution(source_steps),
            exposure_time_verified_count=sum(m.get("exposure_time_verified") is True for m in metadata),
            arrival_header_with_odometry_brackets=len(gaps), arrival_header_bracket_gap_ns=distribution(gaps),
            timing_limit="Odometry brackets use the host-arrival header, not verified exposure time.")


def export_camera(records, types, decode, pairs, output):
    import cv2
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "images").mkdir()
    exported = 0
    decode_errors = Counter()
    with (output / "frames.jsonl").open("x") as frames, (output / "navigation.jsonl").open("x") as navigation:
        for topic, raw, received in records:
            try:
                message = decode(raw, types[topic])
            except Exception:
                decode_errors[topic] += 1
                continue
            if topic not in IMAGE_TOPICS:
                if topic.startswith("/mavros/") or topic in ("/tf", "/tf_static"):
                    navigation.write(line(dict(topic=topic, type=types[topic], bag_receive_ns=received,
                                               message=plain(message))))
                continue
            key = header_key(message)
            if key not in pairs:
                continue
            metadata, info = pairs[key]
            channels = {"bgr8": 3, "rgb8": 3, "mono8": 1}.get(message.encoding)
            if (channels is None or message.width <= 0 or message.height <= 0
                or message.step < message.width*channels or len(message.data) != message.height*message.step):
                raise Unavailable("bag_image_layout_unsupported")
            image = np.frombuffer(bytes(message.data), dtype=np.uint8).reshape(message.height, message.step)
            image = image[:, :message.width*channels].reshape(message.height, message.width, channels)
            if message.encoding == "rgb8":
                image = image[:, :, ::-1]
            ok, encoded = cv2.imencode(".png", image)
            if not ok:
                raise Unavailable("bag_image_encode_failed")
            payload = encoded.tobytes()
            filename = f"images/frame_{exported:08d}.png"
            with (output / filename).open("xb") as stream:
                stream.write(payload)
            frames.write(line(dict(metadata, camera_info=info, image_file=filename,
                                   image_sha256=hashlib.sha256(payload).hexdigest(), bag_receive_ns=received)))
            exported += 1
    return dict(directory=str(output), exported_frames=exported, decode_errors=dict(decode_errors),
                navigation_normalized=False, physical_accuracy_validated=False)


def audit_bag(bag, storage_id=None, *, counts_only=False, decoder=None, export_directory=None):
    storage_id = bag_storage(bag, storage_id)
    if storage_id == "sqlite3":
        files, types, provenance = sqlite_sources(bag)
        records = sqlite_records(files)
    else:
        if export_directory is not None:
            raise Unavailable("camera_export_requires_sqlite3")
        types, records = native_records(bag, storage_id)
        provenance = dict(metadata_present=(Path(bag)/"metadata.yaml").is_file(),
                          archive_completeness_verified=False)
    if counts_only and export_directory is not None:
        raise Unavailable("camera_export_requires_message_decoding")
    decode = None if counts_only else decoder or native_decoder()
    topics = {name: dict(type=kind, count=0, serialized_bytes=0, first_receive_ns=None,
        last_receive_ns=None, receive_backwards=0, header_count=0, header_backwards=0,
        header_duplicates=0, max_header_gap_ns=None, frame_ids=[], decode_errors=0,
        receive_minus_header_ns=[]) for name, kind in types.items()}
    camera = CameraAudit()
    odom_stamps, imu_stamps = [], set()
    navigation = dict(odometry_count=0, zero_pose_covariance_count=0, zero_twist_covariance_count=0,
                      gps_fix_status_counts=Counter(), gps_origins=[], static_transforms=[])
    for topic, raw, received in records:
        info = topics[topic]
        previous = info["last_receive_ns"]
        info["receive_backwards"] += previous is not None and received < previous
        info["count"] += 1
        info["serialized_bytes"] += len(raw)
        if info["first_receive_ns"] is None:
            info["first_receive_ns"] = received
        info["last_receive_ns"] = received
        if decode is None:
            continue
        try:
            message = decode(raw, types[topic])
            if hasattr(message, "header"):
                stamp, frame = header_key(message)
                old = info.get("last_header_ns")
                info["header_backwards"] += old is not None and stamp < old
                info["header_duplicates"] += old is not None and stamp == old
                if old is not None:
                    info["max_header_gap_ns"] = max(info["max_header_gap_ns"] or 0, stamp-old)
                info["header_count"] += 1
                info.setdefault("first_header_ns", stamp)
                info["last_header_ns"] = stamp
                info["receive_minus_header_ns"].append(received-stamp)
                if frame not in info["frame_ids"] and len(info["frame_ids"]) < 20:
                    info["frame_ids"].append(frame)
            camera.add(topic, message)
            if types[topic] == "nav_msgs/msg/Odometry":
                odom_stamps.append(ros_stamp_ns(message.header.stamp))
                navigation["odometry_count"] += 1
                navigation["zero_pose_covariance_count"] += not any(message.pose.covariance)
                navigation["zero_twist_covariance_count"] += not any(message.twist.covariance)
            elif types[topic] == "sensor_msgs/msg/Imu":
                imu_stamps.add(ros_stamp_ns(message.header.stamp))
            elif types[topic] == "sensor_msgs/msg/NavSatFix":
                navigation["gps_fix_status_counts"][str(message.status.status)] += 1
            elif topic == "/mavros/global_position/gp_origin" and len(navigation["gps_origins"]) < 20:
                navigation["gps_origins"].append(plain(message))
            elif topic == "/tf_static" and len(navigation["static_transforms"]) < 100:
                navigation["static_transforms"].extend(plain(message.transforms))
        except Exception:
            info["decode_errors"] += 1
    for info in topics.values():
        seconds = (info["last_receive_ns"]-info["first_receive_ns"])*1e-9 if info["count"] else 0
        info["receive_span_s"] = seconds
        info["mean_received_hz"] = (info["count"]-1)/seconds if seconds > 0 else None
        info["receive_minus_header_ns"] = distribution(info["receive_minus_header_ns"])
    navigation["imu_odometry_exact_stamp_count"] = len(set(odom_stamps) & imu_stamps) if decode else None
    summary = dict(schema="maritime.rosbag_audit", version=2, storage_id=storage_id, topics=topics,
        source=provenance, message_decoding=decode is not None,
        camera=camera.summary(sorted(odom_stamps)) if decode else None,
        navigation=navigation if decode else None, geolocation_ready=False, physical_accuracy_validated=False,
        limits="Receive/header/PTS clocks differ. Exports do not verify exposure timing, mount, frame/origin, heading, height or covariance. No GPS reports or accuracy acceptance are produced.")
    if export_directory is not None:
        pairs, _ = camera.pairs()
        summary["export"] = export_camera(sqlite_records(files), types, decode, pairs, export_directory)
        write_json(Path(export_directory)/"audit.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag", required=True, help="Complete bag directory, or a supplied SQLite .db3 snapshot")
    parser.add_argument("--storage-id")
    parser.add_argument("--counts-only", action="store_true", help="Inspect SQLite topic flow without ROS decoding")
    parser.add_argument("--export-camera", help="New directory for matched PNGs, frames.jsonl and raw navigation.jsonl")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.output).exists() or (args.export_camera and Path(args.export_camera).exists()):
        raise Unavailable("audit_output_must_be_new")
    summary = audit_bag(args.bag, args.storage_id, counts_only=args.counts_only,
                        export_directory=args.export_camera)
    with Path(args.output).open("x") as stream:
        stream.write(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
