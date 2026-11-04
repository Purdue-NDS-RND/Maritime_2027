"""Atomic complete-task run generation with one shared planning deadline."""
from copy import deepcopy
import math
import time
from shared.competition import identity, selected_tasks, task_input, shared_gate, validate_run
from shared.geometry import to_local
from shared.task_geometry import resolve_geometry
from .attempts import capture_start
from .planner import generate
from .settings import effective_settings, validate_settings


def new_run(state):
    draft = state.get('draft') or {}
    return {'planning_mode': 'competition', 'selected_tasks': [], 'task_setup': deepcopy(state.get('course', {})),
            'settings': effective_settings(state['game_settings']), 'planning_area': deepcopy(draft.get('planning_area', [])),
            'attempt': {'mode': 'full', 'start_source': 'live'}, 'start': deepcopy(draft.get('start') or state['map']['geographic_reference']),
            'finish': deepcopy(draft.get('finish') or state['map']['geographic_reference']), 'sizes_confirmed': draft.get('sizes_confirmed', False), 'share_gate': False, 'waypoints': [], 'finish_radius_m': 1, 'execution_budget_s': 300}


def review_geometry(object_map, run):
    result = {}
    for task in selected_tasks(run):
        resolved = resolve_geometry(object_map, task_input(run, task, run['start'], task == run['selected_tasks'][-1]))
        result[task] = {key: resolved[key] for key in ('derived_sections', 'channel') if key in resolved}
    return result


def generate_run(object_map, run, status=None, max_seconds=60):
    deadline = time.monotonic() + min(60, max_seconds)
    result = {'success': False, 'diagnostics': [], 'errors': []}
    try:
        if run.get('settings', {}).get('tower_avoidance') is not None:
            validate_settings({'version': 1, **run['settings'], 'task_overrides': {}})
        run = capture_start(run, status)
        tasks = selected_tasks(run)
        if run['attempt'].get('mode') != 'full':
            raise ValueError('Competition runs require complete tasks; remaining-section resume is unavailable')
        for task in tasks:
            setup = run['task_setup'].get(task)
            if not setup or not setup.get('course_confirmed') or not setup.get('sizes_confirmed'):
                raise ValueError('Review and confirm complete '+task+' assignments before generation')
        run['shared_crossing'] = shared_gate(object_map, run)
        run['review_geometry'] = review_geometry(object_map, run)
        run.update(waypoints=[], blocks=[], route_sections=[])
        attempts = []
        for task in tasks:
            if task == 'gate' and run.get('share_gate'):
                continue
            start = run['waypoints'][-1] if run['waypoints'] else run['start']
            final = task == tasks[-1]
            d = task_input(run, task, start, final)
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Run generation time limit reached; no partial run published')
            generated = generate(object_map, d, max_seconds=remaining, deadline=deadline, transit_finish=not final)
            attempts.append({'task': task, 'searches': generated.get('attempts', [])})
            if not generated['success']:
                return {**generated, 'failed_task': task, 'attempts': attempts}
            d = generated['draft']
            lo = len(run['waypoints'])
            run['waypoints'].extend(d['waypoints'])
            run['blocks'].append({'task': task, 'tasks': ['gate', 'slalom'] if task == 'slalom' and run.get('share_gate') else [task],
                                  'waypoint_start': lo, 'waypoint_end': len(run['waypoints']), 'attempt': d['attempt'], 'stopped_finish': final})
            run['route_sections'].extend({**section, 'leg': section['leg']+lo, 'task': task,
                                          'kind': 'connector' if section['kind'] == 'approach' else 'task'} for section in d['route_sections'])
        run.update({k: deepcopy(v) for k, v in run['settings'].items()})
        run['finish'] = deepcopy(run['waypoints'][-1])
        run['finish_radius_m'] = run['task_setup'][tasks[-1]]['finish_radius_m']
        ref = object_map['geographic_reference']
        points = [to_local(p, ref) for p in [run['start'], *run['waypoints']]]
        run['route_length_m'] = sum(math.dist(a,b) for a,b in zip(points, points[1:]))
        run['nominal_travel_s'] = run['route_length_m']/run['speed_m_s']
        run['suggested_budget_s'] = max(300, math.ceil(2*run['nominal_travel_s']+60))
        run['budget_exceeds_boat_limit'] = run['suggested_budget_s'] > 7200
        run['generation_identity'] = identity(object_map, run)
        validation = validate_run(object_map, run)
        if time.monotonic() > deadline:
            raise TimeoutError('Run generation time limit reached during validation; no partial run published')
        if not validation['valid']:
            return {'success': False, 'diagnostics': [e['reason'] for e in validation['errors']], 'errors': validation['errors']}
        return {'success': True, 'draft': run, 'validation': validation, 'attempts': attempts, 'diagnostics': []}
    except (ValueError, KeyError, TypeError, IndexError, TimeoutError) as error:
        reason = str(error)
        return {**result, 'diagnostics': [reason], 'errors': [{'reason': reason, 'code': 'search_exhausted' if isinstance(error, TimeoutError) else 'invalid_setup', 'location': None}]}
