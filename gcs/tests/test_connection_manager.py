"""Editable profiles, live transport replacement and cross-target ownership."""
import asyncio
from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
import pty
import socket
import tempfile
import threading
import time
import tty
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from gcs.app import main
from gcs.app.connections import Connections
from gcs.app.connection_manager import ConnectionManager, parse, serial_devices
from gcs.app.telemetry import TelemetryConfig
from test_telemetry import heartbeat, position, wait_for

SAFE = {'position_age_s': 0, 'heartbeat_age_s': 0, 'armed': False, 'mode': 4,
        'speed_m_s': 0, 'state': 'ready', 'operations': [], 'system_id': 1, 'component_id': 1}


class Profiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'connections.json'
        self.manager = ConnectionManager(self.path)
        self.field = Connections('http://jetson:8091', TelemetryConfig('/dev/gcs-radio', 115200, 7, 1)).snapshot()

    def apply(self, value=None, **kwargs):
        return self.manager.apply('Field', value or self.field, self.manager.revision,
                                  kwargs.get('ack', False), kwargs.get('status', lambda old: SAFE), kwargs.get('invalidate', lambda: None))

    def test_save_restart_selected_and_active_are_separate(self):
        original = self.manager.active
        self.manager.save('Field', self.field, 0)
        restarted = ConnectionManager(self.path, Connections('http://ignored-env'))
        self.assertEqual(restarted.active, original)
        self.assertEqual(restarted.selected, 'Field')
        self.assertEqual(restarted.profiles['Field'], self.field)
        self.apply()
        restarted = ConnectionManager(self.path)
        self.assertEqual(restarted.active.snapshot(), self.field)
        self.assertEqual(restarted.active_profile, 'Field')
        self.assertEqual(set(json.loads(self.path.read_text())), {'version', 'revision', 'profiles', 'active', 'active_profile', 'selected_profile'})

    def test_environment_seeds_field_only_on_first_initialization(self):
        other = self.path.with_name('field.json')
        env = Connections('http://jetson')
        seeded = ConnectionManager(other, env)
        self.assertEqual(seeded.active, env)
        self.assertEqual(seeded.profiles['Field'], env.snapshot())
        self.assertEqual(seeded.profiles['Simulator'], Connections().snapshot())
        self.assertIsNone(self.manager.profiles['Field'])

    def test_corrupt_invalid_and_unreadable_files_require_explicit_recovery(self):
        for content in ('{', 'null', '[]', '{"version":2}', json.dumps({**self.manager.document(), 'active': {'boat_url': 'bad'}})):
            self.path.write_text(content)
            damaged = ConnectionManager(self.path)
            self.assertIsNone(damaged.active)
            self.assertIn('recovery', damaged.error)
            self.assertEqual(self.path.read_text(), content)
            damaged.apply('Simulator', damaged.snapshot()['simulator_defaults'], damaged.revision, False, None, lambda: None)
            self.assertEqual(damaged.active, Connections())
        with patch.object(Path, 'read_text', side_effect=PermissionError('no access')):
            self.assertIsNone(ConnectionManager(self.path).active)

    def test_failed_writes_leave_memory_file_and_authority_unchanged(self):
        previous = self.path.read_text()
        invalidated = []
        for action in (lambda: self.manager.save('Field', self.field, 0), lambda: self.apply(invalidate=lambda: invalidated.append(True))):
            with patch('gcs.app.connection_manager.os.replace', side_effect=PermissionError('read only')):
                with self.assertRaises(OSError):
                    action()
            self.assertEqual(self.manager.revision, 0)
            self.assertEqual(self.manager.active, Connections())
            self.assertEqual(self.path.read_text(), previous)
            self.assertFalse(invalidated)
            self.assertFalse(list(self.path.parent.glob('.connections-*')))

    def test_concurrent_edit_has_one_winner_and_never_overwrites_it(self):
        barrier = threading.Barrier(2)
        out = []
        def save(name):
            barrier.wait()
            try:
                out.append(self.manager.save(name, self.field, 0)['revision'])
            except HTTPException as e:
                out.append(e.status_code)
        threads = [threading.Thread(target=save, args=(name,)) for name in ('Field', 'Simulator')]
        for t in threads: t.start()
        for t in threads: t.join(3)
        self.assertCountEqual(out, [1, 409])
        self.assertEqual(ConnectionManager(self.path).revision, 1)

    def test_strict_validation(self):
        for patch_value in ({'boat_url': ''}, {'telemetry': {}}, {'telemetry': {**self.field['telemetry'], 'baud': True}},
                            {'telemetry': {**self.field['telemetry'], 'connection': '/dev/../tmp/file'}},
                            {'telemetry': {**self.field['telemetry'], 'connection': 'udpin:127.0.0.1:99999'}},
                            {'telemetry': {**self.field['telemetry'], 'system_id': 0}}):
            with self.assertRaises((ValueError, TypeError)):
                parse({**self.field, **patch_value})

    def test_safe_switch_and_stale_unknown_acknowledgment(self):
        for changes in ({'armed': True}, {'speed_m_s': .21}, {'mode': 10}, {'state': 'executing'}, {'speed_m_s': None}, {'mode': None}):
            with self.assertRaises(HTTPException):
                self.apply(status=lambda old: {**SAFE, **changes}, ack=True)
        with self.assertRaises(HTTPException):
            self.apply(status=lambda old: {**SAFE, 'position_age_s': 4})
        self.apply(status=lambda old: {**SAFE, 'heartbeat_age_s': 4}, ack=True)
        self.assertEqual(self.manager.generation, 1)

    def test_command_racing_status_check_prevents_apply_without_holding_lock(self):
        entered, release = threading.Event(), threading.Event()
        out = []
        def get_status(old):
            entered.set(); release.wait(3); return SAFE
        def apply():
            try: self.apply(status=get_status)
            except HTTPException as e: out.append(e.status_code)
        thread = threading.Thread(target=apply);thread.start()
        self.assertTrue(entered.wait(2))
        with self.manager.command(0):
            self.assertEqual(self.manager.snapshot()['commands_in_flight'], 1)
        release.set();thread.join(3)
        self.assertEqual(out, [409])
        self.assertEqual(self.manager.generation, 0)

    def test_inflight_pending_and_unknown_each_block_apply(self):
        with self.manager.command(0), self.assertRaises(HTTPException):
            self.apply()
        for state in ('pending', 'running', 'unknown'):
            self.manager.track('op', {'state': state})
            with self.assertRaises(HTTPException): self.apply()
        self.manager.track('op', {'state': 'failed'})
        self.apply()

    def test_shutdown_failure_never_starts_another_reader(self):
        class Reader:
            def __init__(self, config): pass
            def start(self): pass
            def stop(self): raise RuntimeError('stuck')
            def snapshot(self): return {'stale': True}
        self.manager.reader_factory = Reader
        self.manager.start()
        self.apply()
        self.assertTrue(self.manager.reader_failed)
        self.assertIn('Restart GCS', self.manager.error)
        with patch.object(self.manager, 'reader_factory') as factory:
            self.apply(Connections('http://jetson:8091', TelemetryConfig('/dev/missing')).snapshot())
            factory.assert_not_called()

    def test_reconnect_hides_cached_position_before_old_reader_shutdown_finishes(self):
        entered, release = threading.Event(), threading.Event()
        class Reader:
            def __init__(self, config): pass
            def start(self): pass
            def stop(self): entered.set(); release.wait(3)
            def snapshot(self): return {'position': {'latitude': 1}, 'stale': False}
        self.manager.reader_factory = Reader
        self.manager.start()
        thread = threading.Thread(target=self.apply)
        thread.start();self.assertTrue(entered.wait(2))
        self.assertIsNone(self.manager.telemetry_snapshot()['position'])
        self.assertEqual(self.manager.snapshot()['effective'], self.field)
        release.set();thread.join(3)
        self.manager.stop()

    def test_serial_inventory_retains_configured_missing_path(self):
        missing = '/dev/nonexistent-maritime-radio'
        self.assertIn({'device': missing, 'present': False, 'accessible': False}, serial_devices(missing))


