#!/usr/bin/env python3
"""Simulation-only manually supplied mission characterization.

Run in the boat image with boat source and simulator logs mounted. This is an
exclusive local-file test owner; stop the boat service first. Truth is recorded
only as measurement evidence and is never supplied to Executor.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
from pymavlink import mavutil
from boat_app.executor import Executor
from boat_app.mission import Mission
from measured_profiles import request_position_rate
from calibration_result import successful

ALLOWED = {'WP_RADIUS':(.05,10), 'WP_PIVOT_ANGLE':(0,180), 'WP_PIVOT_RATE':(1,180),
           'WP_ACCEL':(.01,10), 'WP_JERK':(0,100), 'ATC_STR_RAT_FF':(0,3),
           'ATC_SPEED_P':(.01,2), 'ATC_SPEED_I':(0,2)}


def set_parameter(controller, name, value):
    controller.link.mav.param_set_send(controller.system,controller.component,name.encode(),value,
                                        mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    # Readback is requested independently; an echoed PARAM_SET alone is not proof.
    actual = controller.parameter(name)
    if abs(actual-value)>max(1e-4,abs(value)*1e-5):
        raise RuntimeError(f'parameter {name}: requested {value}, readback {actual}')


def latest_truth(path):
    path=Path(path)
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-32768))
        return json.loads(stream.read().split(b'\n')[-2])


def run(args):
    root=args.output.parent
    root.mkdir(parents=True,exist_ok=True)
    sentinel=root/'RESTORATION_FAILED.json'
    if sentinel.exists():
        raise RuntimeError('previous parameter restoration failed; restore and verify before further experiments: '+str(sentinel))
    overrides=json.loads(args.overrides)
    if set(overrides)-set(ALLOWED):
        raise ValueError('only documented waypoint, steering feedforward and speed P/I parameters may be overridden')
    for name,value in overrides.items():
        low,high=ALLOWED[name]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError('unsupported override: '+name)
    events=[]
    def emit(event):events.append({'monotonic_s':time.monotonic(),**event})
    link=mavutil.mavlink_connection('udpin:127.0.0.1:14551',source_system=245,source_component=191)
    controller=Executor(link,emit)
    mission=Mission.load(args.mission)
    result={'mission':mission.as_dict(),'started_at':datetime.now(timezone.utc).isoformat(),
            'overrides':overrides,'original':{},'restored':{},'events':events,'samples':[]}
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            controller.tick()
            try:controller.fresh();break
            except Exception:time.sleep(.1)
        controller.fresh()
        if controller.armed:
            raise RuntimeError('calibration requires disarmed vehicle')
        result['position_rate_hz']=args.position_hz
        result['position_source_intervals_ms']=request_position_rate(controller,args.position_hz)
        controller.command(mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE,mavutil.mavlink.MAVLINK_MSG_ID_AUTOPILOT_VERSION)
        if controller.firmware_version is None:
            controller.wait(lambda m:m.get_type()=='AUTOPILOT_VERSION')
        result['firmware']={'flight_sw_version':controller.firmware_version,
                            'git_hash_short':controller.firmware_hash}
        result['baseline']={name:controller.parameter(name) for name in ALLOWED}
        for name,value in overrides.items():
            result['original'][name]=controller.parameter(name)
            set_parameter(controller,name,value)
        result['applied']={name:controller.parameter(name) for name in ALLOWED}
        controller.upload(mission)
        result['start_physics']=latest_truth(args.truth)
        controller.start()
        while controller.state in ('executing','stopping'):
            controller.tick()
            result['samples'].append({'status':controller.status(),'physics':latest_truth(args.truth),
                                      'monotonic_s':time.monotonic()})
            time.sleep(.1)
        result['boat_outcome']=controller.status()
        result['end_physics']=latest_truth(args.truth)
    except Exception as error:
        result['error']=str(error)
    finally:
        # Confirm safe state before parameter restoration, including failed starts.
        try:
            controller.stop()
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                controller.tick()
                if controller.speed is not None and controller.speed<=.2:break
                time.sleep(.1)
            controller.disarm()
        except Exception as error:result['cleanup_error']=str(error)
        restoration_errors={}
        for name,value in result['original'].items():
            try:
                set_parameter(controller,name,value)
                result['restored'][name]=controller.parameter(name)
            except Exception as error:restoration_errors[name]=str(error)
        if restoration_errors:
            sentinel.write_text(json.dumps({'original':result['original'],'errors':restoration_errors},indent=2)+'\n')
            result['restoration_error']=restoration_errors
        try:
            # Restore the explicitly recorded launcher stream-rate baseline.
            controller.command(mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                               mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 1e6/args.baseline_position_hz)
            result['telemetry_restored_hz']=args.baseline_position_hz
        except Exception as error:
            result['cleanup_error']=result.get('cleanup_error','')+'; telemetry restoration: '+str(error)
        link.close()
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ('samples','events','start_physics','end_physics')},indent=2))
    return 0 if successful(result) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mission',type=Path)
    parser.add_argument('--truth',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--overrides',default='{}')
    parser.add_argument('--position-hz',type=int,choices=(4,10,20),default=4)
    parser.add_argument('--baseline-position-hz',type=int,choices=(4,10,20),default=4)
    raise SystemExit(run(parser.parse_args()))
