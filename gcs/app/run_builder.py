"""Atomic ordered instance generation using the existing bounded planner."""
from copy import deepcopy
import math
import time
from shared.geometry import to_local
from shared.run_builder import steps, task_input, confirmed_pairs, identity, validate_run
from .attempts import capture_start
from .planner import generate
from .settings import defaults, effective_settings, validate_settings


def new_run(object_map=None):
    start = deepcopy((object_map or {}).get('geographic_reference'))
    return {'planning_mode': 'run', 'steps': [], 'settings': effective_settings(defaults()), 'planning_area': [],
            'start': start, 'attempt': {'mode': 'full', 'start_source': 'live'}, 'sizes_confirmed': False,
            'shared_crossings': [], 'waypoints': [], 'execution_budget_s': 300}


def generate_run(object_map, run, status=None, max_seconds=60):
    deadline = time.monotonic()+min(60, max_seconds)
    current = None
    try:
        validate_settings({'version': 1, **run['settings'], 'task_overrides': {}})
        run = capture_start(run, status)
        values = steps(run)
        if not run.get('sizes_confirmed') or any(not s['setup'].get('course_confirmed') for s in values):
            raise ValueError('Review the map and every complete card before generation')
        if run['attempt']['mode'] != 'full':
            raise ValueError('Cards require complete tasks')
        pairs = confirmed_pairs(object_map, run)
        run.update(waypoints=[], blocks=[], route_sections=[])
        for i, step in enumerate(values):
            current = step['id']
            if current in pairs:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError('Run generation time limit reached; no partial route published')
            final = i == len(values)-1
            start = run['waypoints'][-1] if run['waypoints'] else run['start']
            d = task_input(run, step, start, final)
            if not d.get('course_confirmed'):
                raise ValueError('Review and confirm card '+current)
            if step['type'] != 'manual':
                result = generate(object_map, d, deadline=deadline, max_seconds=deadline-time.monotonic(), transit_finish=not final)
                if not result['success']:
                    return {**result, 'failed_instance_id': current}
                d = result['draft']
            lo = len(run['waypoints'])
            run['waypoints'].extend(d['waypoints'])
            if len(run['waypoints']) > 500:
                raise ValueError('Run exceeds the 500-waypoint boat limit')
            run['blocks'].append({'instance_id': current, 'type': step['type'], 'instances': [*[k for k,v in pairs.items() if v == current], current],
                                  'waypoint_start': lo, 'waypoint_end': len(run['waypoints']), 'attempt': d['attempt'], 'stopped_finish': final})
            route = [start, *d['waypoints']]
            sections = d.get('route_sections') if step['type'] != 'manual' else None
            if sections:
                run['route_sections'].extend({**section, 'leg': lo+section['leg'], 'instance_id': current,
                                              'kind': 'connector' if section['kind'] == 'approach' else 'task'} for section in sections)
            else:
                run['route_sections'].extend({'leg': lo+leg, 'instance_id': current, 'kind': 'manual', 'start': a, 'end': b}
                                             for leg,(a,b) in enumerate(zip(route,route[1:])))
        run.update(deepcopy(run['settings']))
        run.update(finish=deepcopy(run['waypoints'][-1]), finish_radius_m=d['finish_radius_m'])
        points = [to_local(p, object_map['geographic_reference']) for p in [run['start'], *run['waypoints']]]
        run['route_length_m'] = sum(math.dist(a,b) for a,b in zip(points, points[1:]))
        run['nominal_travel_s'] = run['route_length_m']/run['speed_m_s']
        run['suggested_budget_s'] = max(300, math.ceil(2*run['nominal_travel_s']+60))
        run['budget_exceeds_boat_limit'] = run['suggested_budget_s'] > 7200
        run['generation_identity'] = identity(object_map, run)
        check = validate_run(object_map, run)
        if time.monotonic() >= deadline:
            raise TimeoutError('Run generation time limit reached during final validation')
        if not check['valid']:
            return {'success': False, 'errors': check['errors'], 'diagnostics': [e['reason'] for e in check['errors']]}
        return {'success': True, 'draft': run, 'validation': check, 'diagnostics': []}
    except (ValueError, KeyError, TypeError, IndexError, TimeoutError) as error:
        return {'success': False, 'failed_instance_id': current, 'diagnostics': [str(error)],
                'errors': [{'reason': str(error), 'instance_id': current, 'location': None}]}
