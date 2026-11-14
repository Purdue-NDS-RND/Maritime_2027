"""Process-wide connection profiles and transport/command ownership.

The state lock protects only memory and atomic local persistence. Network waits,
reader shutdown and planner locks are deliberately outside it.
"""
from contextlib import contextmanager
from copy import deepcopy
import glob
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time

from fastapi import HTTPException
from serial.tools import list_ports

from .connections import Connections
from .telemetry import Telemetry, TelemetryConfig


def parse(value):
    if not isinstance(value, dict) or set(value) != {'boat_url', 'telemetry'}:
        raise ValueError('Provide a mission API origin and telemetry settings')
    radio = value['telemetry']
    if not isinstance(radio, dict) or set(radio) != {'connection', 'baud', 'system_id', 'component_id'}:
        raise ValueError('Provide connection, baud and expected vehicle/component IDs')
    if not isinstance(value['boat_url'], str) or not isinstance(radio['connection'], str):
        raise ValueError('Connection addresses must be text')
    if any(type(radio[k]) is not int for k in ('baud', 'system_id', 'component_id')):
        raise ValueError('Baud and vehicle/component IDs must be integers')
    return Connections(value['boat_url'], TelemetryConfig(**radio))


def fresh(value):
    return bool(value) and all(type(value.get(k)) in (int, float) and math.isfinite(value[k])
                               and 0 <= value[k] <= 3 for k in ('position_age_s', 'heartbeat_age_s'))


def safe_to_leave(value):
    speed = value.get('speed_m_s')
    return (value.get('armed') is False and type(value.get('mode')) is int and value['mode'] != 10
            and type(speed) in (int, float) and math.isfinite(speed) and 0 <= speed <= .2
            and value.get('state') not in ('executing', 'starting', 'uploading')
            and not any(op.get('state') in ('pending', 'running') for op in (value.get('operations') or [])))


