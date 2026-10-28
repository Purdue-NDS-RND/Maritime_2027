#!/usr/bin/env python3
"""Independent fixed-course evaluation from physics-step evidence.

A complete recording must include every step during the selected mission time
window. No steering or localization output is produced. JSONL may be gzip.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.geometry import polygon_clearance, transform_polygon


def evaluate(samples, footprint, course, start_s, end_s):
    minimum = math.inf
    failures, missing, passages, trajectory = [], [], [], []
    sequence = course['passages']
    next_passage = 0
    previous, finish_since, finished = None, None, False
    count = 0
    finish_error = None
    finish_window_max_error = finish_window_peak_speed = 0
    moving_distance, duration, speed_integral, peak = 0, 0, 0, 0
    for sample in samples:
        t = sample['time_s']
        if not all(isinstance(sample.get(key), (int, float)) and math.isfinite(sample[key]) for key in ('time_s', 'dt_s', 'iteration')):
            missing.append('non-finite physics clock/iteration')
            continue
        if t > end_s:
            break
        if t < start_s:
            continue
        count += 1
        poses = {item['name']: item['pose'] for item in sample['poses']}
        required = {'blueboat/base_link', *course['buoys']}
        if not required <= set(poses):
            missing.append('missing boat or buoy pose')
            continue
        if 'contacts' not in sample:
            missing.append('missing contact evidence')
        elif sample['contacts']:
            failures.append('contact recorded')
        if any(len(pose) != 6 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in pose) for pose in poses.values()):
            missing.append('invalid physics pose')
            continue
        x, y, z, roll, pitch, yaw = poses['blueboat/base_link']
        if abs(roll) > course.get('max_roll_pitch_rad', 0.05) or abs(pitch) > course.get('max_roll_pitch_rad', 0.05):
            missing.append('boat attitude exceeds footprint projection envelope')
        polygon = transform_polygon(footprint['polygon'], x, y, yaw)
        # Bound possible XY displacement from roll/pitch of the collision Z extent.
        vertical = footprint.get('max_abs_z_m')
        if vertical is None:
            missing.append('missing collision vertical extent')
            vertical = 0
        attitude_margin = (vertical * (abs(math.sin(roll)) + abs(math.sin(pitch)))
                           + footprint.get('enclosing_radius_m', 1) * (abs(1-math.cos(roll)) + abs(1-math.cos(pitch)) + abs(math.sin(roll)*math.sin(pitch))))
        step_minimum = math.inf
        for name, buoy in course['buoys'].items():
            separation = polygon_clearance(polygon, poses[name][:2], buoy['radius_m']) - attitude_margin
            step_minimum = min(step_minimum, separation)
            minimum = min(minimum, separation)
        speed = 0
        if previous is not None:
            dt = t - previous['time_s']
            if sample['iteration'] != previous['iteration'] + 1 or abs(dt - sample['dt_s']) > 1e-6:
                missing.append('missing or reversed physics steps')
            if dt <= 0:
                missing.append('non-increasing simulation time')
                continue
            speed = math.hypot(x - previous['x'], y - previous['y']) / dt
            moving_distance += speed * dt
            duration += dt
            speed_integral += speed * dt
            peak = max(peak, speed)
        # Passage planes use +X as course direction. Require initial footprint
        # wholly before every plane, lateral bounds throughout passage, then stern.
        for index, passage in enumerate(sequence):
            plane = passage['x']
            lowest, highest = min(p[0] for p in polygon), max(p[0] for p in polygon)
            if previous is None and highest >= plane:
                missing.append('recording starts after passage approach')
            if lowest <= plane <= highest:
                if passage['kind'] == 'gate':
                    if min(p[1] for p in polygon) < passage['y_min'] or max(p[1] for p in polygon) > passage['y_max']:
                        failures.append('footprint outside gate opening: ' + passage['id'])
                else:
                    buoy_y = poses[passage['buoy']][1]
                    if passage['side'] == 'left' and min(p[1] for p in polygon) <= buoy_y:
                        failures.append('wrong passing side: ' + passage['id'])
                    if passage['side'] == 'right' and max(p[1] for p in polygon) >= buoy_y:
                        failures.append('wrong passing side: ' + passage['id'])
            if previous is not None and previous['stern_x'] <= plane < lowest:
                if index != next_passage:
                    failures.append('missed/reversed passage order: ' + passage['id'])
                else:
                    passages.append({'id': passage['id'], 'stern_clear_time_s': t})
                    next_passage += 1
            if previous is not None and previous['stern_x'] > plane >= lowest and index < next_passage:
                failures.append('reversed cleared passage: ' + passage['id'])
        finish = course['finish']
        finish_error = math.hypot(x-finish['x'], y-finish['y'])
        inside = finish_error <= finish['radius_m']
        if previous is not None and inside and speed <= finish['speed_m_s']:
            finish_since = t if finish_since is None else finish_since
            finish_window_max_error = max(finish_window_max_error, finish_error)
            finish_window_peak_speed = max(finish_window_peak_speed, speed)
            if t - finish_since >= finish['settle_s']:
                finished = True
        else:
            finish_since, finished = None, False
            finish_window_max_error = finish_window_peak_speed = 0
        if count % 100 == 0:
            trajectory.append({'time_s': t, 'x': x, 'y': y, 'yaw_rad': yaw, 'speed_m_s': speed, 'clearance_m': step_minimum})
        previous = {'time_s': t, 'iteration': sample['iteration'], 'x': x, 'y': y,
                    'stern_x': min(p[0] for p in polygon)}
    if not count or previous is None:
        missing.append('empty evidence window')
    if previous and (previous['time_s'] < end_s - 0.002 or abs(start_s - (previous['time_s'] - duration)) > 0.002):
        missing.append('evidence does not cover mission window')
    if minimum < course['minimum_clearance_m']:
        failures.append('minimum footprint clearance violated')
    if next_passage != len(sequence):
        failures.append('incomplete course/stern exit')
    if not finished:
        failures.append('independent finish position/speed settling not met')
    if end_s - start_s > course.get('timeout_s', 300):
        failures.append('execution timeout')
    if not course.get('contact_recorder_verified', False):
        missing.append('live contact recorder has not been verified against deliberate contact')
    return {'outcome': 'inconclusive' if missing else 'failed' if failures else 'passed',
            'missing_evidence': sorted(set(missing)), 'failures': sorted(set(failures)),
            'physics_samples': count, 'minimum_clearance_m': minimum if math.isfinite(minimum) else None,
            'passages': passages, 'finish_settled': finished,
            'finish_window_start_s': finish_since, 'finish_position_error_m': finish_error,
            'finish_window_max_position_error_m': finish_window_max_error,
            'finish_window_peak_speed_m_s': finish_window_peak_speed, 'elapsed_s': end_s-start_s,
            'actual_mean_speed_m_s': speed_integral/duration if duration else None,
            'actual_peak_speed_m_s': peak, 'distance_m': moving_distance, 'trajectory': trajectory}


def verify_contact_evidence(course, course_directory):
    """CLI acceptance must not trust a manually asserted verification boolean."""
    course = dict(course)
    course['contact_recorder_verified'] = False
    try:
        path = Path(course['contact_verification_evidence'])
        if not path.is_absolute():
            path = Path(course_directory) / path
        proof = json.loads(path.read_text())
        course['contact_recorder_verified'] = (
            hashlib.sha256(path.read_bytes()).hexdigest() == course['contact_verification_sha256']
            and proof.get('scene_id') == course['scene_id'] and proof.get('outcome') == 'passed'
            and any(s.get('contacts') for s in proof.get('samples', [])))
    except (ValueError, KeyError, OSError, TypeError):
        pass
    return course


def read_window(path, start_s, end_s):
    opener = gzip.open if Path(path).suffix == '.gz' else open
    with opener(path, 'rt') as stream:
        for line in stream:
            if not line.endswith('\n'):
                break
            # The recorder puts time before its large pose array. Skip earlier
            # data without parsing every floating point pose in a long run.
            prefix = line[:160]
            if '"time_s":' in prefix:
                t = float(prefix.split('"time_s":', 1)[1].split(',', 1)[0])
                if t < start_s:
                    continue
                if t > end_s:
                    break
            yield json.loads(line)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('recording', 'footprint', 'course', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--start-s', type=float, required=True)
    parser.add_argument('--end-s', type=float, required=True)
    args = parser.parse_args()
    try:
        result = evaluate(read_window(args.recording, args.start_s, args.end_s), json.loads(args.footprint.read_text()),
                          verify_contact_evidence(json.loads(args.course.read_text()), args.course.parent), args.start_s, args.end_s)
    except (ValueError, KeyError, OSError, TypeError) as error:
        result = {'outcome': 'inconclusive', 'missing_evidence': [str(error)]}
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
