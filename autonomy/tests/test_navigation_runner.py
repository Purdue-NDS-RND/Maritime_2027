"""Session completion waits for both trajectory acceptance and vehicle cleanup."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('navigation_runner', Path(__file__).resolve().parents[1]/'tools/navigation.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SessionTests(unittest.TestCase):
    def processes(self, **codes):
        return {name: Mock(poll=Mock(return_value=code), wait=Mock(return_value=0))
                for name, code in codes.items()}

    def test_judge_finishing_first_waits_for_hold_and_disarm(self):
        processes = self.processes(navigator=None, judge=0, bridge=None)
        self.assertEqual(runner.session_exit(processes, True), 0)
        processes['bridge'].wait.assert_called_once_with(timeout=25)
        processes['bridge'].wait.return_value = 1
        self.assertEqual(runner.session_exit(processes, True), 1)

    def test_bridge_finishing_first_waits_for_independent_judge(self):
        processes = self.processes(navigator=None, judge=None, bridge=0)
        self.assertEqual(runner.session_exit(processes, True), 0)
        processes['judge'].wait.assert_called_once_with(timeout=15)
        processes['judge'].wait.return_value = 1
        self.assertEqual(runner.session_exit(processes, True), 1)

    def test_unexpected_component_exit_fails_even_with_zero_code(self):
        self.assertEqual(runner.session_exit(self.processes(mapping=0, bridge=None), False), 1)
        self.assertEqual(runner.session_exit(self.processes(judge=1, bridge=None), True), 1)
        self.assertIsNone(runner.session_exit(self.processes(mapping=None, bridge=None), False))
