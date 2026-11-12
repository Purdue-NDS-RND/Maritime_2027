"""Exercise the real boat HTTP owner; record independent Gazebo poses throughout."""
import argparse
import json
import math
import re
from pathlib import Path
import subprocess
import time
import urllib.request
import urllib.error
import uuid


def request(path, method='GET', body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request('http://127.0.0.1:8091' + path, data=data,
                                 method=method, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.load(response)


def operation(path, method='POST', body=None):
    receipt = request(path, method, body)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = request('/operations/' + receipt['operation_id'])
        if result['state'] == 'succeeded':
            return result
        if result['state'] in ('failed', 'unknown'):
            raise RuntimeError(result)
        time.sleep(0.2)
    raise RuntimeError('operation timed out: ' + str(receipt))


def distance(a, b):
    lat = math.radians((a['latitude'] + b['latitude']) / 2)
    return math.hypot((a['latitude'] - b['latitude']) * 111195,
                      (a['longitude'] - b['longitude']) * 111195 * math.cos(lat))


def physics_position(model):
    raw = subprocess.run(['gz', 'topic', '-e', '-t', f'/model/{model}/odometry', '-n', '1'],
                         capture_output=True, text=True, timeout=6, check=True).stdout
    body = re.search(r'position\s*\{([^}]*)\}', raw)
    if body is None:
        raise RuntimeError('missing Gazebo physics position')
    return {axis: float(match.group(1)) if (match := re.search(r'\b' + axis + r':\s*([^\s]+)', body[1])) else 0.0
            for axis in ('x', 'y', 'z')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', default='rover_flat')
    parser.add_argument('--output', default='/sim/lifecycle-' + time.strftime('%Y%m%dT%H%M%S'))
    parser.add_argument('--model', default='wildthumper')
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    truth_file = (root / 'poses.txt').open('w')
    truth = subprocess.Popen(['gz', 'topic', '-e', '-t', f'/world/{args.world}/pose/info'],
                             stdout=truth_file, stderr=subprocess.STDOUT)
    records = (root / 'status.jsonl').open('w', buffering=1)
    result = {'passed': False}
    may_be_running = False
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                status = request('/status')
            except urllib.error.URLError:
                time.sleep(0.5)
                continue
            if status['heartbeat_age_s'] is not None and status['heartbeat_age_s'] < 3 and status['position_age_s'] is not None and status['position_age_s'] < 3 and status['gps_fix'] >= 3:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('boat API not fresh')
        origin = status['position']
        physics_origin = physics_position(args.model)
        mission_id = 'gazebo-lifecycle-' + str(uuid.uuid4())
        mission = {'mission_id': mission_id, 'speed_m_s': 0.7,
                   'waypoints': [{'latitude': origin['latitude'] + 8 / 111195,
                                  'longitude': origin['longitude']}],
                   'finish_radius_m': 3.0, 'finish_speed_m_s': 0.2,
                   'finish_settle_s': 5.0, 'timeout_s': 120.0, 'max_start_distance_m': 20.0}
        envelope = {'approval_id': 'simulation-validation', 'revision_sha256': mission_id, 'mission': mission}
        result['upload'] = operation('/missions/' + mission_id, 'PUT', envelope)
        may_be_running = True
        result['start'] = operation('/missions/' + mission_id + '/start')
        maximum = 0
        deadline = time.monotonic() + 135
        while time.monotonic() < deadline:
            status = request('/status')
            records.write(json.dumps({'time': time.time(), **status}) + '\n')
            maximum = max(maximum, distance(origin, status['position']))
            if status['state'] == 'complete':
                break
            if status['state'] in ('failed', 'interrupted', 'stopped'):
                raise RuntimeError(status)
            time.sleep(0.2)
        else:
            raise RuntimeError('mission did not complete')
        assert maximum >= 4, f'insufficient GPS displacement: {maximum}'
        assert status['mode'] == 5 and status['armed'], status
        assert status['heartbeat_age_s'] < 3, status
        result.update(gps_displacement_m=maximum, completion=status)
        mission['mission_id'] += '-replacement'
        mission['waypoints'] = [status['position']]
        result['armed_upload'] = operation('/missions/' + mission['mission_id'], 'PUT', envelope)
        status = request('/status')
        assert status['mode'] == 5 and status['armed'], status
        result['stop'] = operation('/stop')
        status = request('/status')
        assert status['mode'] == 4 and status['armed'] and status['heartbeat_age_s'] < 3, status
        result['stopped'] = status
        physics_end = physics_position(args.model)
        east = physics_end['x'] - physics_origin['x']
        north = physics_end['y'] - physics_origin['y']
        gps_north = (status['position']['latitude'] - origin['latitude']) * 111195
        gps_east = (status['position']['longitude'] - origin['longitude']) * 111195 * math.cos(math.radians(origin['latitude']))
        displacement = math.hypot(east, north)
        separation = math.hypot(east - gps_east, north - gps_north)
        result.update(physics_origin=physics_origin, physics_end=physics_end,
                      physics_displacement_m=displacement, gps_physics_separation_m=separation)
        if displacement < 4 or separation > 1.0:
            raise RuntimeError(f'physics displacement/alignment failed: {result}')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        if may_be_running:
            try:
                result['failure_stop'] = operation('/stop')
            except Exception as stop_error:
                result['failure_stop_error'] = str(stop_error)
        raise
    finally:
        truth.terminate()
        truth.wait(timeout=5)
        truth_file.close()
        records.close()
        (root / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
