"""Run ordinary ROS nodes against a bag and record their output topics."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from maritime_interfaces.msg import BuoyEstimateArray
from maritime_localization.depth import DepthLocalizer
from maritime_localization.mapping import MappingSettings
from maritime_localization.triangulation import TriangulationLocalizer
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from rosgraph_msgs.msg import Clock
import yaml

from results import export_results


IMAGE = "/sensors/camera_0/color/image_raw"
INFO = "/sensors/camera_0/color/camera_info"
DEPTH = "/sensors/camera_0/depth/image_rect_raw"
POSE = "/mavros/local_position/odom"
DETECTIONS = "/perception/camera_0/detections"
ESTIMATES = "/localization/buoys"


def stop(process, group=True):
    if process is None or process.poll() is not None:
        return
    try:
        if group:
            os.killpg(process.pid, signal.SIGINT)
        else:
            process.send_signal(signal.SIGINT)  # ros2 launch forwards it to its own nodes.
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def run(dataset, destination, method, rate, pose_time_offset_s=0.):
    metadata = json.loads((dataset / "dataset.json").read_text())
    if metadata["status"] != "complete":
        raise ValueError("Recording must be complete")
    domain = int(os.environ.get("ROS_DOMAIN_ID", "0"))
    if domain == metadata["capture_domain"]:
        raise ValueError("Replay must use a different domain from the live capture")
    input_topics = [IMAGE, INFO, POSE, "/tf_static"]
    if method == "depth":
        input_topics.append(DEPTH)
    bag_metadata = yaml.safe_load((dataset / "bag/metadata.yaml").read_text())
    topic_counts = {entry["topic_metadata"]["name"]: entry["message_count"]
                    for entry in bag_metadata["rosbag2_bagfile_information"]["topics_with_message_count"]}
    if any(topic_counts.get(topic, 0) == 0 for topic in input_topics):
        raise ValueError("Recording is missing required camera, pose, or mounting-transform input")
    destination.mkdir(parents=True, exist_ok=False)
    report = dict(status="starting", method=method, recording=metadata["name"],
                  created_at=datetime.now(timezone.utc).isoformat(),
                  algorithm_implemented=True,
                  algorithm_parameters=asdict(MappingSettings() if method == "rgb_mapping" else
                                             (DepthLocalizer if method == "depth" else TriangulationLocalizer)().settings),
                  pose_time_offset_s=pose_time_offset_s,
                  rate=rate, ros_domain=domain,
                  source_rgb_frames=topic_counts[IMAGE], input_topics=input_topics,
                  assumptions={"output_frame": "map", "pose_source": POSE,
                               "timing": ("acquisition-time pose interpolation with explicit clock offset" if method == "rgb_mapping"
                                          else "latest received inputs; no timestamp synchronization"),
                               "observation_point": "2D bounding-box center approximates buoy center",
                               "truth_frame_alignment": "provisional; no accuracy scoring"})
    (destination / "detector.yaml").write_bytes(
        Path("/opt/autonomy_ws/src/maritime_perception/config/aruco.yaml").read_bytes())
    (destination / "source-dataset.json").write_bytes((dataset / "dataset.json").read_bytes())
    (destination / "source-quality.json").write_bytes((dataset / "quality.json").read_bytes())
    def save():
        (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    save()
    stopping = False
    def interrupt(*_):
        nonlocal stopping
        stopping = True
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)}
    probe = Node("benchmark_supervisor")
    last_output = time.monotonic()
    def output_received(_):
        nonlocal last_output
        last_output = time.monotonic()
    probe.create_subscription(BuoyEstimateArray, ESTIMATES, output_received, qos_profile_sensor_data)
    clock = None
    processes, logs = {}, []
    def start(name, command):
        log = (destination / f"{name}.log").open("w")
        logs.append(log)
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        processes[name] = process
        return process
    def spin():
        if stopping:
            raise InterruptedError("Benchmark interrupted")
        if clock is not None:
            clock.publish(initial_clock)
        rclpy.spin_once(probe, timeout_sec=0.1)
    try:
        # Discover conflicts before adding our own publishers.
        until = time.monotonic() + 1.5
        while time.monotonic() < until:
            spin()
        occupied = [topic for topic in input_topics + ["/clock", DETECTIONS, ESTIMATES]
                    if probe.count_publishers(topic)]
        if occupied:
            raise ValueError(f"Replay domain already has publishers: {occupied}")
        # The recorder does not subscribe to data until it has received /clock.
        # Hold at the bag's first time during startup, then hand clock ownership
        # to the player before any input observations are published.
        start_ns = max(1, bag_metadata["rosbag2_bagfile_information"]["starting_time"]["nanoseconds_since_epoch"])
        initial_clock = Clock()
        initial_clock.clock.sec, initial_clock.clock.nanosec = divmod(start_ns, 1_000_000_000)
        clock = probe.create_publisher(Clock, "/clock", qos_profile_sensor_data)
        nodes = start("nodes", ["ros2", "launch", "maritime_localization", "pipeline.launch.py",
                                f"method:={method}", "use_sim_time:=true", f"pose_time_offset_s:={pose_time_offset_s}"])
        # Results are small standard ROS outputs, with a deeper recorder queue.
        result_topics = [DETECTIONS, ESTIMATES]
        if method == "rgb_mapping":
            result_topics += ["/mapping/buoys", "/mapping/observations", "/mapping/costmap",
                              "/mapping/markers", "/mapping/diagnostics"]
        qos = {topic: dict(reliability="best_effort", durability="volatile", history="keep_last", depth=100)
               for topic in result_topics}
        qos_path = destination / "result-qos.yaml"
        qos_path.write_text(yaml.safe_dump(qos))
        recorder = start("recorder", ["ros2", "bag", "record", "--storage", "mcap", "--use-sim-time",
                                      "--disable-keyboard-controls", "--qos-profile-overrides-path", str(qos_path),
                                      "--output", str(destination / "bag"), "--topics", *result_topics])
        deadline = time.monotonic() + 30
        while True:
            spin()
            if nodes.poll() is not None or recorder.poll() is not None:
                raise RuntimeError("Node launch or recorder exited; inspect nodes.log / recorder.log")
            ready = (probe.count_publishers(DETECTIONS) == 1 and probe.count_publishers(ESTIMATES) == 1
                     and probe.count_subscribers(DETECTIONS) >= 2 and probe.count_subscribers(ESTIMATES) >= 2
                     and all(probe.count_subscribers(topic) >= 1 for topic in input_topics))
            if ready:
                break
            if time.monotonic() > deadline:
                counts = {topic: probe.count_subscribers(topic) for topic in input_topics + [DETECTIONS, ESTIMATES]}
                raise TimeoutError(f"Timed out waiting for ROS pipeline; subscriber counts: {counts}")
        probe.destroy_publisher(clock)
        clock = None
        report["status"] = "playing"
        save()
        print(f"Ready: detector + {method} localizer + recorder. Starting playback.", flush=True)
        player = start("player", ["ros2", "bag", "play", str(dataset / "bag"), "--clock", "100",
                                  "--rate", str(rate), "--read-ahead-queue-size", "100",
                                  "--disable-keyboard-controls", "--qos-profile-overrides-path", str(dataset / "qos.yaml"),
                                  "--topics", *input_topics])
        while player.poll() is None:
            spin()
            if nodes.poll() is not None or recorder.poll() is not None:
                raise RuntimeError("Node launch or recorder exited during playback")
        if player.returncode:
            raise RuntimeError(f"Playback failed with code {player.returncode}; inspect player.log")
        # Drain asynchronous node output before finalizing the result bag.
        deadline = time.monotonic() + 5
        finished = time.monotonic()
        while time.monotonic() < deadline:
            spin()
            if time.monotonic() - max(last_output, finished) >= 1:
                break
        stop(nodes, group=False)
        stop(recorder)
        report.update(export_results(destination))
        if not report["localization_arrays"] or not report["inputs_ready_arrays"]:
            raise RuntimeError("No localization outputs with assembled inputs were recorded; "
                               f"input details: {report.get('localization_details', {})}")
        if report.get("map_paused"):
            raise RuntimeError("Mapping session paused; inspect final_map.json and diagnostics")
        if report["localization_statuses"].get("error", 0):
            raise RuntimeError("Localization reported errors; inspect the result bag")
        report["status"] = "complete"
        print(f"Pipeline complete: {report['detection_arrays']} detection arrays, "
              f"{report['localization_arrays']} localization updates, {report['estimates']} XY points.\n"
              + ("Positioning method is unimplemented; empty coordinates are expected."
                 if not report["algorithm_implemented"] else ""), flush=True)
    except BaseException as error:
        report.update(status="interrupted" if isinstance(error, InterruptedError) else "incomplete",
                      error=f"{type(error).__name__}: {error}")
        raise
    finally:
        for name in ("player", "nodes", "recorder"):
            stop(processes.get(name), group=name != "nodes")
        report["process_returncodes"] = {name: process.returncode for name, process in processes.items()}
        if report["status"] in ("interrupted", "incomplete") and (destination / "bag/metadata.yaml").exists():
            try:
                report.update(export_results(destination))
            except Exception as error:
                report["export_error"] = str(error)
        save()
        for log in logs:
            log.close()
        probe.destroy_node()
        rclpy.shutdown()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", choices=("depth", "triangulation", "rgb_mapping"), default="rgb_mapping")
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--pose-time-offset", type=float, default=0.)
    args = parser.parse_args()
    if not -float("inf") < args.pose_time_offset < float("inf"):
        parser.error("pose time offset must be finite")
    if not 0 < args.rate < float("inf"):
        parser.error("rate must be finite and positive")
    try:
        run(args.dataset, args.output, args.method, args.rate, args.pose_time_offset)
    except InterruptedError:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
