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


if __name__ == "__main__":
    unittest.main()
