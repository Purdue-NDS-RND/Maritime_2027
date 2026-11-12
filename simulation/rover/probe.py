"""Health requires independently advancing physics and fresh rover GPS/heartbeat."""
import json
import subprocess
import time
from pathlib import Path
from pymavlink import mavutil


def probe():
    subprocess.run(['python3', '/opt/boat_sim/scripts/gazebo_clock_ready.py',
                    '/world/rover_flat/clock'], check=True, timeout=6)
    link = mavutil.mavlink_connection('udpin:127.0.0.1:14559')
    heartbeat = gps = position = None
    deadline = time.monotonic() + 5
    try:
        while time.monotonic() < deadline:
            msg = link.recv_match(blocking=True, timeout=0.2)
            if msg is None or (msg.get_srcSystem(), msg.get_srcComponent()) != (1, 1):
                continue
            if msg.get_type() == 'HEARTBEAT':
                if msg.type != mavutil.mavlink.MAV_TYPE_GROUND_ROVER or msg.autopilot != 3:
                    raise RuntimeError('expected ArduPilot ground rover')
                heartbeat = time.monotonic()
            elif msg.get_type() == 'GPS_RAW_INT' and msg.fix_type >= 3:
                gps = time.monotonic()
            elif msg.get_type() == 'GLOBAL_POSITION_INT':
                if abs(msg.lat / 1e7 - 51.566151) < 0.01 and abs(msg.lon / 1e7 + 4.034345) < 0.01:
                    position = time.monotonic()
            if all(value is not None and time.monotonic() - value < 3 for value in (heartbeat, gps, position)):
                Path('/sim/ready.json').write_text(json.dumps({'ready': True, 'time': time.time(), 'vehicle_type': 10}))
                return
        raise RuntimeError('fresh ground-rover heartbeat, GPS and origin-aligned position required')
    finally:
        link.close()


if __name__ == '__main__':
    probe()
