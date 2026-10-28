"""One passive MAVLink reader; snapshots never own or command the vehicle."""
from copy import deepcopy
from dataclasses import dataclass
import logging
import math
import os
import socket
import threading
import time
import uuid

from pymavlink import mavutil

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelemetryConfig:
    connection: str = 'udpin:127.0.0.1:14550'
    baud: int = 57600
    system_id: int = 1
    component_id: int = 1

    def __post_init__(self):
        if not self.connection.startswith(('udpin:', '/dev/')):
            raise ValueError('GCS MAVLink connection must be udpin:HOST:PORT or /dev/DEVICE')
        if self.connection.startswith('udpin:'):
            parts = self.connection.split(':')
            if len(parts) != 3 or not parts[1] or not parts[2].isdigit() or not 1 <= int(parts[2]) <= 65535:
                raise ValueError('GCS MAVLink UDP endpoint must be udpin:HOST:PORT (port 1..65535)')
        if self.baud <= 0:
            raise ValueError('GCS MAVLink baud must be positive')
        if not 1 <= self.system_id <= 255 or not 1 <= self.component_id <= 255:
            raise ValueError('GCS MAVLink system/component IDs must be in 1..255')

    @classmethod
    def from_env(cls):
        return cls(
            connection=os.getenv('GCS_MAVLINK_CONNECTION', cls.connection),
            baud=int(os.getenv('GCS_MAVLINK_BAUD', cls.baud)),
            system_id=int(os.getenv('GCS_MAVLINK_SYSTEM_ID', cls.system_id)),
            component_id=int(os.getenv('GCS_MAVLINK_COMPONENT_ID', cls.component_id)),
        )


def open_connection(connection, **kwargs):
    if connection.startswith('udpin:'):
        _, host, port = connection.split(':')
        # pymavlink enables SO_REUSEADDR. Refuse an occupied consumer port
        # first, then disable sharing on our reader so another client cannot
        # silently steal its datagrams. Each client needs a separate output.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind((host, int(port)))
    link = mavutil.mavlink_connection(connection, **kwargs)
    if connection.startswith('udpin:'):
        link.port.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    return link


class Telemetry:
    def __init__(self, config, clock=time.monotonic, connect=open_connection):
        self.config = config
        self.clock = clock
        self.connect = connect
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.error = None
        self.reset()

    def reset(self):
        self.session_id = uuid.uuid4().hex
        self.values = {'position': None, 'heading_deg': None, 'speed_m_s': None,
                       'gps_fix': None, 'mode': None, 'armed': None, 'time_boot_ms': None}
        self.times = {'heartbeat': None, 'position': None, 'gps': None}

    def snapshot(self):
        with self.lock:
            now = self.clock()
            ages = {key + '_age_s': None if timestamp is None else max(0, now - timestamp)
                    for key, timestamp in self.times.items()}
            stale = any(ages[key] is None or ages[key] > 3
                        for key in ('heartbeat_age_s', 'position_age_s'))
            return {**deepcopy(self.values), **ages, 'source': 'mavlink',
                    'system_id': self.config.system_id, 'component_id': self.config.component_id,
                    'session_id': self.session_id, 'stale': stale or self.error is not None,
                    'connection_state': 'error' if self.error else 'waiting' if self.times['heartbeat'] is None
                    else 'stale' if stale else 'live', 'error': self.error}

    def ingest(self, message):
        if (message.get_srcSystem(), message.get_srcComponent()) != (
                self.config.system_id, self.config.component_id):
            return
        kind = message.get_type()
        now = self.clock()
        with self.lock:
            if kind == 'HEARTBEAT':
                if (message.autopilot != mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA
                        or message.type != mavutil.mavlink.MAV_TYPE_SURFACE_BOAT):
                    return
                if self.times['heartbeat'] is not None and now - self.times['heartbeat'] > 3:
                    self.reset()
                self.times['heartbeat'] = now
                self.values.update(mode=message.custom_mode,
                                   armed=bool(message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))
                return
            if self.times['heartbeat'] is None or now - self.times['heartbeat'] > 3:
                return
            if kind == 'GLOBAL_POSITION_INT':
                if not (-900000000 <= message.lat <= 900000000
                        and -1800000000 <= message.lon <= 1800000000):
                    return
                previous = self.values['time_boot_ms']
                if previous == message.time_boot_ms:
                    return
                # Unsigned subtraction accepts the 32-bit clock wrap but rejects
                # duplicates/reordering. After a stale position, a new clock epoch
                # can recover a reboot without displaying cached pre-reboot data.
                if previous is not None and not 0 < (message.time_boot_ms - previous) % 2**32 < 2**31:
                    if now - self.times['position'] <= 3:
                        return
                    heartbeat = self.times['heartbeat']
                    mode, armed = self.values['mode'], self.values['armed']
                    self.reset()
                    self.times['heartbeat'] = heartbeat
                    self.values.update(mode=mode, armed=armed)
                speed = (math.hypot(message.vx, message.vy) / 100
                         if all(-32767 <= v < 32767 for v in (message.vx, message.vy)) else None)
                self.values.update(position={'latitude': message.lat / 1e7, 'longitude': message.lon / 1e7},
                                   heading_deg=message.hdg / 100 if 0 <= message.hdg < 36000 else None,
                                   speed_m_s=speed, time_boot_ms=message.time_boot_ms)
                self.times['position'] = now
            elif kind == 'GPS_RAW_INT':
                self.values['gps_fix'] = message.fix_type
                self.times['gps'] = now

    def start(self):
        self.thread = threading.Thread(target=self.run, name='gcs-mavlink-telemetry', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                raise RuntimeError('GCS MAVLink reader did not stop')

    def run(self):
        while not self.stop_event.is_set():
            link = None
            try:
                link = self.connect(self.config.connection, baud=self.config.baud,
                                    source_system=254, source_component=190, autoreconnect=False)
                with self.lock:
                    self.reset()
                    self.error = None
                while not self.stop_event.is_set():
                    message = link.recv_match(blocking=True, timeout=0.2)
                    if message is not None:
                        self.ingest(message)
            except Exception as error:
                logger.warning('GCS telemetry connection unavailable: %s', error)
                with self.lock:
                    self.error = str(error)
            finally:
                if link is not None:
                    try:
                        link.close()
                    except OSError:
                        logger.exception('Could not close GCS telemetry connection')
            self.stop_event.wait(1)
