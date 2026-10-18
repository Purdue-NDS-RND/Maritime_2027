"""MAVROS 2.15.1 configuration ownership and frozen public policy.

The upstream loader owns FCU URLs/tgt IDs; its UAS owns source IDs,
protocol/plugins; the time child owns rate/filter settings. Global name
remapping breaks the first two owners by collapsing their ROS node names.
Source: github.com/mavlink/mavros/tree/2.15.1/mavros/src/{mavros_node.cpp,
lib/mavros_uas.cpp,plugins/sys_time.cpp}.
"""

import ast
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "Adapter/simulation/ros_ws/src/blueboat_sim_bringup"


class MavrosParameterOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((PACKAGE / "config/mavros.yaml").read_text())
        spec = importlib.util.spec_from_file_location("mavros_readiness", PACKAGE / "blueboat_sim_bringup/mavros_readiness.py")
        self.readiness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.readiness)
        tree = ast.parse((PACKAGE / "blueboat_sim_bringup/diagnostics.py").read_text())
        assignments = [item for item in tree.body if isinstance(item, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id in {"MAVROS_PARAMETERS", "PARAMETER_GROUPS"} for target in item.targets)]
        namespace = dict(PLUGIN_ALLOWLIST=self.readiness.PLUGIN_ALLOWLIST,
                         PLUGIN_DENYLIST=self.readiness.PLUGIN_DENYLIST)
        exec(compile(ast.Module(body=assignments, type_ignores=[]), "diagnostic_parameter_groups", "exec"), namespace)
        self.groups = namespace["PARAMETER_GROUPS"]

    def test_transport_loader_and_uas_policy_have_distinct_parameter_owners(self):
        loader = self.config["/mavros_node"]["ros__parameters"]
        uas = self.config["/mavros"]["ros__parameters"]
        self.assertEqual(loader["fcu_url"], "udp://:14552@")
        self.assertEqual(loader["gcs_url"], "")
        self.assertEqual((loader["tgt_system"], loader["tgt_component"]), (1, 1))
        self.assertNotIn("fcu_url", uas)
        self.assertNotIn("gcs_url", uas)
        self.assertEqual((uas["system_id"], uas["component_id"]), (255, 191))
        self.assertEqual((uas["target_system_id"], uas["target_component_id"]), (1, 1))
        self.assertEqual(uas["uas_url"], "/uas1")
        self.assertEqual(uas["fcu_protocol"], "v2.0")
        self.assertEqual(uas["plugin_allowlist"], self.readiness.PLUGIN_ALLOWLIST)
        self.assertEqual(uas["plugin_denylist"], self.readiness.PLUGIN_DENYLIST)

    def test_every_frozen_parameter_is_polled_on_its_real_owner(self):
        self.assertIn("/mavros_node", self.groups)
        self.assertIn("/mavros", self.groups)
        for owner, expected in self.groups.items():
            with self.subTest(owner=owner):
                if owner == "/mavros_router":
                    loader = self.config["/mavros_node"]["ros__parameters"]
                    actual = {"fcu_urls": [loader["fcu_url"]], "gcs_urls": [],
                              "uas_urls": [f"/uas{loader['tgt_system']}"]}
                else:
                    actual = self.config[owner]["ros__parameters"]
                self.assertEqual(self.readiness.parameter_mismatches(expected, actual), [])
        self.assertIn("fcu_url", self.groups["/mavros_node"])
        self.assertNotIn("fcu_url", self.groups["/mavros"])
        self.assertIn("system_id", self.groups["/mavros"])

    def test_clock_and_heartbeat_policy_remain_enabled_on_supported_children(self):
        timing = self.config["/mavros/time"]["ros__parameters"]
        self.assertEqual(timing["time_ref_source"], "fcu")
        self.assertEqual(timing["timesync_mode"], "MAVLINK")
        self.assertEqual(timing["timesync_rate"], 10.0)
        self.assertEqual(timing["system_time_rate"], 1.0)
        self.assertNotIn("timesync_avg_alpha", timing)
        # Contract 2.0.0 records the supported v2.15.1 scheduled defaults;
        # the old average-alpha alias was undeclared and never effective.
        gains = {"timesync_alpha_initial": 0.05, "timesync_beta_initial": 0.05,
                 "timesync_alpha_final": 0.003, "timesync_beta_final": 0.003,
                 "convergence_window": 500}
        for name, expected in gains.items():
            self.assertEqual(timing[name], expected)
            self.assertEqual(self.groups["/mavros/time"][name], expected)
        heartbeat = self.config["/mavros/sys"]["ros__parameters"]
        self.assertEqual(heartbeat["heartbeat_rate"], 1.0)
        self.assertEqual(heartbeat["heartbeat_mav_type"], "ONBOARD_CONTROLLER")
        self.assertFalse(heartbeat["disable_diag"])
        self.assertFalse(self.config["/mavros/local_position"]["ros__parameters"]["tf.send"])
        self.assertFalse(self.config["/mavros/global_position"]["ros__parameters"]["tf.send"])

    def test_mavros_diagnostic_identifies_contract_v2(self):
        tree = ast.parse((PACKAGE / "blueboat_sim_bringup/diagnostics.py").read_text())
        function = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "status")
        namespace = dict(DiagnosticStatus=SimpleNamespace, KeyValue=SimpleNamespace)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "diagnostic_status", "exec"), namespace)
        status = namespace["status"]("mavros_adapter/source_readiness", 0, "ready", True)
        values = {value.key: value.value for value in status.values}
        self.assertEqual(values["contract_version"], "2.0.0")
        self.assertEqual(values["source_ready"], "true")

    def test_launch_keeps_loader_router_and_uas_default_names(self):
        tree = ast.parse((PACKAGE / "launch/bringup.launch.py").read_text())
        calls = [item for item in ast.walk(tree) if isinstance(item, ast.Call)
                 and any(keyword.arg == "package" and isinstance(keyword.value, ast.Constant)
                         and keyword.value.value == "mavros" for keyword in item.keywords)]
        self.assertEqual(len(calls), 1)
        keywords = {item.arg: item.value for item in calls[0].keywords}
        self.assertNotIn("name", keywords, "global __node remap collapses loader/router/UAS parameter ownership")
        self.assertIn("parameters", keywords)


