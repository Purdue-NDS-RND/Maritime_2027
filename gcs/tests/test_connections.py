"""Startup connection validation and actual HTTP routing without a vehicle."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from fastapi.testclient import TestClient
from gcs.app import main
from gcs.app.connections import Connections


class ConnectionTests(unittest.TestCase):
    def test_environment_and_invalid_origins(self):
        with patch.dict(os.environ, {'GCS_BOAT_URL': 'http://192.168.50.2:8091/',
                                     'GCS_MAVLINK_CONNECTION': '/dev/gcs-radio',
                                     'GCS_MAVLINK_BAUD': '115200'}):
            value = Connections.from_env()
        self.assertEqual(value.boat_url, 'http://192.168.50.2:8091')
        self.assertEqual(value.telemetry.connection, '/dev/gcs-radio')
        self.assertEqual(value.telemetry.baud, 115200)
        for url in ('', 'jetson:8091', 'ftp://jetson', 'http://', 'http://jetson:0',
                    'http://jetson:65536', 'http://jetson:bad', 'http://jetson/path',
                    'http://user:secret@jetson', 'http://jetson?x=1', 'http://jetson#x',
                    'http://jetson\n', 'http://jet son'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                Connections(boat_url=url)

    def test_configured_http_target_and_read_only_diagnostics(self):
        calls = []

        class Boat(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                calls.append((self.command, self.path))
                body = json.dumps({'state': 'ready', 'system_id': 1}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Boat)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        target = f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.object(main, 'CONNECTIONS', Connections(boat_url=target)):
                client = TestClient(main.app)
                value = client.get('/api/connections').json()
                self.assertEqual(value['boat_url'], target)
                self.assertEqual(calls, [])
                self.assertEqual(client.get('/api/status').json()['state'], 'ready')
                self.assertEqual(calls, [('GET', '/status')])
                self.assertEqual(client.put('/api/connections', json={'boat_url': 'http://other'}).status_code, 405)
                client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_command_body_and_unknown_outcome_are_preserved(self):
        with patch.object(main, 'CONNECTIONS', Connections(boat_url='http://jetson:8092')), \
                patch.object(main, 'urlopen') as transport:
            transport.return_value.__enter__.return_value.read.return_value = b'{"operation_id":"receipt"}'
            self.assertEqual(main.boat('/missions/new', 'PUT', {'mission': 'approved'}),
                             {'operation_id': 'receipt'})
            request = transport.call_args.args[0]
            self.assertEqual(request.full_url, 'http://jetson:8092/missions/new')
            self.assertEqual(request.method, 'PUT')
            self.assertEqual(json.loads(request.data), {'mission': 'approved'})
            transport.side_effect = ConnectionResetError('link lost')
            with self.assertRaises(main.HTTPException) as error:
                main.boat('/missions/new/start', 'POST')
            self.assertEqual(error.exception.status_code, 503)
            self.assertIn('outcome unknown', error.exception.detail)
            self.assertEqual(transport.call_count, 2)  # No automatic command retry.