class ConnectionManager:
    def __init__(self, path=None, initial=None, reader_factory=Telemetry):
        self.lock = threading.RLock()
        self.apply_lock = threading.Lock()
        self.path = Path(path) if path else None
        self.reader_factory = reader_factory
        self.reader = None
        self.reader_failed = False
        self.running = False
        self.revision = 0
        self.generation = 0  # Mission target only; telemetry edits preserve planning.
        self.inflight = 0
        self.command_serial = 0
        self.pending = {}
        self.resolved_unknown = set()
        self.error = None
        self.api_status = None
        self.status_at = None
        self.api_error = None
        initial = initial or Connections()
        self.active = initial
        nondefault = initial != Connections()
        self.profiles = {'Simulator': Connections().snapshot(), 'Field': initial.snapshot() if nondefault else None}
        self.selected = self.active_profile = 'Field' if nondefault else 'Simulator'
        if self.path:
            self.load()

    def load(self):
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                if type(data['version']) is not int or data['version'] != 1 or type(data['revision']) is not int or data['revision'] < 0:
                    raise ValueError('Unsupported connection file version or revision')
                if set(data['profiles']) != {'Simulator', 'Field'}:
                    raise ValueError('Expected Simulator and Field profiles')
                for name, value in data['profiles'].items():
                    if value is not None:
                        parse(value)
                if data['selected_profile'] not in self.profiles or data['active_profile'] not in self.profiles:
                    raise ValueError('Unknown profile')
                active = parse(data['active']) if data['active'] is not None else None
                self.profiles = data['profiles']
                self.selected, self.active_profile = data['selected_profile'], data['active_profile']
                self.revision, self.active = data['revision'], active
            else:
                self.persist(self.document())
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.active = None
            self.error = f'Connection settings need recovery: {error}. Select built-in Simulator defaults or correct a profile, then Apply explicitly.'

    def document(self):
        return {'version': 1, 'revision': self.revision, 'profiles': deepcopy(self.profiles),
                'selected_profile': self.selected, 'active_profile': self.active_profile,
                'active': self.active.snapshot() if self.active else None}

    def persist(self, data):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, prefix='.connections-', delete=False) as stream:
                temporary = stream.name
                json.dump(data, stream, allow_nan=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def snapshot(self):
        with self.lock:
            effective = self.active.snapshot() if self.active else None
            result = {**self.document(), **(effective or {}), 'effective': effective,
                      'generation': self.generation, 'error': self.error,
                      'simulator_defaults': Connections().snapshot(),
                      'commands_in_flight': self.inflight,
                      'unresolved': deepcopy(list(self.pending.values()))}
            api_status = deepcopy(self.api_status)
            if api_status and self.status_at is not None:
                for key in ('heartbeat_age_s', 'position_age_s'):
                    if type(api_status.get(key)) in (int, float):
                        api_status[key] += time.monotonic() - self.status_at
            result['api_error'] = self.api_error
            result['mission'] = api_status
            result['telemetry_status'] = self.telemetry_snapshot()
            result['identity_mismatch'] = self.mismatch(api_status, result['telemetry_status'])
            return result

    def telemetry_snapshot(self):
        with self.lock:
            reader = self.reader
        return reader.snapshot() if reader else {'position': None, 'stale': True, 'connection_state': 'error' if self.error else 'connecting', 'error': self.error}

    @staticmethod
    def mismatch(status, telemetry):
        return (fresh(status) and not telemetry.get('stale', True)
                and any(status.get(k) is not None and status[k] != telemetry.get(k) for k in ('system_id', 'component_id')))

    def update_status(self, status, generation):
        with self.lock:
            if generation == self.generation:
                self.api_status = deepcopy(status)
                self.status_at = time.monotonic()
                self.api_error = None
                # The boat journal also covers receipts lost before a GCS restart.
                for operation in status.get('operations', []) or []:
                    key = operation.get('operation_id')
                    if key and key not in self.resolved_unknown and operation.get('state') in ('pending', 'running', 'unknown'):
                        self.pending[key] = deepcopy(operation)

    def check_revision(self, revision):
        if type(revision) is not int or revision != self.revision:
            raise HTTPException(409, 'Connections changed in another tab. Reload saved profiles before saving or applying.')

    def save(self, name, value, revision):
        config = parse(value)
        with self.lock:
            self.check_revision(revision)
            if name not in self.profiles:
                raise ValueError('Select Simulator or Field')
            data = self.document()
            data['profiles'][name] = config.snapshot()
            data.update(selected_profile=name, revision=self.revision + 1)
            self.persist(data)
            self.profiles, self.selected, self.revision = data['profiles'], name, data['revision']
        return self.snapshot()

    def start(self):
        self.running = True
        self.replace_reader()

    def replace_reader(self, previous=None):
        with self.lock:
            old, self.reader = previous or self.reader, None
            config = self.active
        if self.reader_failed:
            raise RuntimeError('Previous reader did not stop; restart GCS')
        if old:
            try:
                old.stop()
            except RuntimeError:
                with self.lock:
                    self.reader_failed = True
                raise
        if config and self.running:
            reader = self.reader_factory(config.telemetry)
            with self.lock:
                self.reader = reader
            reader.start()

    def stop(self):
        self.running = False
        self.replace_reader()

    @contextmanager
    def command(self, generation):
        with self.lock:
            if generation != self.generation or self.active is None:
                raise HTTPException(409, 'Mission target changed or is unconfigured; review the current connection')
            self.inflight += 1
            self.command_serial += 1
        try:
            yield
        finally:
            with self.lock:
                self.inflight -= 1

    def track(self, key, value):
        with self.lock:
            if value.get('state') in ('succeeded', 'failed', 'cancelled'):
                self.pending.pop(key, None)
            else:
                self.pending[key] = {**deepcopy(value), 'operation_id': key}

    def apply(self, name, value, revision, acknowledge_unknown, get_status, invalidate):
        config = parse(value)
        if not self.apply_lock.acquire(blocking=False):
            raise HTTPException(409, 'Another connection apply is in progress')
        try:
            with self.lock:
                self.check_revision(revision)
                if name not in self.profiles:
                    raise ValueError('Select Simulator or Field')
                if self.inflight or self.pending:
                    raise HTTPException(409, 'Resolve vehicle commands in flight or with unknown outcomes before Apply. Query status and operations.')
                old, serial = self.active, self.command_serial
            changed = old is None or old.boat_url != config.boat_url
            radio_changed = old is None or old.telemetry != config.telemetry
            if changed and old:
                try:
                    status = get_status(old)
                except HTTPException:
                    status = None
                if fresh(status):
                    if not safe_to_leave(status):
                        raise HTTPException(409, 'Current boat must be disarmed, stopped (≤0.20 m/s), outside AUTO and not executing before switching mission API')
                elif not acknowledge_unknown:
                    raise HTTPException(409, 'Old boat state is unknown or stale. Explicitly acknowledge the unknown state to switch; no Stop or Disarm will be sent.')
            with self.lock:
                self.check_revision(revision)
                if serial != self.command_serial or self.inflight or self.pending:
                    raise HTTPException(409, 'A vehicle command raced with Apply. Reconcile it before retrying.')
                data = self.document()
                data['profiles'][name] = config.snapshot()
                data.update(selected_profile=name, active_profile=name, active=config.snapshot(), revision=self.revision + 1)
                self.persist(data)
                self.profiles, self.selected, self.active_profile = data['profiles'], name, name
                self.active, self.revision, self.error = config, data['revision'], None
                old_reader = self.reader if radio_changed else None
                if radio_changed:
                    self.reader = None  # New settings must never expose old cached positions.
                if changed:
                    self.generation += 1
                    self.resolved_unknown.clear()
                    self.api_status = None
                    self.status_at = None
                    self.api_error = None
                    invalidate()  # Registry only; no planner lock or network wait.
            if radio_changed:
                try:
                    self.replace_reader(old_reader)
                except RuntimeError as error:
                    # Never open a second reader after shutdown failure.
                    with self.lock:
                        self.error = f'Telemetry reconnect failed: {error}. Restart GCS before reconnecting.'
            return self.snapshot()
        finally:
            self.apply_lock.release()


def serial_devices(configured=None):
    paths = {port.device for port in list_ports.comports() if os.path.exists(port.device)}
    paths.update(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*') + glob.glob('/dev/serial/by-id/*') + glob.glob('/dev/gcs-radio'))
    if configured and configured.startswith('/dev/'):
        paths.add(configured)
    return [{'device': p, 'present': os.path.exists(p), 'accessible': os.access(p, os.R_OK | os.W_OK)} for p in sorted(paths)]
