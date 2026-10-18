"""Command gate semantics without a vehicle connection; run in evaluation image."""
import sys
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, '/navigation-scripts')
from geometry_msgs.msg import TwistStamped
from mavros_msgs.msg import PositionTarget
from navigation_bridge import Bridge
import navigation_bridge


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
        self.assertFalse(output[-1].type_mask & PositionTarget.IGNORE_YAW_RATE)
        self.assertEqual(output[-1].coordinate_frame, PositionTarget.FRAME_BODY_NED)
        self.assertAlmostEqual(output[-1].yaw_rate, .2)
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
        message.header.frame_id = 'base_link'
        for value in [float('nan'), float('inf'), .9]:
            message.twist.linear.x = value
            Bridge.on_velocity(node, message)
            self.assertIsNone(node.latest)
            self.assertEqual(node.received, 0)

    def test_interrupted_arm_response_still_holds_and_disarms(self):
        self.check_interrupted_arm_cleanup(False)

    def test_lost_hold_response_still_disarms_and_restores_intervals(self):
        self.check_interrupted_arm_cleanup(True)

    def check_interrupted_arm_cleanup(self, lose_hold_response):
        state = SimpleNamespace(connected=True, armed=False, mode='HOLD')
        requests = []
        class Session:
            def __init__(self):
                self.state, self.ready = state, True
                self.mode, self.arm, self.interval = 'mode', 'arm', 'interval'
                self.started = False
            def until(self, predicate, timeout):
                pass
            def call(self, client, request):
                if client == 'interval':
                    requests.append((request.message_id, request.message_rate))
                    return SimpleNamespace(success=True)
                if client == 'mode':
                    requests.append(request.custom_mode)
                    state.mode = request.custom_mode
                    if lose_hold_response and request.custom_mode == 'HOLD':
                        raise RuntimeError('HOLD acknowledgement lost')
                    return SimpleNamespace(mode_sent=True)
                requests.append(request.value)
                state.armed = request.value
                if request.value:
                    raise KeyboardInterrupt  # FCU armed, but response was lost.
                return SimpleNamespace(success=True)
            def destroy_node(self):
                pass
        with patch.dict('os.environ', SIMULATION_NAVIGATION='1', ADAPTER_ENVIRONMENT='simulation'), \
                patch.object(navigation_bridge, 'Bridge', Session), \
                patch.object(navigation_bridge.rclpy, 'init'), \
                patch.object(navigation_bridge.rclpy, 'shutdown'), \
                patch.object(navigation_bridge.signal, 'signal'):
            if lose_hold_response:
                with self.assertRaisesRegex(RuntimeError, 'HOLD acknowledgement lost'):
                    navigation_bridge.main()
            else:
                navigation_bridge.main()
        self.assertEqual(requests, [(32, 20.), (31, 20.), (2, 20.), 'GUIDED', True, 'HOLD', False,
                                    (32, 0.), (31, 0.), (2, 0.)])
        self.assertFalse(state.armed)
