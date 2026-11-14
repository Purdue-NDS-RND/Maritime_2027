"""Field capture freshness, durable edits and real terminal/HTTP interaction."""
from copy import deepcopy
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import termios
import threading
import time
import unittest
from unittest.mock import patch

from gcs.app.imports import import_points
from gcs.scripts.record_buoys import PointFile, capture_position, output_lock


ROOT = Path(__file__).resolve().parents[2]
POSITION = {'latitude': 51.566151, 'longitude': -4.034301645758707}


def telemetry():
    return {'source': 'mavlink', 'stale': False, 'connection_state': 'live',
            'error': None, 'position': dict(POSITION), 'gps_fix': 3,
            'heartbeat_age_s': 0.1, 'position_age_s': 0.2, 'gps_age_s': 0.3,
            'system_id': 1, 'component_id': 1}


class RecorderTests(unittest.TestCase):
    def test_capture_rejects_stale_missing_and_invalid_gps(self):
        self.assertEqual(capture_position(telemetry()), POSITION)
        for field, value in [('stale', True), ('connection_state', 'error'),
                             ('source', 'other'), ('error', 'disconnected'),
                             ('gps_fix', 2), ('gps_fix', None), ('gps_fix', True),
                             ('gps_age_s', 4), ('gps_age_s', None),
                             ('position_age_s', float('nan')),
                             ('heartbeat_age_s', -1), ('position', None),
                             ('position', {'latitude': 86, 'longitude': 0}),
                             ('position', {'latitude': True, 'longitude': 0})]:
            with self.subTest(field=field, value=value):
                sample = telemetry()
                sample[field] = value
                with self.assertRaises(ValueError):
                    capture_position(sample)
        with self.assertRaises(ValueError):
            capture_position(telemetry(), elapsed_s=3)
        for fix in (4, 5, 6):
            sample = telemetry()
            sample['gps_fix'] = fix
            self.assertEqual(capture_position(sample), POSITION)

    def test_immediate_save_resume_and_session_only_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'map.json'
            output = PointFile(path)
            self.assertFalse(path.exists())
            output.append(POSITION, 'red')
            self.assertEqual(json.loads(path.read_text())['points'][0]['color'], 'red')
            resumed = PointFile(path)
            with self.assertRaises(ValueError):
                resumed.undo()
            resumed.append({**POSITION, 'longitude': -4.035}, 'green')
            imported = import_points(path.read_text())
            self.assertEqual([p['category'] for p in imported['buoys']], ['red', 'green'])
            resumed.undo()
            self.assertEqual(len(json.loads(path.read_text())['points']), 1)
            with self.assertRaises(ValueError):
                resumed.undo()

    def test_full_map_append_preserves_existing_points_and_metadata(self):
        fixture = json.loads((ROOT / 'gcs/examples/competition-gps-points.json').read_text())
        fixture['operator_note'] = 'preserve this'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'full.json'
            path.write_text(json.dumps(fixture))
            original = deepcopy(fixture)
            output = PointFile(path)
            output.append(POSITION, 'blue')
            saved = json.loads(path.read_text())
            self.assertEqual(saved['points'][:-1], original['points'])
            self.assertEqual(saved['operator_note'], original['operator_note'])
            imported = import_points(path.read_text())
            self.assertEqual(len(imported['buoys']), 30)
            output.undo()
            self.assertEqual(json.loads(path.read_text()), original)

    def test_list_format_id_collisions_and_invalid_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'map.json'
            path.write_text(json.dumps([{**POSITION, 'id': 'point_2'}]))
            output = PointFile(path)
            output.append(POSITION, 'red')
            self.assertIsInstance(json.loads(path.read_text()), list)
            self.assertEqual(len(import_points(path.read_text())['buoys']), 2)
            for content in ('broken', '{"schema_version": 3}', '{"points": [null]}',
                            '{"points": {}}'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    PointFile(path)
                self.assertEqual(path.read_text(), content)

    def test_atomic_failure_external_edit_and_second_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'map.json'
            output = PointFile(path)
            output.append(POSITION, 'red')
            original = path.read_bytes()
            with patch('gcs.scripts.record_buoys.os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    output.append(POSITION, 'green')
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(output.points), 1)
            self.assertEqual(list(Path(directory).glob('.map.json*')), [])
            path.write_text('{"points": []}')
            with self.assertRaisesRegex(ValueError, 'changed outside'):
                output.append(POSITION, 'green')
            self.assertEqual(path.read_text(), '{"points": []}')
            with output_lock(path):
                with self.assertRaisesRegex(ValueError, 'Another recorder'):
                    with output_lock(path):
                        self.fail('second writer acquired lock')

    def test_real_terminal_space_color_undo_and_http_failure(self):
        sample = telemetry()
        requests = []
        response_status = [200]

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(('GET', self.path))
                body = json.dumps(sample).encode()
                self.send_response(response_status[0])
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'field.json'
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            master, slave = pty.openpty()
            previous_terminal = termios.tcgetattr(slave)
            process = subprocess.Popen(
                [sys.executable, '-u', str(ROOT / 'gcs/scripts/record_buoys.py'),
                 '--output', str(path), '--gcs-url', f'http://127.0.0.1:{server.server_port}'],
                stdin=slave, stdout=slave, stderr=slave, cwd=ROOT)
            transcript = b''

            def expect(message):
                nonlocal transcript
                deadline = time.monotonic() + 5
                while message.encode() not in transcript:
                    if time.monotonic() > deadline:
                        self.fail(f'Terminal did not show {message!r}: {transcript!r}')
                    if select.select([master], [], [], 0.1)[0]:
                        try:
                            transcript += os.read(master, 65536)
                        except OSError as error:
                            if error.errno != errno.EIO:
                                raise
                            self.fail(f'Terminal exited: {transcript!r}')

            try:
                expect('Ready;')
                os.write(master, b' ')
                expect('Saved #1 red')
                os.write(master, b'g')
                expect('Selected color: green')
                # The helper intentionally ignores repeat Space within 0.75 s.
                time.sleep(0.8)
                os.write(master, b' ')
                expect('Saved #2 green')
                self.assertEqual(len(import_points(path.read_text())['buoys']), 2)
                os.write(master, b'u')
                expect('Undid last capture')
                before = path.read_bytes()
                sample['gps_fix'] = 2
                time.sleep(0.8)
                os.write(master, b' ')
                expect('Capture refused; no point saved:')
                self.assertEqual(path.read_bytes(), before)
                response_status[0] = 503
                time.sleep(0.8)
                os.write(master, b' ')
                expect('HTTP Error 503')
                self.assertEqual(path.read_bytes(), before)
                os.write(master, b'q')
                process.wait(timeout=3)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(termios.tcgetattr(slave), previous_terminal)
                self.assertEqual(requests, [('GET', '/api/telemetry')] * 4)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
                os.close(master)
                os.close(slave)
                server.shutdown()
                worker.join(timeout=3)
                server.server_close()


if __name__ == '__main__':
    unittest.main()
