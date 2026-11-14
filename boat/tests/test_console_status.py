"""Operator diagnostics distinguish transport, heartbeat and GPS readiness."""

import unittest
from unittest.mock import Mock

from boat_app.console_status import ConsoleStatus


class ConsoleStatusTests(unittest.TestCase):
    def setUp(self):
        self.logger = Mock()
        self.console = ConsoleStatus(self.logger)
        self.status = dict(state='ready', detail='connected; no mission authorized',
                           system_id=1, component_id=1, heartbeat_age_s=0.2,
                           available_modes={'HOLD': 4}, mode=4, armed=False,
                           gps_fix=0, position={'latitude': 0, 'longitude': 0}, position_age_s=0.2)

    def messages(self):
        return [str(call.args[0]) for call in self.logger.method_calls]

    def test_connected_without_gps_is_explicit_and_quiet_until_changed(self):
        self.console.update(self.status, 0)
        self.assertTrue(any('CONNECTED' in m and 'DISARMED' in m and 'HOLD' in m for m in self.messages()))
        self.assertTrue(any('no 3D fix' in m for m in self.messages()))
        count = len(self.messages())
        self.console.update(self.status, 100)
        self.assertEqual(len(self.messages()), count)
        self.status['gps_fix'] = 3
        self.console.update(self.status, 101)
        self.assertIn('3D fix or better', self.messages()[-1])
        self.status['position_age_s'] = 4
        self.console.update(self.status, 102)
        self.assertIn('missing or stale', self.messages()[-1])

    def test_loss_reconnection_and_armed_change_are_reported(self):
        self.console.update(self.status, 0)
        self.status['heartbeat_age_s'] = 4
        self.console.update(self.status, 4)
        self.assertIn('LOST', self.messages()[-1])
        self.status['heartbeat_age_s'] = 0.1
        self.status['armed'] = True
        self.logger.reset_mock()
        self.console.update(self.status, 5)
        self.assertTrue(any('CONNECTED' in m and '| ARMED' in m for m in self.messages()))

    def test_waiting_and_wrong_firmware_details_repeat_without_flooding(self):
        status = dict(system_id=None, detail='Unsupported heartbeat: MAV_TYPE_HEXAROTOR')
        self.console.update(status, 0)
        self.assertIn('HEXAROTOR', self.messages()[0])
        self.console.update(status, 1)
        self.assertEqual(len(self.messages()), 1)
        self.console.update(status, 15)
        self.assertEqual(len(self.messages()), 2)


if __name__ == '__main__':
    unittest.main()
