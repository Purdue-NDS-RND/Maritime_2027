"""Bag transport, camera association and provenance regressions, without a ROS install."""
from copy import deepcopy
from array import array
import hashlib
import json
import sqlite3
from types import SimpleNamespace as NS

import cv2
import numpy as np
import pytest
import yaml

from maritime_perception.adapters.rosbag_audit import audit_bag, plain
from maritime_perception.validation import Unavailable


class Message(NS):
    def get_fields_and_field_types(self):
        return dict.fromkeys(vars(self))


def header(ns, frame="optical"):
    sec, nanosec = divmod(ns, 10**9)
    return Message(stamp=Message(sec=sec, nanosec=nanosec), frame_id=frame)


def database(path, topics, records):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE topics(id INTEGER PRIMARY KEY,name TEXT,type TEXT,serialization_format TEXT)")
        connection.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY,topic_id INTEGER,timestamp INTEGER,data BLOB)")
        connection.executemany("INSERT INTO topics VALUES(?,?,?,'cdr')", topics)
        connection.executemany("INSERT INTO messages(topic_id,timestamp,data) VALUES(?,?,?)", records)
    return path


def companions(ns, source_stamp=17):
    info = Message(header=header(ns), width=2, height=1, distortion_model="plumb_bob",
        d=[0.]*5, k=np.eye(3).reshape(-1), r=np.eye(3).reshape(-1), p=np.zeros(12),
        binning_x=0, binning_y=0, roi=Message(x_offset=0, y_offset=0, height=0, width=0, do_rectify=False))
    metadata = dict(id="capture_test_00000001", capture_session_id="capture_test", frame_id="optical",
        clock_id="source_clock", stamp_ns=source_stamp, stamp_semantics="gstreamer_running_time_unverified",
        ros_header_stamp_ns=ns, ros_header_stamp_semantics="host_arrival_unverified",
        input_image_size=[2, 1], image_domain="rectified", calibration_id="historical_candidate",
        synthetic=False, exposure_time_verified=False)
    image = Message(header=header(ns), width=2, height=1, encoding="rgb8", step=8,
                    data=bytes([255, 0, 0, 0, 255, 0, 99, 99]))
    return image, info, Message(data=json.dumps(metadata))


@pytest.fixture
def recorded(tmp_path):
    image, info, metadata = companions(10**9)
    _, second_info, second_metadata = companions(2*10**9, source_stamp=100)
    odom = Message(header=header(999_000_000, "map"), child_frame_id="base_link",
                   pose=Message(covariance=[0.]*36), twist=Message(covariance=[0.]*36))
    later_odom = deepcopy(odom)
    later_odom.header = header(1_001_000_000, "map")
    messages = {b"i": image, b"c": info, b"m": metadata, b"c2": second_info,
                b"m2": second_metadata, b"o": odom, b"o2": later_odom}
    path = database(tmp_path/"recording.db3", [
        (1, "/camera/image_rect", "sensor_msgs/msg/Image"),
        (2, "/camera/camera_info", "sensor_msgs/msg/CameraInfo"),
        (3, "/camera/frame_metadata", "std_msgs/msg/String"),
        (4, "/mavros/local_position/odom", "nav_msgs/msg/Odometry"),
        (5, "/tf", "tf2_msgs/msg/TFMessage")], [
        (1, 10, b"i"), (2, 12, b"c"), (3, 11, b"m"), (3, 20, b"m2"),
        (2, 21, b"c2"), (4, 1, b"o"), (4, 2, b"o2")])
    return path, messages


def test_sqlite_snapshot_counts_without_ros_and_retains_empty_topics(recorded):
    path, _ = recorded
    before = path.read_bytes()
    summary = audit_bag(path, counts_only=True)
    assert summary["topics"]["/camera/image_rect"]["count"] == 1
    assert summary["topics"]["/tf"]["count"] == 0
    assert summary["topics"]["/tf"]["mean_received_hz"] is None
    assert not summary["source"]["metadata_present"]
    assert not summary["source"]["archive_completeness_verified"]
    assert summary["source"]["files"][0]["sha256"] == hashlib.sha256(before).hexdigest()
    assert summary["camera"] is None and not summary["message_decoding"]
    assert path.read_bytes() == before