class ConnectionAPI(unittest.TestCase):
    def setUp(self):
        self.manager = ConnectionManager()
        self.patches = [patch.object(main, 'manager', self.manager)]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        main.sessions.clear();main.operations.clear()
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.calls = []
        self.status = deepcopy(SAFE)
        def transport(request, **kwargs):
            self.calls.append((request.full_url, request.method))
            return BytesIO(json.dumps(self.status).encode())
        self.transport = patch.object(main, 'urlopen', side_effect=transport)
        self.transport.start();self.addCleanup(self.transport.stop)
        self.field = Connections('http://jetson').snapshot()

    def apply(self, value=None, **extra):
        return self.client.post('/api/connections/apply', json={'revision': self.manager.revision, 'profile': 'Field', 'settings': value or self.field, **extra})

    def test_test_and_apply_only_send_status_gets_and_test_does_not_change_active(self):
        original = self.manager.active
        out = self.client.post('/api/connections/test', json={'boat_url': 'http://candidate', 'revision': self.manager.revision}).json()
        self.assertTrue(out['reachable'])
        self.assertEqual(self.manager.active, original)
        self.assertEqual(self.manager.revision, 0)
        self.assertEqual(self.apply().status_code, 200)
        self.assertEqual(self.calls, [('http://candidate/status', 'GET'), ('http://127.0.0.1:8091/status', 'GET')])

    def test_all_tabs_sessions_and_old_results_expire_but_telemetry_edit_retains_them(self):
        keys = [self.client.post('/api/session').json()['session_id'] for _ in range(2)]
        old = [main.sessions[k] for k in keys]
        radio = Connections(telemetry=TelemetryConfig('/dev/missing')).snapshot()
        self.assertEqual(self.apply(radio).status_code, 200)
        self.assertEqual(set(main.sessions), set(keys))
        self.assertFalse(self.calls)
        self.assertEqual(self.apply().status_code, 200)
        for key, workspace in zip(keys, old):
            self.assertTrue(workspace.cancelled.is_set())
            self.assertEqual(self.client.get('/api/workspace', headers={'X-Planner-Session': key}).status_code, 409)
        self.assertEqual(self.client.post('/api/start', headers={'X-Connection-Generation': '0'}).status_code, 409)
        self.assertEqual(self.client.get('/api/operations/old').status_code, 404)
        self.assertEqual(len(self.calls), 1)

    def test_failed_probe_and_independent_telemetry_failure(self):
        with patch.object(main, 'urlopen', side_effect=OSError('offline')):
            self.assertFalse(self.client.post('/api/connections/test', json={'boat_url': 'http://candidate', 'revision': self.manager.revision}).json()['reachable'])
            self.assertEqual(self.apply().status_code, 409)
            self.assertEqual(self.apply(acknowledge_unknown=True).status_code, 200)
        self.assertEqual(self.client.get('/api/status').status_code, 200)
        self.assertTrue(self.manager.telemetry_snapshot()['stale'])

    def test_operation_id_reuse_never_queries_new_boat_for_old_operation(self):
        workspace = main.SessionWorkspace()
        main.operations['same-id'] = (workspace, 'start', {}, 0, (self.manager.active, 0))
        self.assertEqual(self.apply().status_code, 200)
        self.assertEqual(self.client.get('/api/operations/same-id').status_code, 404)
        # Even if a stale handler retains/reinserts an old operation, reject it.
        main.operations['same-id'] = (workspace, 'start', {}, 0, (Connections(), 0))
        self.assertEqual(self.client.get('/api/operations/same-id').status_code, 409)
        self.assertEqual(self.calls, [('http://127.0.0.1:8091/status', 'GET')])

    def test_unknown_resolution_requires_safe_status_operation_summary_and_ack(self):
        self.manager.track('unknown-receipt', {'state': 'unknown'})
        self.assertEqual(self.apply().status_code, 409)
        self.client.post('/api/connections/reconcile', json={'revision': 0})
        self.assertTrue(self.manager.pending)
        for changes in ({'operations': None}, {'operations': [{'state': 'running'}]}, {'armed': True}, {'position_age_s': 4}):
            self.status = {**SAFE, **changes}
            self.assertEqual(self.client.post('/api/connections/reconcile', json={'revision': 0, 'acknowledge_unknown': True}).status_code, 409)
        self.status = deepcopy(SAFE)
        self.assertEqual(self.client.post('/api/connections/reconcile', json={'revision': 0, 'acknowledge_unknown': True}).status_code, 200)
        self.assertFalse(self.manager.pending)
        self.assertEqual(self.apply().status_code, 200)
        self.assertTrue(all(method == 'GET' for _, method in self.calls))

    def test_boat_journal_recovers_unknown_receipt_after_gcs_restart(self):
        self.status['operations'] = [{'operation_id': 'lost-before-restart', 'state': 'unknown', 'command': 'start'}]
        self.assertEqual(self.client.get('/api/status').status_code, 200)
        self.assertIn('lost-before-restart', self.manager.pending)
        self.assertEqual(self.apply().status_code, 409)
        with patch.object(main, 'urlopen', side_effect=lambda req, **kw: BytesIO(json.dumps(self.status if req.full_url.endswith('/status') else self.status['operations'][0]).encode())):
            resolved = self.client.post('/api/connections/reconcile', json={'revision': 0, 'acknowledge_unknown': True})
        self.assertEqual(resolved.status_code, 200)
        self.assertFalse(self.manager.pending)
        self.assertEqual(self.apply().status_code, 200)

    def test_http_command_inflight_blocks_apply_and_stop_does_not_wait_for_planner_lock(self):
        key = self.client.post('/api/session').json()['session_id']
        workspace = main.sessions[key]
        entered, release = threading.Event(), threading.Event()
        out = []
        def transport(request, **kwargs):
            if request.method == 'POST':
                entered.set();release.wait(3)
                return BytesIO(b'{"operation_id":"stop-id","state":"pending","command":"stop"}')
            return BytesIO(json.dumps(SAFE).encode())
        with patch.object(main, 'urlopen', side_effect=transport):
            with workspace.lock:
                thread = threading.Thread(target=lambda: out.append(self.client.post('/api/stop', headers={'X-Planner-Session': key})))
                thread.start()
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.apply().status_code, 409)
                release.set()
            thread.join(3)
        self.assertEqual(out[0].status_code, 200)
        self.assertIn('stop-id', self.manager.pending)
        self.assertEqual(self.apply().status_code, 409)

    def test_late_operation_cannot_clear_new_boat_operation_with_reused_id(self):
        old_target = self.manager.active
        self.assertEqual(self.apply().status_code, 200)
        new_workspace = main.SessionWorkspace()
        entry = (new_workspace, 'disarm', None, 0, (self.manager.active, self.manager.generation))
        main.operations['same-id'] = entry
        self.manager.track('same-id', {'state': 'pending'})
        token = main.request_target.set((old_target, 0))
        try:
            with self.assertRaises(HTTPException):
                main.reconcile('same-id', {'state': 'succeeded'})
        finally:
            main.request_target.reset(token)
        self.assertIs(main.operations['same-id'], entry)
        self.assertIn('same-id', self.manager.pending)
        self.assertFalse(hasattr(new_workspace, 'disarm_epoch'))

    def test_http_server_error_on_command_retains_unknown_outcome(self):
        from urllib.error import HTTPError
        with patch.object(main, 'urlopen', side_effect=HTTPError('http://boat/stop', 500, 'lost result', {}, BytesIO(b'broken'))):
            self.assertEqual(self.client.post('/api/stop').status_code, 500)
        self.assertTrue(self.manager.pending)
        self.assertEqual(self.apply().status_code, 409)

    def test_late_read_response_cannot_restore_status_after_target_switch(self):
        entered, release = threading.Event(), threading.Event()
        result = []
        original = main.urlopen
        def delayed(request, **kwargs):
            if threading.current_thread().name == 'old-request':
                entered.set();release.wait(3)
            return original(request, **kwargs)
        def old_request():
            try: result.append(main.boat_at(Connections(), 0, '/status'))
            except HTTPException as e: result.append(e.status_code)
        with patch.object(main, 'urlopen', side_effect=delayed):
            thread = threading.Thread(target=old_request, name='old-request');thread.start()
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.apply().status_code, 200)
            release.set();thread.join(3)
        self.assertEqual(result, [409])
        self.assertIsNone(self.manager.api_status)

    def test_identity_mismatch_blocks_upload_but_missing_passive_feed_does_not(self):
        # Exercise the common Upload/Start guard independently of route geometry.
        telemetry = {'stale': False, 'system_id': 2, 'component_id': 1}
        self.status['position'] = {'latitude': 0, 'longitude': 0}
        with patch.object(self.manager, 'telemetry_snapshot', return_value=telemetry):
            with self.assertRaisesRegex(HTTPException, '409') as error:
                main.validate_actual_start({})
            self.assertIn('identity mismatch', error.exception.detail)
        self.assertFalse(self.manager.mismatch(self.status, {'stale': True}))
        self.manager.update_status(SAFE, 0)
        self.manager.status_at -= 4
        self.assertFalse(self.manager.snapshot()['identity_mismatch'])


