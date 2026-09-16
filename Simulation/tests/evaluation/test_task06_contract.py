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
from blueboat_sim_bringup.mavros_readiness import PUBLIC_SERVICES, PUBLIC_TOPICS, parameter_mismatches, validate_fix, validate_graph


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

    def test_camera_diagnostics_use_aggregate_readiness_and_exact_reasons(self):
        source = (ADAPTER / "ros_ws" / "src" / "blueboat_camera_adapter" / "src" / "camera_boundary.cpp").read_text()
        self.assertIn('evidence.value = aggregate_ready', source)
        self.assertIn('return "frame_mismatch"', source)
        self.assertIn('return "unsupported_encoding"', source)
        self.assertIn('return "invalid_dimensions"', source)
        self.assertIn('return "invalid_data_layout"', source)
        self.assertNotIn('"invalid_color_content"', source)
        self.assertNotIn('"invalid_depth_content"', source)
        info_validator = source[source.index("std::string invalid_info_reason"):source.index("template<typename Queue>")]
        self.assertIn('message.header.frame_id != kPrivateFrame) return "frame_mismatch"', info_validator)
        self.assertIn('message.width == 0 || message.height == 0) return "invalid_dimensions"', info_validator)
        self.assertIn('return calibrated ? "" : "invalid_calibration"', info_validator)

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

    def test_camera_anchor_waits_when_only_present_stream_advanced(self):
        header = ADAPTER / "ros_ws" / "src" / "blueboat_camera_adapter" / "include" / "blueboat_camera_adapter" / "matching.hpp"
        source = f'''#include <cassert>\n#include "{header}"\nint main() {{\nusing blueboat_camera_adapter::reject_anchor;\nassert(!reject_anchor(false, true, true, false, false));\nassert(reject_anchor(true, true, false, false, false));\nassert(reject_anchor(false, false, true, false, true));\n}}'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.cpp"
            binary = Path(directory) / "test"
            path.write_text(source)
            subprocess.run(["g++", "-std=c++17", str(path), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_camera_tf_contract_accepts_only_exact_public_chain(self):
        header = ADAPTER / "ros_ws" / "src" / "blueboat_camera_adapter" / "include" / "blueboat_camera_adapter" / "tf_validation.hpp"
        source = f'''#include <cassert>\n#include "{header}"\nint main() {{\nusing blueboat_camera_adapter::valid_camera_transform;\nassert(valid_camera_transform("base_link", "camera_0_link", .35,0,.4,0,0,0,1));\nassert(valid_camera_transform("camera_0_link", "camera_0_optical_frame", 0,0,0,-.5,.5,-.5,.5));\nassert(!valid_camera_transform("world", "camera_0_link", .35,0,.4,0,0,0,1));\nassert(!valid_camera_transform("base_link", "camera_0_link", .36,0,.4,0,0,0,1));\nassert(!valid_camera_transform("camera_0_link", "camera_0_optical_frame", 0,0,0,0,0,0,1));\n}}'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.cpp"
            binary = Path(directory) / "test"
            path.write_text(source)
            subprocess.run(["g++", "-std=c++17", str(path), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_mavlink_wire_evidence_requires_udp_14552_and_magic_fd(self):
        header = ADAPTER / "ros_ws" / "src" / "blueboat_mavlink_monitor" / "include" / "blueboat_mavlink_monitor" / "packet.hpp"
        monitor = (ADAPTER / "ros_ws" / "src" / "blueboat_mavlink_monitor" / "src" / "mavlink_v2_monitor.cpp").read_text()
        self.assertNotIn('if_nametoindex("lo")', monitor)
        self.assertIn("AF_PACKET", monitor)
        source = f'''#include <array>\n#include <cassert>\n#include "{header}"\nint main() {{\nstd::array<unsigned char,43> p{{}}; p[14]=0x45; p[23]=17; p[36]=0x38; p[37]=0xD8; p[42]=0xFD;\nassert(blueboat_mavlink_monitor::is_mavlink_v2_udp_14552(p.data(),p.size()));\np[42]=0xFE; assert(!blueboat_mavlink_monitor::is_mavlink_v2_udp_14552(p.data(),p.size()));\np[42]=0xFD; p[36]=0; p[37]=1; assert(!blueboat_mavlink_monitor::is_mavlink_v2_udp_14552(p.data(),p.size()));\n}}'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.cpp"
            binary = Path(directory) / "test"
            path.write_text(source)
            subprocess.run(["g++", "-std=c++17", str(path), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

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

    def test_mavros_child_parameter_override_fails_closed(self):
        expected = {"heartbeat_rate": 1.0, "disable_diag": False}
        self.assertEqual(parameter_mismatches(expected, dict(expected)), [])
        self.assertEqual(parameter_mismatches(expected, {"heartbeat_rate": 2.0, "disable_diag": False}), ["heartbeat_rate"])
        self.assertEqual(parameter_mismatches(expected, {"heartbeat_rate": 1.0}), ["disable_diag"])

    def test_diagnostics_use_the_jazzy_parameter_client_readiness_api(self):
        diagnostics = (ROOT / "Adapter/simulation/ros_ws/src/blueboat_sim_bringup/blueboat_sim_bringup/diagnostics.py").read_text()
        self.assertIn("client.services_are_ready()", diagnostics)
        self.assertNotIn("client.service_is_ready()", diagnostics)

    def test_guided_mode_requires_observed_state_transition(self):
        package = ROOT / "Simulation" / "tests" / "evaluation" / "ros_ws" / "src" / "blueboat_sim_evaluation"
        sys.path.insert(0, str(package))
        from blueboat_sim_evaluation.safety import guided_mode_observed
        self.assertFalse(guided_mode_observed(None))
        self.assertFalse(guided_mode_observed(type("State", (), {"mode": "HOLD"})()))
        self.assertTrue(guided_mode_observed(type("State", (), {"mode": "GUIDED"})()))


if __name__ == "__main__":
    unittest.main()
