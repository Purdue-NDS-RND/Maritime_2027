"""Simulation experiment checks, independent of boat/GCS mission authorization."""
import json
import math
from pathlib import Path
from pymavlink import mavutil
from boat_app.executor import MissionError

WAYPOINT_PARAMETERS = {'WP_RADIUS','WP_PIVOT_ANGLE','WP_PIVOT_RATE','WP_ACCEL','WP_JERK'}
CONTROL_DEFAULTS = {'ATC_STR_RAT_FF':0.2, 'ATC_SPEED_P':0.1, 'ATC_SPEED_I':0.2}
ALLOWED_PARAMETERS = WAYPOINT_PARAMETERS | set(CONTROL_DEFAULTS)


def request_position_rate(controller, rate):
    if type(rate) is not int or rate not in (4,10,20):
        raise MissionError('unsupported profile position telemetry rate')
    controller.command(mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                       mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 1e6/rate)
    frames = [controller.wait(lambda m: m.get_type()=='GLOBAL_POSITION_INT', timeout=2).time_boot_ms
              for _ in range(8)]
    # Ignore the first transition interval. Source timestamps distinguish an
    # actual stream from queued packets or an acknowledgement without payloads.
    intervals = [(b-a) % 2**32 for a,b in zip(frames[1:],frames[2:])]
    if any(not 0 < interval <= 1500/rate for interval in intervals):
        raise MissionError('observed position telemetry interval does not match measured profile')
    controller.emit({'event':'position_rate_verified','requested_hz':rate,'source_intervals_ms':intervals})
    return intervals


def verify_profile(controller, name, directory, geometry_sha256):
    if name == 'local-file-unvalidated':
        return
    if not isinstance(name,str) or not name or Path(name).name != name:
        raise MissionError('invalid profile identity')
    try:
        profile=json.loads((Path(directory)/(name+'.json')).read_text())
    except (OSError,ValueError) as error:
        raise MissionError('selected navigation profile is unavailable') from error
    if profile['id']!=name or profile.get('status')!='calibrated':
        raise MissionError('selected navigation profile is not calibrated')
    position_rate=profile.get('position_rate_hz',4)
    if type(position_rate) is not int or position_rate not in (4,10,20):
        raise MissionError('unsupported profile position telemetry rate')
    if not geometry_sha256 or profile['geometry_sha256']!=geometry_sha256:
        raise MissionError('profile does not match configured boat geometry')
    controller.firmware_version=None
    controller.command(mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE,mavutil.mavlink.MAVLINK_MSG_ID_AUTOPILOT_VERSION)
    if controller.firmware_version is None:
        controller.wait(lambda m:m.get_type()=='AUTOPILOT_VERSION')
    if controller.firmware_version!=profile['firmware']['flight_sw_version']:
        raise MissionError('profile does not match active firmware version')
    if controller.firmware_hash!=profile['firmware']['git_hash_short']:
        raise MissionError('profile does not match active firmware source hash')
    parameters=profile['parameters']
    if not WAYPOINT_PARAMETERS <= set(parameters) or set(parameters)-ALLOWED_PARAMETERS:
        raise MissionError('profile must identify the five waypoint parameters and only supported control gains')
    # Earlier evidence used the pinned firmware's original control gains. Do
    # not authorize it with subsequently tuned steering or speed gains.
    parameters={**CONTROL_DEFAULTS, **parameters}
    for key,expected in parameters.items():
        if type(expected) not in (int,float) or not math.isfinite(expected):
            raise MissionError(f'profile parameter {key} must be finite')
        actual=controller.parameter(key)
        if not math.isfinite(actual) or abs(actual-expected)>max(.0001,abs(expected)*.00001):
            raise MissionError(f'active parameter {key} differs from measured profile')
    request_position_rate(controller, position_rate)
    controller.emit({'event':'navigation_profile_verified','profile_id':name,'geometry_sha256':geometry_sha256,
                     'firmware_version':controller.firmware_version,'parameters':parameters,
                     'position_rate_hz':position_rate})
