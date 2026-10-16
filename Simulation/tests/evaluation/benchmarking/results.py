"""Export recorded ROS outputs. Evaluation never feeds estimates back to nodes."""

from collections import Counter
import csv
import json
from pathlib import Path

from maritime_interfaces.msg import BuoyEstimateArray
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
        "/perception/camera_0/detections", "/localization/buoys"]))
    statuses = Counter()
    detection_arrays = boxes = position_arrays = ready_arrays = 0
    points = []
    with (directory / "estimates.csv").open("w") as output:
        writer = csv.writer(output)
        writer.writerow(["timestamp_ns", "frame_id", "method", "category", "track_id",
                         "x_m", "y_m", "vessel_pose_timestamp_ns", "depth_timestamp_ns"])
        while reader.has_next():
            topic, data, _ = reader.read_next()
            if topic == "/perception/camera_0/detections":
                message = deserialize_message(data, Detection2DArray)
                detection_arrays += 1
                boxes += len(message.detections)
                continue
            message = deserialize_message(data, BuoyEstimateArray)
            position_arrays += 1
            statuses[message.status] += 1
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
    summary = dict(detection_arrays=detection_arrays, detected_boxes=boxes,
                   localization_arrays=position_arrays, inputs_ready_arrays=ready_arrays,
                   localization_statuses=dict(statuses), estimates=len(points),
                   scatter_saved=bool(points))
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
