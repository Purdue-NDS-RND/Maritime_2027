"""Export recorded ROS outputs. Evaluation never feeds estimates back to nodes."""

from collections import Counter
import csv
import json
from pathlib import Path

from maritime_interfaces.msg import BuoyEstimateArray, BuoyMap, BearingObservationArray
from rclpy.serialization import deserialize_message
import rosbag2_py
from vision_msgs.msg import Detection2DArray


def nanoseconds(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def export_results(directory):
    """Use the finalized output bag, rather than observer delivery, as evidence."""
    directory = Path(directory)
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(directory / "bag"), storage_id="mcap"),
                rosbag2_py.ConverterOptions("cdr", "cdr"))
    reader.set_filter(rosbag2_py.StorageFilter(topics=[
        "/perception/camera_0/detections", "/perception/camera_1/detections", "/localization/buoys", "/mapping/buoys", "/mapping/observations"]))
    statuses = Counter()
    details = Counter()
    detection_arrays = boxes = position_arrays = ready_arrays = 0
    points = []
    maps = []
    observations = []
    final_map = None
    with (directory / "estimates.csv").open("w") as output:
        writer = csv.writer(output)
        writer.writerow(["timestamp_ns", "frame_id", "method", "category", "track_id",
                         "x_m", "y_m", "vessel_pose_timestamp_ns", "depth_timestamp_ns"])
        while reader.has_next():
            topic, data, _ = reader.read_next()
            if topic in ("/perception/camera_0/detections", "/perception/camera_1/detections"):
                message = deserialize_message(data, Detection2DArray)
                detection_arrays += 1
                boxes += len(message.detections)
                continue
            if topic == "/mapping/buoys":
                message = deserialize_message(data, BuoyMap)
                final_map = dict(session_id=message.session_id, timestamp_ns=nanoseconds(message.header.stamp),
                                 frame_id=message.header.frame_id, paused=message.paused, detail=message.detail,
                                 unresolved_count=message.unresolved_count, tracks=[])
                for track in message.tracks:
                    record = dict(world_id=track.world_id, category=track.category, lifecycle=track.lifecycle,
                                  x_m=track.x, y_m=track.y, covariance=list(track.covariance),
                                  category_probability=track.category_probability,
                                  footprint_radius_m=track.footprint_radius_m,
                                  existence_confidence=track.existence_confidence,
                                  first_seen_ns=nanoseconds(track.first_seen), last_seen_ns=nanoseconds(track.last_seen),
                                  last_update_ns=nanoseconds(track.last_update), source_cameras=list(track.source_cameras),
                                  observation_count=track.observation_count,
                                  selected_observation_count=track.selected_observation_count,
                                  confirmation_evidence=track.confirmation_evidence,
                                  observation_ids=list(track.observation_ids), last_residual_rad=track.last_residual_rad)
                    final_map["tracks"].append(record)
                    maps.append([final_map["timestamp_ns"], message.session_id, message.header.frame_id,
                                 track.world_id, track.category, track.lifecycle, track.x, track.y,
                                 *track.covariance, nanoseconds(track.last_seen), nanoseconds(track.last_update)])
                continue
            if topic == "/mapping/observations":
                message = deserialize_message(data, BearingObservationArray)
                for view in message.observations:
                    observations.append([nanoseconds(message.header.stamp), message.session_id, view.observation_id,
                                         view.camera_id, view.category, view.origin_x, view.origin_y,
                                         view.world_bearing_rad, view.bearing_variance, view.world_id, view.decision,
                                         nanoseconds(message.pose_before), nanoseconds(message.pose_after),
                                         message.pose_time_offset_s])
                continue
            message = deserialize_message(data, BuoyEstimateArray)
            position_arrays += 1
            statuses[message.status] += 1
            if message.detail:
                details[message.detail] += 1
            ready_arrays += int(message.inputs_ready)
            if message.estimates and message.status != "ok":
                raise ValueError("A non-ok localization output contains position estimates")
            for point in message.estimates:
                writer.writerow([nanoseconds(message.header.stamp), message.header.frame_id,
                                 message.method, point.category, point.track_id, point.x, point.y,
                                 nanoseconds(message.vessel_pose_stamp), nanoseconds(message.depth_stamp)])
                points.append((point.x, point.y, point.category, message.header.frame_id))
    if points:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        frames = {point[3] for point in points}
        if len(frames) != 1:
            raise ValueError("Cannot scatter points from different coordinate frames together")
        figure, axes = plt.subplots()
        for category in sorted({point[2] for point in points}):
            selected = [point for point in points if point[2] == category]
            axes.scatter([point[0] for point in selected], [point[1] for point in selected],
                         label=category, s=12, alpha=0.6)
        axes.set(xlabel="x (m)", ylabel="y (m)", title=f"Buoy estimates — {next(iter(frames))}")
        axes.set_aspect("equal", adjustable="datalim")
        axes.legend()
        figure.tight_layout()
        figure.savefig(directory / "scatter.png")
        plt.close(figure)
    if final_map is not None:
        (directory / "final_map.json").write_text(json.dumps(final_map, indent=2) + "\n")
        for name, header, rows in (
            ("map_history.csv", ["timestamp_ns", "session_id", "frame_id", "world_id", "category", "lifecycle",
                                 "x_m", "y_m", "cov_xx", "cov_xy", "cov_yx", "cov_yy", "last_seen_ns", "last_update_ns"], maps),
            ("observations.csv", ["timestamp_ns", "session_id", "observation_id", "camera_id", "category", "origin_x",
                                  "origin_y", "world_bearing_rad", "bearing_variance", "world_id", "decision",
                                  "pose_before_ns", "pose_after_ns", "pose_time_offset_s"], observations)):
            with (directory / name).open("w") as stream:
                writer = csv.writer(stream)
                writer.writerow(header)
                writer.writerows(rows)
    summary = dict(detection_arrays=detection_arrays, detected_boxes=boxes,
                   localization_arrays=position_arrays, inputs_ready_arrays=ready_arrays,
                   localization_statuses=dict(statuses), localization_details=dict(details), estimates=len(points),
                   scatter_saved=bool(points))
    if final_map is not None:
        summary.update(map_tracks=len(final_map["tracks"]),
                       confirmed_tracks=sum(track["lifecycle"] == "confirmed" for track in final_map["tracks"]),
                       unresolved_tracks=final_map["unresolved_count"], map_paused=final_map["paused"])
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
