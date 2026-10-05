"""Run the actual FCU decision method without ROS transport or command clients.

Only the method is loaded, so host tests need neither ROS nor FCU connectivity.
The method's globals (clock/status values) are supplied by the harness.
"""

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "Adapter/simulation/ros_ws/src/blueboat_sim_bringup/blueboat_sim_bringup/diagnostics.py"


def decision_method():
    tree = ast.parse(SOURCE.read_text())
    cls = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "AdapterDiagnostics")
    method = next(item for item in cls.body if isinstance(item, ast.FunctionDef) and item.name == "fcu_state")
    namespace = {"time": SimpleNamespace(monotonic_ns=lambda: 10_000_000_000),
                 "DiagnosticStatus": SimpleNamespace(OK=0, WARN=1, ERROR=2, STALE=3)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["fcu_state"]


class FcuReadinessBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.state = SimpleNamespace(
            state=(10_000_000_000, SimpleNamespace(connected=True)),
            telemetry={name: (10_000_000_000, True) for name in ("imu", "local", "global")},
            time_reference_arrival=10_000_000_000, timesync=(10_000_000_000, True),
            mavros_diagnostics={}, prohibited_tf=None, wire_v2=True,
        )
        self.decide = decision_method()

    def test_complete_evidence_is_ready_without_making_a_mission_claim(self):
        self.assertEqual(self.decide(self.state, True), (0, "ready", True))

    def test_live_process_and_connected_heartbeat_cannot_replace_source_contract(self):
        self.assertEqual(self.decide(self.state, False), (2, "source_unready", False))
        self.state.telemetry["imu"] = None
        self.assertEqual(self.decide(self.state, True), (3, "telemetry_stale:imu", False))

    def test_disconnected_and_stale_fcu_fail_closed(self):
        self.state.state[1].connected = False
        self.assertEqual(self.decide(self.state, True), (2, "fcu_disconnected", False))
        self.state.state = (7_000_000_000, SimpleNamespace(connected=True))
        self.assertEqual(self.decide(self.state, True), (3, "state_stale", False))

    def test_invalid_or_stale_telemetry_and_clocks_are_not_fcu_ready(self):
        cases = (
            ("telemetry", {"imu": (10_000_000_000, False)}, "telemetry_invalid:imu"),
            ("time_reference_arrival", None, "time_reference_stale"),
            ("timesync", None, "timesync_stale"),
            ("timesync", (10_000_000_000, False), "timesync_invalid"),
        )
        for field, value, reason in cases:
            with self.subTest(field=field, reason=reason):
                previous = getattr(self.state, field)
                setattr(self.state, field, value)
                level, observed, ready = self.decide(self.state, True)
                self.assertGreaterEqual(level, 2)
                self.assertEqual(observed, reason)
                self.assertFalse(ready)
                setattr(self.state, field, previous)

    def test_wire_protocol_errors_and_navigation_truth_tf_invalidate_readiness(self):
        self.state.wire_v2 = False
        self.assertEqual(self.decide(self.state, True), (2, "mavlink_v2_wire_unverified", False))
        self.state.wire_v2 = True
        self.state.prohibited_tf = "map->base_link"
        self.assertEqual(self.decide(self.state, True), (2, "prohibited_mavros_tf:map->base_link", False))
        self.state.prohibited_tf = None
        self.state.mavros_diagnostics = {"FCU": (2, "transport error")}
        self.assertEqual(self.decide(self.state, True), (2, "mavros_diagnostic_error:transport error", False))


class ParameterResponseBehaviorTests(unittest.TestCase):
    """Use ROS GetParameters_Response shape: non-iterable .values payload.

    ParameterValue fixtures expose the wire fields, never a Python .value.
    The converter harness models rclpy's public type-to-field conversion.
    """
    def setUp(self):
        self.expected = {"enabled": False, "heartbeat_rate": 1.0, "frame_id": "map",
                         "plugins": ["sys_status", "imu"]}
        self.response = SimpleNamespace(values=[
            SimpleNamespace(type=1, bool_value=False),
            SimpleNamespace(type=3, double_value=1.0),
            SimpleNamespace(type=4, string_value="map"),
            SimpleNamespace(type=9, string_array_value=["sys_status", "imu"]),
        ])
        self.converted = []
        try:
            from rclpy.parameter import parameter_value_to_python as ros_converter
        except ModuleNotFoundError:
            ros_converter = None
        def convert(value):
            self.converted.append(value)
            if ros_converter is not None:
                return ros_converter(value)
            field = {1: "bool_value", 3: "double_value", 4: "string_value", 9: "string_array_value"}[value.type]
            return getattr(value, field)
        tree = ast.parse(SOURCE.read_text())
        cls = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "AdapterDiagnostics")
        method = next(item for item in cls.body if isinstance(item, ast.FunctionDef) and item.name == "poll_parameters")
        spec = importlib.util.spec_from_file_location("mavros_readiness", SOURCE.with_name("mavros_readiness.py"))
        readiness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(readiness)
        namespace = dict(PARAMETER_GROUPS={"/mavros": self.expected}, parameter_value_to_python=convert,
                         parameter_mismatches=readiness.parameter_mismatches)
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), namespace)
        self.poll = namespace["poll_parameters"]
        self.future = SimpleNamespace(done=lambda: True, result=lambda: self.response)
        self.state = SimpleNamespace(parameter_futures={"/mavros": self.future},
                                     parameter_clients={"/mavros": None}, parameter_values={},
                                     parameter_errors={"/mavros": "parameters_unobserved"})

    def test_service_response_values_are_converted_and_readiness_evidence_clears(self):
        self.poll(self.state)
        self.assertEqual(self.state.parameter_values["/mavros"], self.expected)
        self.assertEqual(self.converted, self.response.values)
        self.assertIsNone(self.state.parameter_errors["/mavros"])
        self.assertIsNone(self.state.parameter_futures["/mavros"])

    def test_real_parameter_override_is_rejected_after_conversion(self):
        self.response.values[1].double_value = 2.0
        self.poll(self.state)
        self.assertEqual(self.state.parameter_errors["/mavros"], "parameter_mismatch:heartbeat_rate")
        self.assertIsNone(self.state.parameter_futures["/mavros"])

    def test_missing_parameter_and_failed_service_query_fail_closed(self):
        self.response.values.pop()
        self.poll(self.state)
        self.assertIn("plugins", self.state.parameter_errors["/mavros"])
        def failed_result():
            raise RuntimeError("service unavailable")
        self.state.parameter_futures["/mavros"] = SimpleNamespace(done=lambda: True, result=failed_result)
        self.poll(self.state)
        self.assertEqual(self.state.parameter_errors["/mavros"], "parameter_query_failed:service unavailable")
        self.assertIsNone(self.state.parameter_futures["/mavros"])

    def test_pending_future_is_not_claimed_as_parameter_readiness(self):
        self.future.done = lambda: False
        self.poll(self.state)
        self.assertEqual(self.state.parameter_errors["/mavros"], "parameters_unobserved")
        self.assertEqual(self.state.parameter_values, {})
        self.assertEqual(self.converted, [])


