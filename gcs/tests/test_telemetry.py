"""Telemetry isolation, timing and real MAVLink transport tests."""
import asyncio
import json
import os
import pty
import socket
import threading
import time
import unittest
from unittest.mock import patch

from pymavlink import mavutil
from gcs.app.telemetry import Telemetry, TelemetryConfig, open_connection


def heartbeat(system=1, component=1):
    message = mavutil.mavlink.MAVLink_heartbeat_message(
        mavutil.mavlink.MAV_TYPE_SURFACE_BOAT,
        mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA, 128, 10, 4, 3)
    return source(message, system, component)


def position(boot=1000, latitude=515661510, heading=9000, vx=100):
    return source(mavutil.mavlink.MAVLink_global_position_int_message(
        boot, latitude, -40343450, 0, 0, vx, 100, 0, heading))


def source(message, system=1, component=1):
    # Pack/decode to exercise source metadata exactly as a received frame has it.
    encoder = mavutil.mavlink.MAVLink(None, srcSystem=system, srcComponent=component)
    return mavutil.mavlink.MAVLink(None).parse_char(message.pack(encoder))


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError('timed out waiting for telemetry')


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.now = 10
        self.reader = Telemetry(TelemetryConfig(), clock=lambda: self.now)

    def test_filters_source_and_requires_surface_boat_heartbeat(self):
        self.reader.ingest(position())
        self.reader.ingest(heartbeat(2))
        self.reader.ingest(heartbeat(component=2))
        self.assertIsNone(self.reader.snapshot()['position'])
        self.assertIsNone(self.reader.snapshot()['heartbeat_age_s'])
        self.reader.ingest(heartbeat())
        self.reader.ingest(position())
        value = self.reader.snapshot()
        self.assertFalse(value['stale'])
        self.assertEqual(value['position'], {'latitude': 51.566151, 'longitude': -4.034345})
        self.assertEqual(value['heading_deg'], 90)
        self.assertAlmostEqual(value['speed_m_s'], 2**0.5)
        self.assertTrue(value['armed'])
        self.reader.ingest(source(position(2000), 2))
        self.assertEqual(self.reader.snapshot()['time_boot_ms'], 1000)

    def test_position_age_advances_without_data_and_recovery_clears_old_state(self):
        self.reader.ingest(heartbeat())
        self.reader.ingest(position())
        first_session = self.reader.snapshot()['session_id']
        self.now += 4
        value = self.reader.snapshot()
        self.assertTrue(value['stale'])
        self.assertEqual(value['position_age_s'], 4)
        self.assertIsNotNone(value['position'])
        self.reader.ingest(heartbeat())
        value = self.reader.snapshot()
        self.assertNotEqual(value['session_id'], first_session)
        self.assertIsNone(value['position'])
        self.reader.ingest(position(100))
        self.assertFalse(self.reader.snapshot()['stale'])

    def test_reordering_duplicate_clock_wrap_and_reboot(self):
        self.reader.ingest(heartbeat())
        self.reader.ingest(position(2000))
        self.reader.ingest(position(1000, latitude=0))
        self.reader.ingest(position(2000, latitude=0))
        self.assertEqual(self.reader.snapshot()['position']['latitude'], 51.566151)
        # Keep heartbeats while the rebooted source clock is initially rejected.
        session = self.reader.snapshot()['session_id']
        for _ in range(4):
            self.now += 1
            self.reader.ingest(heartbeat())
        self.reader.ingest(position(100))
        self.assertNotEqual(self.reader.snapshot()['session_id'], session)
        self.assertEqual(self.reader.snapshot()['time_boot_ms'], 100)
        self.reader = Telemetry(TelemetryConfig())
        self.reader.ingest(heartbeat())
        self.reader.ingest(position(2**32 - 100))
        self.reader.ingest(position(50))
        self.assertEqual(self.reader.snapshot()['time_boot_ms'], 50)

    def test_invalid_fields_and_independent_gps_age(self):
        self.reader.ingest(heartbeat())
        self.reader.ingest(position(latitude=900000001))
        self.assertIsNone(self.reader.snapshot()['position'])
        self.reader.ingest(position(heading=65535, vx=32767))
        value = self.reader.snapshot()
        self.assertIsNone(value['heading_deg'])
        self.assertIsNone(value['speed_m_s'])
        self.assertIsNotNone(value['position'])
        self.reader.ingest(source(mavutil.mavlink.MAVLink_gps_raw_int_message(
            1000000, 3, 0, 0, 0, 100, 100, 0, 0, 12)))
        self.now += 2
        self.reader.ingest(heartbeat())
        value = self.reader.snapshot()
        self.assertEqual(value['gps_age_s'], 2)
        self.assertEqual(value['heartbeat_age_s'], 0)
        self.assertEqual(value['gps_fix'], 3)

    def test_configuration(self):
        with patch.dict(os.environ, {'GCS_MAVLINK_CONNECTION': '/dev/ttyUSB0',
                                    'GCS_MAVLINK_BAUD': '115200',
                                    'GCS_MAVLINK_SYSTEM_ID': '7',
                                    'GCS_MAVLINK_COMPONENT_ID': '2'}):
            config = TelemetryConfig.from_env()
        self.assertEqual((config.connection, config.baud, config.system_id, config.component_id),
                         ('/dev/ttyUSB0', 115200, 7, 2))
        for kwargs in ({'baud': 0}, {'system_id': 0}, {'component_id': 256},
                       {'connection': 'tcp:localhost:5760'}):
            with self.assertRaises(ValueError):
                TelemetryConfig(**kwargs)

    def test_real_udp_receives_without_transmitting_and_stops(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        reader = Telemetry(TelemetryConfig(connection=f'udpin:127.0.0.1:{port}'))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.bind(('127.0.0.1', 0))
            reader.start()
            try:
                def send():
                    for message in (heartbeat(), position()):
                        sender.sendto(message.get_msgbuf(), ('127.0.0.1', port))
                    return not reader.snapshot()['stale']
                wait_for(send)
                sender.settimeout(0.1)
                with self.assertRaises(socket.timeout):
                    sender.recvfrom(4096)
            finally:
                reader.stop()
            self.assertFalse(reader.thread.is_alive())

    def test_real_serial_pty_with_configurable_baud(self):
        master, slave = pty.openpty()
        reader = Telemetry(TelemetryConfig(connection=os.ttyname(slave), baud=115200))
        reader.start()
        try:
            def send():
                os.write(master, heartbeat().get_msgbuf() + position().get_msgbuf())
                return not reader.snapshot()['stale']
            wait_for(send)
            self.assertEqual(reader.snapshot()['heading_deg'], 90)
        finally:
            reader.stop()
            os.close(master)
            os.close(slave)

    def test_occupied_udp_port_is_not_shared(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as existing:
            existing.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            existing.bind(('127.0.0.1', 0))
            connection = f'udpin:127.0.0.1:{existing.getsockname()[1]}'
            with self.assertRaises(OSError):
                open_connection(connection)

    def test_transport_error_retries_and_closes(self):
        class Link:
            closed = False
            def recv_match(self, **kwargs):
                time.sleep(0.01)
                return None
            def close(self):
                self.closed = True
        link = Link()
        from unittest.mock import Mock
        connector = Mock(side_effect=[OSError('radio unplugged'), link])
        reader = Telemetry(TelemetryConfig(baud=115200), connect=connector)
        reader.start()
        try:
            wait_for(lambda: reader.snapshot()['error'] == 'radio unplugged')
            wait_for(lambda: connector.call_count == 2 and reader.snapshot()['error'] is None)
            self.assertTrue(reader.snapshot()['stale'])
            self.assertEqual(connector.call_args.kwargs['baud'], 115200)
        finally:
            reader.stop()
        self.assertTrue(link.closed)

    def test_stream_ages_latest_snapshot_without_queued_history(self):
        from gcs.app.main import telemetry_events
        async def check():
            stream = telemetry_events(self.reader)
            first = json.loads((await anext(stream))[6:])
            self.assertTrue(first['stale'])
            self.reader.ingest(heartbeat())
            self.reader.ingest(position())
            self.reader.ingest(position(2000))
            value = json.loads((await anext(stream))[6:])
            self.assertEqual(value['time_boot_ms'], 2000)
            self.now += 4
            value = json.loads((await anext(stream))[6:])
            self.assertEqual(value['position_age_s'], 4)
            self.assertTrue(value['stale'])
            await stream.aclose()
        asyncio.run(check())

    def test_api_lifespan_telemetry_does_not_call_boat(self):
        from fastapi.testclient import TestClient
        from gcs.app.main import app
        with patch('gcs.app.main.boat', side_effect=AssertionError('boat API called')):
            with TestClient(app) as client:
                value = client.get('/api/telemetry').json()
                self.assertEqual(value['source'], 'mavlink')
                self.assertTrue(value['stale'])
                self.assertEqual(value['position'], None)
                thread = app.state.telemetry.thread
            self.assertFalse(thread.is_alive())

    def test_live_http_stream_receives_movement_then_marks_loss(self):
        import httpx
        import uvicorn
        from gcs.app.main import app
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1', 0))
            udp_port = probe.getsockname()[1]
        with socket.socket() as http_socket, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            http_socket.bind(('127.0.0.1', 0))
            http_port = http_socket.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
            thread = threading.Thread(target=server.run, kwargs={'sockets': [http_socket]})
            with patch.dict(os.environ, {'GCS_MAVLINK_CONNECTION': f'udpin:127.0.0.1:{udp_port}'}), \
                    patch('gcs.app.main.boat', side_effect=AssertionError('boat API called')):
                thread.start()
                try:
                    wait_for(lambda: server.started)
                    sender.sendto(heartbeat().get_msgbuf() + position().get_msgbuf(), ('127.0.0.1', udp_port))
                    wait_for(lambda: not app.state.telemetry.snapshot()['stale'])
                    with httpx.Client(base_url=f'http://127.0.0.1:{http_port}', timeout=6) as client:
                        self.assertEqual(client.get('/api/telemetry').json()['heading_deg'], 90)
                        with client.stream('GET', '/api/telemetry/events') as response:
                            self.assertEqual(response.status_code, 200)
                            self.assertIn('text/event-stream', response.headers['content-type'])
                            lines = response.iter_lines()
                            def next_value():
                                return json.loads(next(line[6:] for line in lines if line.startswith('data: ')))
                            first = next_value()
                            sender.sendto(position(2000, latitude=515661520).get_msgbuf(), ('127.0.0.1', udp_port))
                            for _ in range(10):
                                moved = next_value()
                                if moved['time_boot_ms'] == 2000:
                                    break
                            self.assertNotEqual(first['position'], moved['position'])
                            for _ in range(25):
                                lost = next_value()
                                if lost['stale']:
                                    break
                            self.assertTrue(lost['stale'])
                            self.assertEqual(lost['position'], moved['position'])
                        # Disconnecting a stream does not close the shared reader.
                        self.assertEqual(client.get('/api/telemetry').status_code, 200)
                finally:
                    server.should_exit = True
                    thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