def test_export_exact_companions_preserves_source_clock_and_unknown_pose(recorded, tmp_path):
    path, messages = recorded
    output = tmp_path/"export"
    summary = audit_bag(path, decoder=lambda raw, kind: messages[raw], export_directory=output)
    assert summary["camera"]["exact_triplet_count"] == 1
    assert summary["camera"]["metadata_without_image_count"] == 1
    assert summary["camera"]["arrival_header_bracket_gap_ns"]["max"] == 2_000_000
    assert summary["camera"]["exposure_time_verified_count"] == 0
    assert summary["navigation"]["zero_pose_covariance_count"] == 2
    assert summary["export"]["exported_frames"] == 1
    assert not summary["export"]["navigation_normalized"] and not summary["geolocation_ready"]
    rows = [json.loads(line) for line in (output/"frames.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["stamp_ns"] == 17
    assert rows[0]["clock_id"] == "source_clock" and rows[0]["ros_header_stamp_ns"] == 10**9
    assert rows[0]["bag_receive_ns"] == 10 and not rows[0]["synthetic"]
    file = output/rows[0]["image_file"]
    assert hashlib.sha256(file.read_bytes()).hexdigest() == rows[0]["image_sha256"]
    np.testing.assert_array_equal(cv2.imread(str(file)), np.array([[[0, 0, 255], [0, 255, 0]]], dtype=np.uint8))
    navigation = [json.loads(line) for line in (output/"navigation.jsonl").read_text().splitlines()]
    assert len(navigation) == 2 and navigation[0]["message"]["pose"]["covariance"] == [0.]*36
    assert not (output/"measurements.jsonl").exists()
    with pytest.raises(FileExistsError):
        audit_bag(path, decoder=lambda raw, kind: messages[raw], export_directory=output)


@pytest.mark.parametrize("fault", ["duplicate_image", "duplicate_metadata", "wrong_frame", "wrong_size", "wrong_domain"])
def test_ambiguous_or_inconsistent_camera_records_are_not_exported(recorded, tmp_path, fault):
    path, messages = recorded
    if fault.startswith("duplicate"):
        tid, token = (1, b"i") if fault == "duplicate_image" else (3, b"m")
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO messages(topic_id,timestamp,data) VALUES(?,?,?)", (tid, 13, token))
    elif fault == "wrong_frame":
        messages[b"c"].header.frame_id = "another_camera"
    elif fault == "wrong_size":
        messages[b"c"].width = 3
    else:
        metadata = json.loads(messages[b"m"].data)
        metadata["image_domain"] = "raw"
        messages[b"m"].data = json.dumps(metadata)
    summary = audit_bag(path, decoder=lambda raw, kind: messages[raw], export_directory=tmp_path/"export")
    assert summary["camera"]["exact_triplet_count"] == 0
    assert summary["export"]["exported_frames"] == 0


def test_metadata_omitted_or_unknown_message_does_not_become_an_accepted_frame(recorded):
    path, messages = recorded
    messages[b"m"].data = "invalid JSON"
    def decode(raw, kind):
        if raw == b"o":
            raise ValueError("unknown message definition")
        return messages[raw]
    summary = audit_bag(path, decoder=decode)
    assert summary["topics"]["/mavros/local_position/odom"]["count"] == 2
    assert summary["topics"]["/mavros/local_position/odom"]["decode_errors"] == 1
    assert summary["camera"]["invalid_metadata_count"] == 1
    assert summary["camera"]["exact_triplet_count"] == 0


def test_declared_splits_are_required_and_topic_ids_are_local_to_each_file(tmp_path):
    database(tmp_path/"part_0.db3", [(1, "/imu", "sensor_msgs/msg/Imu")], [(1, 200, b"a")])
    database(tmp_path/"part_1.db3", [(9, "/imu", "sensor_msgs/msg/Imu")], [(9, 100, b"b")])
    (tmp_path/"metadata.yaml").write_text("rosbag2_bagfile_information:\n  storage_identifier: sqlite3\n  relative_file_paths: [part_0.db3, part_1.db3]\n")
    summary = audit_bag(tmp_path, counts_only=True)
    assert summary["source"]["all_declared_splits_supplied"]
    assert summary["topics"]["/imu"]["count"] == 2
    assert summary["topics"]["/imu"]["first_receive_ns"] == 100
    assert summary["topics"]["/imu"]["last_receive_ns"] == 200
    (tmp_path/"part_1.db3").unlink()
    with pytest.raises(Unavailable, match="bag_split_missing"):
        audit_bag(tmp_path, counts_only=True)


def test_metadata_cannot_read_a_split_outside_bag_directory(tmp_path):
    (tmp_path/"metadata.yaml").write_text("rosbag2_bagfile_information:\n  storage_identifier: sqlite3\n  relative_file_paths: [../another.db3]\n")
    with pytest.raises(Unavailable, match="bag_split_outside_directory"):
        audit_bag(tmp_path, counts_only=True)


def test_counts_only_cannot_silently_produce_a_camera_export(recorded, tmp_path):
    with pytest.raises(Unavailable, match="camera_export_requires_message_decoding"):
        audit_bag(recorded[0], counts_only=True, export_directory=tmp_path/"export")


def test_native_ros_typed_sequences_and_nonfinite_raw_values_are_strict_json():
    message = Message(covariance=array("d", [0., float("nan")]), quality=np.float64(float("inf")))
    assert json.dumps(plain(message), allow_nan=False) == '{"covariance": [0.0, null], "quality": null}'


def manifest(path):
    topics = [("/camera/image_rect", "sensor_msgs/msg/Image", 1),
              ("/camera/camera_info", "sensor_msgs/msg/CameraInfo", 2),
              ("/camera/frame_metadata", "std_msgs/msg/String", 2),
              ("/mavros/local_position/odom", "nav_msgs/msg/Odometry", 2),
              ("/tf", "tf2_msgs/msg/TFMessage", 0)]
    return dict(version=5, storage_identifier="sqlite3", compression_mode="", message_count=7,
        starting_time=dict(nanoseconds_since_epoch=1), duration=dict(nanoseconds=20),
        relative_file_paths=[path.name],
        files=[dict(path=path.name, message_count=7, starting_time=dict(nanoseconds_since_epoch=1),
                    duration=dict(nanoseconds=20))],
        topics_with_message_count=[dict(topic_metadata=dict(name=name, type=kind, serialization_format="cdr"),
                                        message_count=count) for name, kind, count in topics])


def test_complete_manifest_matches_database_and_is_hashed(recorded):
    path, _ = recorded
    metadata = path.parent/"metadata.yaml"
    metadata.write_text(yaml.safe_dump(dict(rosbag2_bagfile_information=manifest(path))))
    summary = audit_bag(path.parent, counts_only=True)
    assert summary["source"]["all_declared_splits_supplied"]
    assert summary["source"]["metadata_consistency_verified"]
    assert summary["source"]["archive_completeness_verified"]
    assert all(summary["source"]["metadata_consistency_checks"].values())
    assert summary["source"]["metadata_sha256"] == hashlib.sha256(metadata.read_bytes()).hexdigest()
    assert not summary["geolocation_ready"]


@pytest.mark.parametrize("fault", ["total", "start", "duration", "topic_count", "topic_type", "file_count", "file_duration"])
def test_stale_or_mismatched_manifest_is_rejected_before_export(recorded, tmp_path, fault):
    path, messages = recorded
    value = manifest(path)
    if fault == "total":
        value["message_count"] = 8
    elif fault == "start":
        value["starting_time"]["nanoseconds_since_epoch"] = 0
    elif fault == "duration":
        value["duration"]["nanoseconds"] = 21
    elif fault == "topic_count":
        value["topics_with_message_count"][0]["message_count"] = 2
    elif fault == "topic_type":
        value["topics_with_message_count"][0]["topic_metadata"]["type"] = "sensor_msgs/msg/CompressedImage"
    elif fault == "file_count":
        value["files"][0]["message_count"] = 8
    else:
        value["files"][0]["duration"]["nanoseconds"] = 21
    (path.parent/"metadata.yaml").write_text(yaml.safe_dump(dict(rosbag2_bagfile_information=value)))
    output = tmp_path/"export"
    with pytest.raises(Unavailable, match="bag_metadata_mismatch"):
        audit_bag(path.parent, decoder=lambda raw, kind: messages[raw], export_directory=output)
    assert not output.exists()


def test_one_selected_split_is_not_compared_with_whole_bag_totals(recorded):
    path, _ = recorded
    database(path.parent/"another.db3", [(1, "/another", "std_msgs/msg/Empty")], [(1, 0, b"x")])
    value = manifest(path)
    value["relative_file_paths"].append("another.db3")
    value["message_count"] = 8
    value["starting_time"]["nanoseconds_since_epoch"] = 0
    value["duration"]["nanoseconds"] = 21
    value["files"].append(dict(path="another.db3", message_count=1,
        starting_time=dict(nanoseconds_since_epoch=0), duration=dict(nanoseconds=0)))
    value["topics_with_message_count"].append(dict(topic_metadata=dict(name="/another", type="std_msgs/msg/Empty",
        serialization_format="cdr"), message_count=1))
    (path.parent/"metadata.yaml").write_text(yaml.safe_dump(dict(rosbag2_bagfile_information=value)))
    assert audit_bag(path.parent, counts_only=True)["source"]["metadata_consistency_verified"]
    selected = audit_bag(path, counts_only=True)
    assert not selected["source"]["all_declared_splits_supplied"]
    assert not selected["source"]["metadata_consistency_verified"]
    assert not selected["source"]["archive_completeness_verified"]
