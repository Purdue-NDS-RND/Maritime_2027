"""Recording safeguards, plus real MCAP checks when run in the Monitor image."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / "recordings"


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host = load_module("recordings")


class HostTests(unittest.TestCase):
    def test_recording_names_cannot_escape_dataset_directory(self):
        for name in (None, "", ".", "..", "../other", "/tmp/other", "a/b", "a b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                host.dataset_path(name)
        self.assertEqual(host.dataset_path("gate-pass_01").name, "gate-pass_01")

    def test_symlink_recordings_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(host, "DATASETS", Path(directory)):
            (Path(directory) / "linked").symlink_to("/tmp")
            with self.assertRaisesRegex(ValueError, "symbolic"):
                host.dataset_path("linked")

    def test_invalid_rates_and_durations(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(Exception):
                host.positive_number(value)

    def test_run_mismatch_is_rejected_before_creating_dataset(self):
        containers = [{"State": {"Running": True}, "Config": {"Env": [
            f"RUN_ID={run}", "RUN_CONFIG_SHA256=abc",
        ]}} for run in ("run-one", "run-two")]
        with tempfile.TemporaryDirectory() as directory, patch.object(host, "output", return_value=json.dumps(containers)):
            destination = Path(directory) / "dataset"
            with self.assertRaisesRegex(ValueError, "disagree on RUN_ID"):
                host.prepare_recording(destination, "image")
            self.assertFalse(destination.exists())

    def test_existing_recording_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(host, "DATASETS", Path(directory)):
            destination = Path(directory) / "existing"
            destination.mkdir()
            marker = destination / "keep.txt"
            marker.write_text("original")
            with patch("sys.argv", ["recordings.py", "record", "--name", "existing"]):
                with self.assertRaises(SystemExit) as result:
                    host.main()
            self.assertEqual(result.exception.code, 1)
            self.assertEqual(marker.read_text(), "original")

    def test_replay_refuses_the_capture_domain_and_incomplete_datasets(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(host, "DATASETS", Path(directory)):
            destination = Path(directory) / "test"
            destination.mkdir()
            for status, domain in (("complete", "0"), ("incomplete", "97")):
                (destination / "dataset.json").write_text(json.dumps({"status": status, "capture_domain": 0}))
                with self.subTest(status=status, domain=domain), patch("os.execvp") as launch:
                    with patch("sys.argv", ["recordings.py", "replay", "--recording", "test", "--domain", domain]):
                        with self.assertRaises(SystemExit) as result:
                            host.main()
                    self.assertEqual(result.exception.code, 1)
                    launch.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec("rosbag2_py"), "run in Monitor image for MCAP integration tests")
class BagTests(unittest.TestCase):
    def setUp(self):
        self.session = load_module("session")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "topics.yaml").write_bytes((TOOLS / "topics.yaml").read_bytes())
        # Same category/marker ID, separate physical entities.
        manifest = {"buoys": [
            {"name": name, "marker_id": 1, "truth_topic": f"/blueboat/ground_truth/{name}/odometry"}
            for name in ("red_port", "red_starboard")
        ]}
        (self.root / "scenario.manifest.json").write_text(json.dumps(manifest))

    def write_bag(self, missing=None, unmatched=False, omit_transforms=False):
        import rosbag2_py
        from geometry_msgs.msg import TransformStamped
        from mavros_msgs.msg import State
        from nav_msgs.msg import Odometry
        from rclpy.serialization import serialize_message
        from rosgraph_msgs.msg import Clock
        from sensor_msgs.msg import CameraInfo, Image, Imu, NavSatFix
        from tf2_msgs.msg import TFMessage

        config = self.session.topic_config(self.root)
        writer = rosbag2_py.SequentialWriter()
        writer.open(rosbag2_py.StorageOptions(uri=str(self.root / "bag"), storage_id="mcap"),
                    rosbag2_py.ConverterOptions("", ""))
        classes = {"/clock": Clock, "/tf_static": TFMessage,
                   "/blueboat/ground_truth/tf_static": TFMessage, "/mavros/state": State,
                   "/mavros/imu/data": Imu, "/mavros/global_position/global": NavSatFix}
        classes.update(dict(zip(self.session.CAMERA_TOPICS, (Image, Image, CameraInfo))))
        for topic in config["required"]:
            if topic == missing:
                continue
            cls = classes.get(topic, Odometry)
            type_name = f"{cls.__module__.split('.')[0]}/msg/{cls.__name__}"
            writer.create_topic(rosbag2_py.TopicMetadata(id=0, name=topic, type=type_name, serialization_format="cdr"))
            for index in range(3):
                message = cls()
                if hasattr(message, "header"):
                    message.header.stamp.sec = 20
                    message.header.stamp.nanosec = index * 100_000_000
                    if topic.startswith("/mavros/"):
                        message.header.stamp.sec = 1_792_109_695
                if topic in self.session.CAMERA_TOPICS:
                    message.header.frame_id = "camera_0_optical_frame"
                if isinstance(message, Image):
                    message.height = message.width = 2
                    message.encoding = "rgb8"
                    message.step = 6
                    message.data = bytes([index] * 12)
                if topic == self.session.CAMERA_TOPICS[1] and unmatched and index == 1:
                    message.header.stamp.nanosec += 50_000_000
                if topic == "/tf_static" and not omit_transforms:
                    for parent, child in (("base_link", "camera_0_link"), ("camera_0_link", "camera_0_optical_frame")):
                        tf = TransformStamped()
                        tf.header.frame_id, tf.child_frame_id = parent, child
                        tf.transform.rotation.w = 1.0
                        message.transforms.append(tf)
                if topic == "/blueboat/ground_truth/odometry":
                    message.pose.pose.position.x = float(index)
                writer.write(topic, serialize_message(message), 20_000_000_000 + index * 100_000_000)
        del writer

    def test_real_mcap_checks_preserve_clock_domains_and_entity_identity(self):
        self.write_bag()
        report = self.session.inspect_bag(self.root)
        self.assertTrue(report["passed"], report["errors"])
        self.assertAlmostEqual(report["rgbd"]["rate_hz"], 10)
        self.assertEqual(report["rgbd"]["matched"], 3)
        self.assertEqual(report["boat_displacement_m"], 2)
        self.assertIn("/blueboat/ground_truth/red_starboard/odometry", report["topics"])
        self.assertEqual(report["header_time_ranges_ns"]["/mavros/local_position/odom"][0], 1_792_109_695_000_000_000)

    def test_missing_buoy_truth_fails_dataset_check(self):
        missing = "/blueboat/ground_truth/red_starboard/odometry"
        self.write_bag(missing=missing)
        report = self.session.inspect_bag(self.root)
        self.assertFalse(report["passed"])
        self.assertIn(f"No messages: {missing}", report["errors"])

    def test_unmatched_depth_is_not_counted_as_a_synchronized_triple(self):
        self.write_bag(unmatched=True)
        report = self.session.inspect_bag(self.root)
        self.assertEqual(report["rgbd"]["matched"], 2)
        self.assertFalse(report["passed"])

    def test_missing_camera_transforms_fails_dataset_check(self):
        self.write_bag(omit_transforms=True)
        report = self.session.inspect_bag(self.root)
        self.assertFalse(report["passed"])
        self.assertTrue(any("Missing camera transform" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
