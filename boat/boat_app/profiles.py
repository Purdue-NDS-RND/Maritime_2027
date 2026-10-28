"""Verify selected measured settings; never infer or silently change parameters."""
import json
import os
from pathlib import Path
from pymavlink import mavutil
from .executor import MissionError

ALLOWED_PARAMETERS = {'WP_RADIUS','WP_PIVOT_ANGLE','WP_PIVOT_RATE','WP_ACCEL','WP_JERK'}


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
    if set(parameters)!=ALLOWED_PARAMETERS:
        raise MissionError('profile must identify exactly the five measured waypoint parameters')
    for key,expected in parameters.items():
        actual=controller.parameter(key)
        if abs(actual-expected)>max(.0001,abs(expected)*.00001):
            raise MissionError(f'active parameter {key} differs from measured profile')
    controller.emit({'event':'navigation_profile_verified','profile_id':name,'geometry_sha256':geometry_sha256,
                     'firmware_version':controller.firmware_version,'parameters':parameters})
