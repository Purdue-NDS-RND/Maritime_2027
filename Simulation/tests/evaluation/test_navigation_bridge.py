"""Command gate semantics without a vehicle connection; run in evaluation image."""
import sys
from types import SimpleNamespace
import time
import unittest
sys.path.insert(0, '/navigation-scripts')
from geometry_msgs.msg import TwistStamped
from mavros_msgs.msg import PositionTarget
from navigation_bridge import Bridge


class BridgeTests(unittest.TestCase):
    def fixture(self):
        outputs = []
        latest = TwistStamped()
        latest.twist.linear.x = .5
        latest.twist.angular.z = .2
        node = SimpleNamespace(started=True, terminal=False, latest=latest,
            state=SimpleNamespace(connected=True, armed=True, mode='GUIDED'),
            state_time=time.monotonic(), received=time.monotonic(),
            publisher=SimpleNamespace(publish=outputs.append),
            get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: latest.header.stamp)))
        return node, outputs

    def test_active_and_stale(self):
        node, output = self.fixture()
        Bridge.tick(node)
        self.assertEqual(output[-1].velocity.x, .5)
        self.assertTrue(output[-1].type_mask & PositionTarget.IGNORE_YAW_RATE)
        node.received -= 1
        Bridge.tick(node)
        self.assertEqual(output[-1].velocity.x, 0)
        self.assertEqual(output[-1].yaw_rate, 0)
        self.assertFalse(output[-1].type_mask & PositionTarget.IGNORE_YAW_RATE)

    def test_all_state_gates_zero_commands(self):
        for attribute, value in [('connected', False), ('armed', False), ('mode', 'HOLD')]:
            node, output = self.fixture()
            setattr(node.state, attribute, value)
            Bridge.tick(node)
            self.assertEqual(output[-1].velocity.x, 0)
        for attribute, value in [('terminal', True), ('started', False), ('state_time', 0.)]:
            node, output = self.fixture()
            setattr(node, attribute, value)
            Bridge.tick(node)
            self.assertEqual(output[-1].velocity.x, 0)

    def test_invalid_command_clears_previous_command(self):
        node, _ = self.fixture()
        message = TwistStamped()
        message.header.frame_id = 'map'
        for value in [float('nan'), float('inf'), .9]:
            message.twist.linear.x = value
            Bridge.on_velocity(node, message)
            self.assertIsNone(node.latest)
            self.assertEqual(node.received, 0)
