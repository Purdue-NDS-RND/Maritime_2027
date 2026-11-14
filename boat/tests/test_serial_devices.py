"""USB discovery without opening or probing a physical serial device."""

import importlib.util
import os
from pathlib import Path
import pty
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    'serial_devices', Path(__file__).resolve().parents[1] / 'container/serial_devices.py')
serial_devices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serial_devices)


class SerialDeviceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'serial/by-id').mkdir(parents=True)

    def device(self, name):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        path = self.root / 'serial/by-id' / name
        path.symlink_to(os.ttyname(slave))
        return path

    def resolve(self, device='auto', group='auto'):
        return serial_devices.resolve({'services': {'boat': {
            'devices': [{'source': str(device), 'target': '/dev/boat-fcu'}],
            'group_add': [group],
        }}}, self.root)

    def test_one_controller_uses_stable_primary_alias_and_derived_group(self):
        path = self.device('usb-CubePilot_CubeOrange_123-if00')
        self.device('usb-CubePilot_CubeOrange_123-if02')
        (self.root / 'ttyACM0').symlink_to(path.resolve())
        selected, group = self.resolve()
        self.assertEqual(selected, str(path))
        self.assertEqual(group, str(path.stat().st_gid))
        self.assertEqual(len(serial_devices.discover(self.root)), 2)

    def test_controller_swap_is_detected_on_next_launch(self):
        cube = self.device('usb-CubePilot_CubeOrange_123-if00')
        self.assertEqual(self.resolve()[0], str(cube))
        cube.unlink()
        pixhawk = self.device('usb-Holybro_Pixhawk_456-if00')
        self.assertEqual(self.resolve()[0], str(pixhawk))

    def test_multiple_controllers_are_listed_instead_of_guessed(self):
        cube = self.device('usb-CubePilot_CubeOrange_123-if00')
        pixhawk = self.device('usb-Pixhawk_456-if00')
        with self.assertRaisesRegex(ValueError, 'Multiple flight controllers') as error:
            self.resolve()
        self.assertIn(str(cube), str(error.exception))
        self.assertIn(str(pixhawk), str(error.exception))

    def test_unknown_usb_and_secondary_interface_need_explicit_selection(self):
        path = self.device('usb-Generic_USB_UART_123')
        self.device('usb-CubePilot_456-if02')
        with self.assertRaisesRegex(ValueError, 'No recognized flight controller'):
            self.resolve()
        self.assertEqual(self.resolve(path, '123'), (str(path), '123'))

    def test_missing_or_non_device_paths_fail_before_launch(self):
        with self.assertRaisesRegex(ValueError, 'Cannot access flight controller'):
            self.resolve(self.root / 'missing')
        plain = self.root / 'file'
        plain.touch()
        with self.assertRaisesRegex(ValueError, 'not a character device'):
            self.resolve(plain)

    def test_simulation_does_not_inspect_usb(self):
        self.assertIsNone(serial_devices.resolve({'services': {'boat': {}}}, self.root))


if __name__ == '__main__':
    unittest.main()