class LiveReplacement(unittest.TestCase):
    def test_udp_to_serial_existing_stream_follows_reader_and_replug_is_passive(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        manager = ConnectionManager(initial=Connections(telemetry=TelemetryConfig(f'udpin:127.0.0.1:{port}')))
        manager.start()
        self.addCleanup(manager.stop)
        old = manager.reader
        old.ingest(heartbeat());old.ingest(position())
        async def check():
            with patch.object(main, 'manager', manager):
                stream = main.telemetry_events()
                first = json.loads((await anext(stream))[6:])
                self.assertFalse(first['stale'])
                device_dir = tempfile.TemporaryDirectory(dir='/dev/shm')
                self.addCleanup(device_dir.cleanup)
                device = Path(device_dir.name)/'radio'
                master, slave = pty.openpty()
                tty.setraw(slave)
                device.symlink_to(os.ttyname(slave))
                config = Connections(telemetry=TelemetryConfig(str(device))).snapshot()
                manager.apply('Field', config, 0, False, None, lambda: self.fail('Telemetry change invalidated planning'))
                self.assertFalse(old.thread.is_alive())
                cleared = json.loads((await anext(stream))[6:])
                self.assertIsNone(cleared['position'])
                def feed():
                    os.write(master, heartbeat().get_msgbuf() + position(2000).get_msgbuf())
                    return not manager.telemetry_snapshot()['stale']
                wait_for(feed)
                live = json.loads((await anext(stream))[6:])
                self.assertEqual(live['time_boot_ms'], 2000)
                self.assertNotEqual(first['session_id'], live['session_id'])
                os.set_blocking(master, False)
                with self.assertRaises(BlockingIOError): os.read(master, 4096)
                # Unplug: close the physical side, wait for reader error/cache reset.
                os.close(master);os.close(slave)
                wait_for(lambda: manager.telemetry_snapshot()['error'] is not None)
                self.assertIsNone(manager.telemetry_snapshot()['position'])
                master, slave = pty.openpty()
                tty.setraw(slave)
                self.addCleanup(os.close, master);self.addCleanup(os.close, slave)
                replacement = device.with_name('replacement')
                replacement.symlink_to(os.ttyname(slave))
                replacement.replace(device)
                wait_for(feed, timeout=4)
                self.assertFalse(manager.telemetry_snapshot()['stale'])
                os.set_blocking(master, False)
                with self.assertRaises(BlockingIOError): os.read(master, 4096)
                self.assertEqual(manager.generation, 0)
                await stream.aclose()
        asyncio.run(check())

    def test_occupied_port_error_clears_old_position_and_never_falls_back(self):
        manager = ConnectionManager(initial=Connections(telemetry=TelemetryConfig('/dev/does-not-exist-maritime')))
        manager.start();self.addCleanup(manager.stop)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as occupied:
            occupied.bind(('127.0.0.1', 0));port = occupied.getsockname()[1]
            config = Connections(telemetry=TelemetryConfig(f'udpin:127.0.0.1:{port}')).snapshot()
            manager.apply('Simulator', config, 0, False, None, lambda: None)
            wait_for(lambda: manager.telemetry_snapshot()['error'] is not None)
            self.assertIsNone(manager.telemetry_snapshot()['position'])
            self.assertEqual(manager.active.telemetry.connection, f'udpin:127.0.0.1:{port}')
        wait_for(lambda: manager.telemetry_snapshot()['error'] is None)
        self.assertTrue(manager.telemetry_snapshot()['stale'])

class Lifecycle(unittest.TestCase):
    def test_restart_profiles_survive_and_sessions_are_empty_with_saved_over_env_precedence(self):
        with tempfile.TemporaryDirectory() as data, patch.dict(os.environ, {'GCS_DATA': data, 'GCS_MAVLINK_CONNECTION': '/dev/maritime-missing'}):
            with TestClient(main.app) as client:
                original = client.get('/api/connections').json()
                session = client.post('/api/session').json()
                workspace = main.sessions[session['session_id']]
                workspace.state['return_target'] = {'latitude': 1, 'longitude': 2}
                config = Connections('http://saved-jetson', TelemetryConfig('/dev/maritime-missing')).snapshot()
                with patch.object(main, 'urlopen', return_value=BytesIO(json.dumps(SAFE).encode())):
                    applied = client.post('/api/connections/apply', json={'revision': original['revision'], 'profile': 'Field', 'settings': config})
                self.assertEqual(applied.status_code, 200)
                client.post('/api/session')
            # Invalid environment does not override a saved active configuration.
            with patch.dict(os.environ, {'GCS_BOAT_URL': 'bad', 'GCS_MAVLINK_BAUD': 'bad'}), TestClient(main.app) as client:
                self.assertEqual(client.get('/api/connections').json()['effective'], config)
                fresh_session = client.post('/api/session').json()['workspace']
                self.assertIsNone(fresh_session['map'])
                self.assertIsNone(fresh_session['approval'])
                self.assertIsNone(fresh_session['return_target'])
                self.assertFalse(fresh_session['run_draft']['steps'])
                self.assertEqual(len(main.sessions), 1)

    def test_invalid_saved_file_starts_no_reader_and_api_test_can_recover_without_commands(self):
        with tempfile.TemporaryDirectory() as data, patch.dict(os.environ, {'GCS_DATA': data}):
            path = Path(data)/'connections.json'
            path.write_text('broken')
            with TestClient(main.app) as client:
                self.assertIsNone(main.manager.reader)
                self.assertEqual(client.get('/api/status').status_code, 503)
                value = client.get('/api/connections').json()
                with patch.object(main, 'urlopen', return_value=BytesIO(json.dumps(SAFE).encode())) as transport:
                    self.assertTrue(client.post('/api/connections/test', json={'revision': 0, 'boat_url': 'http://test'}).json()['reachable'])
                    applied = client.post('/api/connections/apply', json={'revision': 0, 'profile': 'Simulator', 'settings': value['simulator_defaults']})
                    self.assertEqual(applied.status_code, 200)
                    self.assertEqual(transport.call_count, 1)
                self.assertIsNotNone(main.manager.reader)
