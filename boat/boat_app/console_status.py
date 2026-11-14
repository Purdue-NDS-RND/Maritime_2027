"""Human-readable bench diagnostics, independent of mission/control behavior."""

import math


def fresh(age):
    return type(age) in (float, int) and math.isfinite(age) and 0 <= age <= 3


class ConsoleStatus:
    def __init__(self, logger, repeat_s=15):
        self.logger = logger
        self.repeat_s = repeat_s
        self.previous = {}

    def report(self, channel, key, level, message, now, repeat=False):
        previous = self.previous.get(channel)
        if previous is None or previous[0] != key or (repeat and now - previous[1] >= self.repeat_s):
            # rclpy caches severity per call site; keep fixed-severity calls on
            # separate lines when a diagnostic changes from waiting to live.
            if level == 'warning':
                self.logger.warning(message)
            else:
                self.logger.info(message)
            self.previous[channel] = (key, now)

    def update(self, status, now):
        connected = status.get('system_id') is not None and fresh(status.get('heartbeat_age_s'))
        if not connected:
            seen = status.get('system_id') is not None
            detail = status.get('detail', 'Waiting for an ArduPilot Rover/boat heartbeat.')
            message = (f"Flight controller LOST: heartbeat is stale. Last vehicle "
                       f"{status['system_id']}/{status.get('component_id')}. Check USB/power and baud."
                       if seen else f"Flight controller NOT CONNECTED: {detail}. Check device, power, MAVLink and baud.")
            self.report('controller', ('waiting', detail, seen), 'warning', message, now, repeat=True)
            # GPS and mission messages must be emitted again on reconnection.
            self.previous.pop('gps', None)
            self.previous.pop('mission', None)
            return
        mode = next((name for name, number in status.get('available_modes', {}).items()
                     if number == status.get('mode')), str(status.get('mode', 'unknown')))
        identity = status['system_id'], status.get('component_id'), mode, status.get('armed')
        self.report('controller', identity, 'info',
                    f"Flight controller CONNECTED: ArduPilot Rover/boat, system {identity[0]}, "
                    f"component {identity[1]} | mode {mode} | {'ARMED' if identity[3] else 'DISARMED'}.", now)
        fix = status.get('gps_fix', 0)
        position_ok = status.get('position') is not None and fresh(status.get('position_age_s'))
        gps_ok = type(fix) in (int, float) and fix >= 3 and position_ok
        if gps_ok:
            message = f'GPS: 3D fix or better (fix {fix}); position messages are fresh. Mission checks still apply.'
        elif type(fix) in (int, float) and fix >= 3:
            message = f'GPS: fix {fix} reported, but position messages are missing or stale; not ready for navigation.'
        else:
            message = f'GPS: no 3D fix (fix {fix}); controller connected, not ready for GPS navigation.'
        self.report('gps', (gps_ok, fix, position_ok), 'info' if gps_ok else 'warning', message, now)
        self.report('mission', (status.get('state'), status.get('detail')), 'info',
                    f"Mission state {status.get('state', 'unknown').upper()}: {status.get('detail', '')}.", now)
