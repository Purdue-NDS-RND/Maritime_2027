"""Ordered, independently configured run instances and final-route validation."""
from copy import deepcopy
import hashlib
import json
import math
from .geometry import to_local, finite, segment_distance
from .clearance import validate_route
from .task_geometry import resolve_geometry

INPUTS = ('steps', 'settings', 'planning_area', 'start', 'attempt', 'sizes_confirmed', 'shared_crossings', 'execution_budget_s')
SETUP_FIELDS = ('passages', 'direction', 'channel', 'channel_chains', 'connection_override', 'finish', 'finish_radius_m', 'entry_radius_m', 'exit_radius_m', 'course_confirmed')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def identity(object_map, run):
    return digest({'map': object_map, **{k: run.get(k) for k in INPUTS}})


def steps(run):
    values = run.get('steps', [])
    if not values or len(values) > 500:
        raise ValueError('Add 1..500 task or manual cards')
    ids = [s['id'] for s in values]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Every card needs a unique instance ID')
    if any(s['type'] not in ('gate', 'slalom', 'channel', 'manual') for s in values):
        raise ValueError('Unsupported card type')
    if run.get('shared_crossings'):
        raise ValueError('Gate and Slalom are separate tasks. Clear shared crossings and Generate again')
    return values


def task_input(run, step, start, final):
    setup = {k: deepcopy(v) for k, v in step['setup'].items() if k in SETUP_FIELDS}
    setup.update(deepcopy(run['settings']))
    setup.update(task='custom', start=deepcopy(start), waypoints=[], planning_area=deepcopy(run['planning_area']),
                 sizes_confirmed=run.get('sizes_confirmed', False), finish_radius_m=setup.get('finish_radius_m', 1),
                 attempt={'mode': 'full', 'start_source': run['attempt']['start_source']}, transit_finish=not final)
    if step['type'] == 'manual':
        setup['waypoints'] = deepcopy(step['setup'].get('waypoints', []))
        if not setup['waypoints']:
            raise ValueError('Manual card '+step['id']+' needs ordered waypoints')
        setup['finish'] = deepcopy(setup['waypoints'][-1])
    else:
        if step['type'] == 'slalom' and (setup.get('passages') or [{}])[0].get('kind') == 'gate':
            raise ValueError('Slalom starts at the first turn. Move the starting gate to a separate Gate card and review again')
        setup.update(planner_task=step['type'], geometry_version=2, require_full_entrance=True)
    return setup


def validate_run(object_map, run, actual_start=None):
    errors, preferred, towers = [], [], []
    try:
        values = steps(run)
        if not run.get('sizes_confirmed') or any(not s['setup'].get('course_confirmed') for s in values):
            raise ValueError('Review the map and every complete card before generation')
        if run.get('generation_identity') != identity(object_map, run):
            raise ValueError('Run inputs changed: Generate and approve a fresh complete run')
        if not run.get('attempt', {}).get('captured_at') or run['attempt'].get('start_snapshot') != run['start']:
            raise ValueError('Generate a fresh run start before approval')
        if run['attempt'].get('mode') != 'full':
            raise ValueError('Run cards require complete tasks')
        if not 10 <= finite(run['execution_budget_s']) <= 7200:
            raise ValueError('Execution budget must be within 10..7200 seconds')
        if any(run.get(k) != v for k,v in run['settings'].items()):
            raise ValueError('Flattened run settings differ from shared settings')
        expected = values
        blocks = run.get('blocks', [])
        if [b['instance_id'] for b in blocks] != [s['id'] for s in expected]:
            raise ValueError('Run must contain every ordered card instance')
        points = run['waypoints']
        if not 1 <= len(points) <= 500:
            raise ValueError('Run requires 1..500 waypoints')
        cursor = 0
        for i, (block, step) in enumerate(zip(blocks, expected)):
            lo, hi = block['waypoint_start'], block['waypoint_end']
            final = i == len(blocks)-1
            if lo != cursor or not lo < hi <= len(points) or block['type'] != step['type'] or block['instances'] != [step['id']] or block['stopped_finish'] != final:
                raise ValueError('Invalid instance ranges or stopped-finish metadata')
            start = run['start'] if lo == 0 else points[lo-1]
            d = task_input(run, step, start, final)
            if step['type'] == 'manual' and points[lo:hi] != d['waypoints']:
                raise ValueError('Manual card waypoints must remain exactly as configured')
            d['waypoints'] = points[lo:hi]
            d['attempt'].update(block.get('attempt', {}))
            if lo == 0 and actual_start is not None:
                d['start'] = actual_start
            check = validate_route(object_map, d, transit_finish=not final)
            errors.extend({**e, 'instance_id': step['id'], 'waypoint_start': lo} for e in check['errors'])
            preferred.extend({**e, 'leg': e['leg']+lo, 'instance_id': step['id']} for e in check['preferred_shortfalls'])
            towers.extend({**e, 'leg': e['leg']+lo, 'instance_id': step['id']} for e in check['tower_shortfalls'])
            cursor = hi
        if cursor != len(points) or run['finish'] != points[-1] or run['finish_radius_m'] != task_input(run, expected[-1], run['start'], True)['finish_radius_m']:
            raise ValueError('Run final finish or waypoint ranges changed')
        # Preserve sub-leg approach/task splits without adding mission points.
        sections = run.get('route_sections', [])
        if {s['leg'] for s in sections} != set(range(len(points))):
            raise ValueError('Every emitted leg needs an instance section')
        route = [run['start'], *points]
        ref = object_map['geographic_reference']
        for leg in range(len(points)):
            block = next(b for b in blocks if b['waypoint_start'] <= leg < b['waypoint_end'])
            a,b = [to_local(p,ref) for p in route[leg:leg+2]]
            previous = a
            for section in [s for s in sections if s['leg'] == leg]:
                u,v = [to_local(section[k],ref) for k in ('start','end')]
                if section['instance_id'] != block['instance_id'] or section['kind'] not in ('connector','task','manual') or math.dist(previous,u) > .001 or segment_distance(u,a,b) > .001 or segment_distance(v,a,b) > .001:
                    raise ValueError('Invalid instance/connector section association')
                previous = v
            if math.dist(previous,b) > .001:
                raise ValueError('Instance sections do not reach emitted waypoint')
        if actual_start is not None and math.dist(to_local(actual_start, object_map['geographic_reference']), to_local(run['start'], object_map['geographic_reference'])) > 1:
            raise ValueError('Boat moved more than 1 m from approved start: Generate and approve again')
    except (ValueError, KeyError, TypeError, IndexError, StopIteration) as error:
        errors.append({'reason': str(error), 'location': None})
    return {'valid': not errors, 'errors': errors, 'preferred_shortfalls': preferred, 'tower_shortfalls': towers}
