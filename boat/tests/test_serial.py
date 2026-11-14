"""Exercise the real MAVLink serial transport without physical hardware."""

import os
import pty
import unittest

from pymavlink import mavutil


class SerialTests(unittest.TestCase):
    def test_virtual_serial_heartbeat(self):
        master_fd, slave_fd = pty.openpty()
        try:
            link = mavutil.mavlink_connection(
                os.ttyname(slave_fd), baud=115200,
                source_system=245, source_component=191,
            )
            try:
                encoder = mavutil.mavlink.MAVLink(None, srcSystem=1, srcComponent=1)
                heartbeat = encoder.heartbeat_encode(11, 3, 0, 4, 3)
                os.write(master_fd, heartbeat.pack(encoder))
                received = link.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
                self.assertIsNotNone(received)
                self.assertEqual(received.get_srcSystem(), 1)
                self.assertEqual(received.type, 11)
                self.assertEqual(link.port.baudrate, 115200)
            finally:
                link.close()
        finally:
            os.close(slave_fd)
            os.close(master_fd)


if __name__ == "__main__":
    unittest.main()