class PluginConfigurationResponseTests(unittest.TestCase):
    """Execute production configurator with non-iterable SetParameters_Response."""
    def setUp(self):
        self.namespace = SimpleNamespace
        self.sent = {}
        self.clients = {}
        self.cancelled = []
        self.logs = []
        self.stream_requests = []
        self.stream_ready = True
        filename = PACKAGE / "config/mavros.yaml"
        harness = self
        class NodeHarness:
            @property
            def clients(self):
                # rclpy.Node owns this read-only property. Production state
                # must use another name even in the isolated harness.
                return ()
            def __init__(self, name, parameter_overrides=None):
                self.name = name
            def declare_parameter(self, name, default):
                return SimpleNamespace(value=str(filename))
            def create_timer(self, period, callback):
                return SimpleNamespace(cancel=lambda: harness.cancelled.append(True))
            def create_client(self, kind, topic):
                def send(request):
                    harness.stream_requests.append(request)
                    return SimpleNamespace(done=lambda: True, result=lambda: SimpleNamespace())
                return SimpleNamespace(service_is_ready=lambda: harness.stream_ready, call_async=send)
            def create_subscription(self, kind, topic, callback, depth):
                callback(SimpleNamespace(connected=True))
            def get_logger(self):
                return SimpleNamespace(info=harness.logs.append)
        def parameter_client(node, owner):
            client = SimpleNamespace(services_are_ready=lambda: True)
            def send(parameters):
                harness.sent[owner] = parameters
                return SimpleNamespace(done=lambda: True, result=lambda: SimpleNamespace(results=[
                    SimpleNamespace(successful=True, reason="") for _ in parameters
                ]))
            client.set_parameters = send
            self.clients[owner] = client
            return client
        tree = ast.parse((PACKAGE / "blueboat_sim_bringup/configure_mavros.py").read_text())
        cls = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "ConfigureMavros")
        namespace = dict(Node=NodeHarness, Path=Path, yaml=yaml,
                         os=SimpleNamespace(environ={"STACK_STARTUP_TIMEOUT": "180"}),
                         time=SimpleNamespace(monotonic=lambda: 10.0),
                         AsyncParameterClient=parameter_client,
                         State=object, StreamRate=SimpleNamespace(Request=lambda **kw: SimpleNamespace(**kw)),
                         Parameter=lambda name, value: SimpleNamespace(name=name, value=value))
        exec(compile(ast.Module(body=[cls], type_ignores=[]), "configure_mavros_harness", "exec"), namespace)
        self.node = namespace["ConfigureMavros"]()

    def test_only_plugin_owners_are_applied_once_then_timer_stops(self):
        self.assertEqual(set(self.node.groups), {"/mavros/sys", "/mavros/time", "/mavros/local_position", "/mavros/global_position", "/mavros/imu"})
        self.node.configure()
        self.assertEqual(set(self.sent), set(self.node.groups))
        for owner, parameters in self.sent.items():
            self.assertEqual({parameter.name: parameter.value for parameter in parameters}, self.node.groups[owner])
        self.node.configure()
        self.assertEqual(self.node.completed, set(self.node.groups))
        self.node.configure()
        self.assertTrue(self.cancelled)
        previous = dict(self.sent)
        self.node.configure()
        self.assertEqual(self.sent, previous)
        self.assertEqual(len(self.stream_requests), 1)
        self.assertEqual(vars(self.stream_requests[0]), dict(stream_id=0, message_rate=4, on_off=True))

    def test_baseline_waits_for_connection_and_never_resets_session_intervals(self):
        self.node.connected = False
        for _ in range(4):
            self.node.configure()
        self.assertEqual(self.stream_requests, [])
        self.assertFalse(self.cancelled)
        self.node.connected = True
        self.stream_ready = False
        self.node.configure()
        self.assertEqual(self.stream_requests, [])
        self.stream_ready = True
        for _ in range(5):
            self.node.configure()
        self.assertEqual(len(self.stream_requests), 1)
        self.assertTrue(self.cancelled)

    def test_rejected_or_incomplete_service_results_cannot_complete_configuration(self):
        for results in ([], [self.namespace(successful=False, reason="unsupported parameter")]):
            with self.subTest(results=results):
                self.node.futures["/mavros/time"] = self.namespace(done=lambda: True, result=lambda: self.namespace(results=results))
                with self.assertRaisesRegex(RuntimeError, "configuration rejected"):
                    self.node.configure()
                self.assertNotIn("/mavros/time", self.node.completed)
                self.assertFalse(self.cancelled)

    def test_unavailable_or_pending_service_remains_unconfigured(self):
        for client in self.clients.values():
            client.services_are_ready = lambda: False
        self.node.configure()
        self.assertEqual(self.sent, {})
        self.assertEqual(self.node.completed, set())
        self.node.futures["/mavros/time"] = self.namespace(done=lambda: False)
        self.node.configure()
        self.assertEqual(self.node.completed, set())
        self.assertFalse(self.cancelled)

    def test_startup_deadline_is_fail_fast_and_reports_pending_owner(self):
        self.node.deadline = 10.0
        with self.assertRaisesRegex(RuntimeError, "/mavros/time"):
            self.node.configure()
        self.assertFalse(self.cancelled)


class ConfigureMavrosRosConstructionTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("rclpy") is not None, "ROS unavailable: run this constructor check inside the Simulation Adapter")
    def test_actual_rclpy_constructor_accepts_configuration_without_spinning_or_sending_commands(self):
        import rclpy
        source = PACKAGE / "blueboat_sim_bringup/configure_mavros.py"
        spec = importlib.util.spec_from_file_location("configure_mavros_integration", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        configuration = PACKAGE / "config/mavros.yaml"
        from rclpy.parameter import Parameter
        rclpy.init(args=[])
        node = None
        try:
            # Actual Node initialization catches collisions with rclpy's own
            # properties. No spinning means parameter services are not called.
            node = module.ConfigureMavros(parameter_overrides=[Parameter("configuration_file", value=str(configuration))])
            self.assertEqual(node.get_name(), "mavros_configuration")
            self.assertEqual(set(node.parameter_clients), set(node.groups))
            self.assertEqual(node.completed, set())
            self.assertEqual(node.futures, {})
            self.assertGreater(node.deadline, 0)
        finally:
            if node is not None:
                node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    unittest.main()
