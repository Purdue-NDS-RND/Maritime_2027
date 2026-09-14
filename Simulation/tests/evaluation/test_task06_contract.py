"""Focused source-level and pure behavior checks for the staged Task 06 boundary."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
ADAPTER = ROOT / "Adapter" / "simulation"
BRINGUP = ADAPTER / "ros_ws" / "src" / "blueboat_sim_bringup"
sys.path.insert(0, str(BRINGUP))

from blueboat_sim_bringup.manifest import load_manifest, truth_bridge_arguments
from blueboat_sim_bringup.camera_contract import freshness, validate_camera_info, validate_image
from blueboat_sim_bringup.camera_readiness import CameraReadinessModel
from blueboat_sim_bringup.mavros_readiness import PUBLIC_SERVICES, PUBLIC_TOPICS, validate_fix, validate_graph


def manifest(buoys):
    return {
        "schema_version": 1,
        "scenario": "repeated_red",
        "seed": None,
        "world": "blueboat_rgbd",
        "boat_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw_rad": 0.0},
        "camera_mount": {"x": 0.35, "y": 0.0, "z": 0.4},
        "buoys": buoys,
    }


def buoy(name, y):
    return {
        "name": name,
        "marker_id": 1,
        "category": "red",
        "gazebo_model_name": name,
        "model_uri": "model://aruco_buoy_id1",
        "model_pose": {"x": 7.0, "y": y, "z": 0.0, "yaw_deg": 180.0, "yaw_rad": 3.141592653589793},
        "marker_plane_center": {"x": 6.689, "y": y, "z": 0.75, "normal_x": -1.0, "normal_y": 0.0},
        "truth_topic": f"/blueboat/ground_truth/{name}/odometry",
        "evaluation_key": name,
    }


class Task06ContractTests(unittest.TestCase):
    def write_manifest(self, value):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.addCleanup(lambda: os.unlink(handle.name))
        json.dump(value, handle)
        handle.close()
        return handle.name

    def test_repeated_category_truth_bridges_use_entity_identity(self):
        value = load_manifest(self.write_manifest(manifest([buoy("red_gate_port", 1.5), buoy("red_gate_starboard", -1.5)])))
        bridges = truth_bridge_arguments(value)
        self.assertEqual([item[0] for item in bridges], ["red_gate_port", "red_gate_starboard"])
        self.assertEqual([item[1] for item in bridges], [
            "/blueboat/ground_truth/red_gate_port/odometry",
            "/blueboat/ground_truth/red_gate_starboard/odometry",
        ])
        self.assertNotEqual(bridges[0][2], bridges[1][2])

    def test_manifest_fails_closed_on_version_and_derived_identity(self):
        value = manifest([buoy("red_gate_port", 1.5)])
        value["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "schema_version"):
            load_manifest(self.write_manifest(value))

    def test_manifest_enforces_geometry_invariants(self):
        cases = []
        outside = manifest([buoy("red_gate_port", 1.5)])
        outside["buoys"][0]["model_pose"]["x"] = 3.9
        cases.append((outside, "outside"))
        close = manifest([buoy("red_gate_port", 0.0), buoy("red_gate_starboard", 0.5)])
        cases.append((close, "less than 1 metre"))
        nonunit = manifest([buoy("red_gate_port", 1.5)])
        nonunit["buoys"][0]["marker_plane_center"]["normal_x"] = -2.0
        cases.append((nonunit, "unit length"))
        inconsistent = manifest([buoy("red_gate_port", 1.5)])
        inconsistent["buoys"][0]["marker_plane_center"]["normal_x"] = 0.0
        inconsistent["buoys"][0]["marker_plane_center"]["normal_y"] = 1.0
        cases.append((inconsistent, "disagrees with yaw"))
        for value, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    load_manifest(self.write_manifest(value))
        value = manifest([buoy("red_gate_port", 1.5)])
        value["buoys"][0]["truth_topic"] = "/blueboat/ground_truth/buoy_1/odometry"
        with self.assertRaisesRegex(ValueError, "truth_topic"):
            load_manifest(self.write_manifest(value))

    def test_runtime_contains_no_evaluator_or_opencv_dependency(self):
        dockerfile = (ADAPTER / "container" / "Dockerfile").read_text()
        setup = (BRINGUP / "setup.py").read_text()
        launch = (BRINGUP / "launch" / "bringup.launch.py").read_text()
        self.assertNotIn("opencv", dockerfile.lower())
        self.assertNotIn("cv_bridge", dockerfile)
        self.assertNotIn("sensor_smoke", setup + launch)
        self.assertNotIn("mavros_smoke", setup + launch)
        self.assertEqual(launch.count('package="mavros"'), 1)
        self.assertIn("on_exit=Shutdown", launch)

    def test_public_camera_names_and_frames_are_normalized(self):
        sources = "\n".join(path.read_text() for path in [
            BRINGUP / "config" / "bridge.yaml",
            BRINGUP / "config" / "bridge_rgb.yaml",
            BRINGUP / "config" / "bridge_depth.yaml",
            BRINGUP / "launch" / "bringup.launch.py",
            ADAPTER / "ros_ws" / "src" / "blueboat_camera_adapter" / "src" / "camera_boundary.cpp",
        ])
        for topic in (
            "/sensors/camera_0/color/image_raw",
            "/sensors/camera_0/depth/image_rect_raw",
            "/sensors/camera_0/color/camera_info",
        ):
            self.assertIn(topic, sources)
        self.assertIn("camera_0_link", sources)
        self.assertIn("camera_0_optical_frame", sources)
        self.assertIn("quiet_NaN", sources)

    def test_evaluator_guard_fails_without_explicit_simulation_opt_in(self):
        package = ROOT / "Simulation" / "tests" / "evaluation" / "ros_ws" / "src" / "blueboat_sim_evaluation"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(package)
        env["ADAPTER_ENVIRONMENT"] = "simulation"
        env.pop("SIMULATION_EVALUATION", None)
        result = subprocess.run(
            [sys.executable, "-c", "from blueboat_sim_evaluation.guard import require_explicit_simulation; require_explicit_simulation()"],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SIMULATION_EVALUATION=1", result.stderr)

    def test_command_evaluator_rejects_non_sitl_transport(self):
        package = ROOT / "Simulation" / "tests" / "evaluation" / "ros_ws" / "src" / "blueboat_sim_evaluation"
        env = os.environ.copy()
        env.update({"PYTHONPATH": str(package), "ADAPTER_ENVIRONMENT": "simulation", "SIMULATION_EVALUATION": "1", "FCU_URL": "serial:///dev/ttyACM0"})
        result = subprocess.run(
            [sys.executable, "-c", "from blueboat_sim_evaluation.guard import require_explicit_simulation; require_explicit_simulation(command_capable=True)"],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("udp://:14552@", result.stderr)

    def test_camera_freshness_distinguishes_error_stale_and_ready(self):
        self.assertEqual(freshness(101, 100, 100, 100), ("ERROR", "future_acquisition_stamp"))
        self.assertEqual(freshness(100, 101, 100, 100), ("ERROR", "steady_clock_regression"))
        self.assertEqual(freshness(1, 1, 100_000_002, 2), ("STALE", "acquisition_timeout"))
        self.assertEqual(freshness(1, 1, 2, 2_000_000_002), ("STALE", "arrival_timeout"))
        self.assertEqual(freshness(1, 1, 2, 2), ("OK", "ready"))

    def test_camera_content_checks_reject_wrong_frame_and_uncalibrated_info(self):
        class Header:
            frame_id = "private_frame"
        class Image:
            header = Header()
            width, height, step, encoding, data = 1, 1, 3, "rgb8", b"abc"
        self.assertEqual(validate_image(Image()), "frame_mismatch")
        class Info:
            header = type("Header", (), {"frame_id": "camera_0_optical_frame"})()
            width, height, distortion_model = 1, 1, "plumb_bob"
            d, k, r, p = [0.0] * 5, [0.0] * 9, [0.0] * 9, [0.0] * 12
        self.assertEqual(validate_camera_info(Info()), "invalid_calibration")

    def test_camera_matcher_queues_exact_triples_and_recovers_only_on_valid_triple(self):
        class Stamp:
            def __init__(self, value): self.sec, self.nanosec = divmod(value, 1_000_000_000)
        class Header:
            def __init__(self, value): self.stamp, self.frame_id = Stamp(value), "camera_0_optical_frame"
        class Image:
            def __init__(self, value, depth=False):
                self.header, self.width, self.height = Header(value), 2, 1
                self.encoding = "32FC1" if depth else "rgb8"
                self.step = 8 if depth else 6
                self.data = bytes(self.step)
        class Info:
            def __init__(self, value):
                self.header, self.width, self.height = Header(value), 2, 1
                self.distortion_model, self.d = "plumb_bob", [0.0] * 5
                self.k = [1.0,0,0,0,1.0,0,0,0,1.0]
                self.r = [1.0,0,0,0,1.0,0,0,0,1.0]
                self.p = [1.0,0,0,0,0,1.0,0,0,0,0,1.0,0]
        model = CameraReadinessModel(queue_limit=2)
        now = 1_000_000_000
        self.assertFalse(model.ingest("color", Image(now + 1), now, 10))
        self.assertEqual(model.rejected_count, 1)
        for stream, message in (("color", Image(now)), ("depth", Image(now, True)), ("info", Info(now))):
            self.assertTrue(model.ingest(stream, message, now, 20))
        components, evidence = model.snapshot(now + 1, 21)
        self.assertEqual(components["source_readiness"], ("OK", "ready"))
        self.assertEqual(evidence["rejected_count"], 1)
        model.ingest("color", Image(now + 10), now + 20, 30)
        model.ingest("depth", Image(now + 11, True), now + 20, 31)
        model.ingest("info", Info(now + 11), now + 20, 32)
        components, evidence = model.snapshot(now + 100_000_020, 40)
        self.assertEqual(components["synchronization"][0], "ERROR")
        self.assertGreater(evidence["unmatched_count"], 0)

    def test_camera_matcher_reports_bounded_queue_overflow_with_evidence(self):
        class Stamp:
            def __init__(self, value): self.sec, self.nanosec = divmod(value, 1_000_000_000)
        class Message:
            def __init__(self, value):
                self.header = type("Header", (), {"stamp": Stamp(value), "frame_id": "camera_0_optical_frame"})()
                self.width, self.height, self.step, self.encoding, self.data = 1, 1, 3, "rgb8", b"abc"
        model = CameraReadinessModel(queue_limit=2)
        for value in (100, 101, 102):
            model.ingest("color", Message(value), 200, value)
        components, evidence = model.snapshot(200, 200)
        self.assertEqual(components["synchronization"], ("ERROR", "queue_overflow"))
        self.assertEqual(evidence["overflow_count"], 1)
        self.assertEqual(evidence["color_header_stamp_ns"], 102)

    def test_mavros_fix_validation_fails_closed_on_invalid_fix(self):
        class Fix:
            header = type("Header", (), {"stamp": type("Stamp", (), {"sec": 1, "nanosec": 0})()})()
            status = type("Status", (), {"status": -1})()
            latitude, longitude, altitude = 0.0, 0.0, 0.0
            position_covariance = [0.0] * 9
            position_covariance_type = 0
        self.assertFalse(validate_fix(Fix()))

    def test_mavros_graph_requires_exact_full_surface_and_types(self):
        topics = {name: [kind] for name, kind in PUBLIC_TOPICS.items()}
        services = {name: [kind] for name, kind in PUBLIC_SERVICES.items()}
        self.assertEqual(validate_graph(topics, services), (True, "ready"))
        topics["/mavros/state"] = ["example_msgs/msg/Wrong"]
        valid, reason = validate_graph(topics, services)
        self.assertFalse(valid)
        self.assertEqual(reason, "topic_contract_mismatch:/mavros/state")

    def test_manual_mode_requires_observed_state_transition(self):
        package = ROOT / "Simulation" / "tests" / "evaluation" / "ros_ws" / "src" / "blueboat_sim_evaluation"
        sys.path.insert(0, str(package))
        from blueboat_sim_evaluation.safety import manual_mode_observed
        self.assertFalse(manual_mode_observed(None))
        self.assertFalse(manual_mode_observed(type("State", (), {"mode": "HOLD"})()))
        self.assertTrue(manual_mode_observed(type("State", (), {"mode": "MANUAL"})()))


if __name__ == "__main__":
    unittest.main()
