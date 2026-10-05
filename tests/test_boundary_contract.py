"""Negative tests of observed runtime boundary evidence, independent of ROS."""

import copy
import unittest

from boundary_contract import EXPECTED_FRAMES, MISSION, PLACEHOLDER, REQUIRED_READY, validate_evidence


class BoundaryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.diagnostics = {name: (0, "ready", {"source_ready": "true"}) for name in REQUIRED_READY}
        self.diagnostics[MISSION] = (1, "mission_policy_unavailable", {"source_ready": "false"})
        self.diagnostics[PLACEHOLDER] = (1, "preimplementation_placeholder", {
            "adapter_environment": "simulation", "placeholder_active": "true",
            "mission_ready": "false", "vehicle_commands_permitted": "false",
        })

    def check(self, **overrides):
        evidence = dict(diagnostics=self.diagnostics, frames=EXPECTED_FRAMES,
                        placeholder_publishers=["/diagnostics", "/rosout", "/parameter_events"],
                        placeholder_subscribers=[], placeholder_clients=[])
        evidence.update(overrides)
        validate_evidence(**evidence)

    def test_all_sources_ready_does_not_make_placeholder_mission_ready(self):
        self.check()

    def test_liveness_does_not_substitute_for_any_source_or_fcu_readiness(self):
        for name in REQUIRED_READY:
            for fault in (None, (0, "ready", {"source_ready": "false"}), (3, "stale", {"source_ready": "true"})):
                with self.subTest(name=name, fault=fault):
                    diagnostic = copy.deepcopy(self.diagnostics)
                    if fault is None:
                        del diagnostic[name]
                    else:
                        diagnostic[name] = fault
                    with self.assertRaises(AssertionError):
                        self.check(diagnostics=diagnostic)

    def test_application_readiness_and_command_permission_fail_closed(self):
        for key, invalid in (("mission_ready", "true"), ("vehicle_commands_permitted", "true"),
                             ("placeholder_active", "false"), ("adapter_environment", "hardware")):
            with self.subTest(key=key):
                diagnostic = copy.deepcopy(self.diagnostics)
                diagnostic[PLACEHOLDER][2][key] = invalid
                with self.assertRaises(AssertionError):
                    self.check(diagnostics=diagnostic)
        diagnostic = copy.deepcopy(self.diagnostics)
        diagnostic[MISSION] = (0, "ready", {"source_ready": "true"})
        with self.assertRaises(AssertionError):
            self.check(diagnostics=diagnostic)

    def test_truth_tf_and_missing_camera_tf_are_rejected(self):
        for frames in (set(), EXPECTED_FRAMES | {("map", "base_link")},
                       EXPECTED_FRAMES | {("world", "red_gate_port")}):
            with self.subTest(frames=frames), self.assertRaises(AssertionError):
                self.check(frames=frames)

    def test_command_and_truth_capability_are_rejected(self):
        for change in ({"placeholder_publishers": ["/mavros/setpoint_velocity/cmd_vel"]},
                       {"placeholder_subscribers": ["/blueboat/ground_truth/red_gate_port/odometry"]},
                       {"placeholder_clients": ["/mavros/cmd/arming"]}):
            with self.subTest(change=change), self.assertRaises(AssertionError):
                self.check(**change)


if __name__ == "__main__":
    unittest.main()