class SemanticHealthBehaviorTests(unittest.TestCase):
    def setUp(self):
        source = ROOT / "Adapter/simulation/ros_ws/src/blueboat_sim_bringup/blueboat_sim_bringup/healthcheck.py"
        tree = ast.parse(source.read_text())
        cls = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "Health")
        method = next(item for item in cls.body if isinstance(item, ast.FunctionDef) and item.name == "failures")
        namespace = {"time": SimpleNamespace(monotonic=lambda: 10.0), "DiagnosticStatus": SimpleNamespace(OK=0)}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
        self.failures = namespace["failures"]
        required = {"mavros_adapter/source_readiness", "mavros_adapter/fcu_readiness", "camera_adapter/camera_0/source_readiness"}
        self.health = SimpleNamespace(live=lambda: True, required_diagnostics=required, samples={})
        for name in required:
            self.health.samples[name] = (10.0, SimpleNamespace(level=0, message="ready", values=[SimpleNamespace(key="source_ready", value="true")]))

    def test_liveness_plus_fresh_sources_are_healthy_without_mission_policy(self):
        self.assertEqual(self.failures(self.health), [])
        self.health.live = lambda: False
        self.assertIn("process_liveness", self.failures(self.health)[0])

    def test_live_nodes_do_not_substitute_for_each_missing_stale_or_unready_source(self):
        for name in self.health.required_diagnostics:
            original = self.health.samples[name]
            for replacement in (None, (7.9, original[1]),
                                (10.0, SimpleNamespace(level=3, message="stale", values=original[1].values)),
                                (10.0, SimpleNamespace(level=0, message="ready", values=[])),
                                (10.0, SimpleNamespace(level=0, message="ready", values=[SimpleNamespace(key="source_ready", value="false")]))):
                with self.subTest(name=name, replacement=replacement):
                    if replacement is None:
                        self.health.samples.pop(name)
                    else:
                        self.health.samples[name] = replacement
                    failures = self.failures(self.health)
                    self.assertEqual(len(failures), 1)
                    self.assertTrue(failures[0].startswith(name))
            self.health.samples[name] = original


if __name__ == "__main__":
    unittest.main()
