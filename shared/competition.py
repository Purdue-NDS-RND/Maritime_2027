"""Composite task semantics and validation, independent of generated paths."""
from copy import deepcopy
import hashlib
import json
import math
from .geometry import to_local, finite, segment_distance
from .task_geometry import resolve_geometry

TASKS = ('gate', 'slalom', 'channel')
SETTINGS = ('speed_m_s', 'clearance_m', 'preferred_buffer_m', 'tower_avoidance')


def identity(object_map, run):
    keys = ('selected_tasks', 'task_setup', 'planning_area', 'settings', 'share_gate', 'attempt', 'start')
    return hashlib.sha256(json.dumps({'map': object_map, **{k: run.get(k) for k in keys}}, sort_keys=True).encode()).hexdigest()


def selected_tasks(run):
    selected = run.get('selected_tasks', [])
    if not selected or selected != [t for t in TASKS if t in selected]:
        raise ValueError('Select complete tasks in Gate → Slalom → Channel order')
    return selected


def task_input(run, task, start, final=False):
    setup = deepcopy(run['task_setup'][task])
    setup.pop('planning_mode', None)
    # Saved paths and attempt progress are never inputs to a new run.
    for key in ('waypoints', 'generation_setup_sha256', 'route_sections', 'derived_sections', 'excluded_sections'):
        setup.pop(key, None)
    if set(run['settings']) - set(SETTINGS):
        raise ValueError('Run settings must contain only common speed, buffers and tower avoidance')
    for key in SETTINGS:
        setup.pop(key, None)
    setup.update(deepcopy(run['settings']))
    setup.update(planner_task=task, geometry_version=2, task='custom', start=deepcopy(start),
                 planning_area=deepcopy(run['planning_area']), waypoints=[],
                 attempt={'mode': 'full', 'start_source': run['attempt']['start_source']},
                 transit_finish=not final, require_full_entrance=True)
    return setup


def shared_gate(object_map, run):
    if not all(t in run.get('selected_tasks', []) for t in ('gate', 'slalom')):
        if run.get('share_gate'):
            raise ValueError('Shared crossing requires both Gate and Slalom')
        return {'compatible': False, 'reason': 'Select Gate and Slalom to compare their entrance'}
    drafts = [task_input(run, t, run['start']) for t in ('gate', 'slalom')]
    resolved = [resolve_geometry(object_map, d) for d in drafts]
    if any(not d.get('passages') for d in resolved):
        raise ValueError('Missing Gate or Slalom entrance assignments: review both tasks')
    gates = [d['passages'][0] for d in resolved]
    pair = lambda p: {p.get('red'), p.get('green')}
    same = all(p['kind'] == 'gate' for p in gates) and pair(gates[0]) == pair(gates[1]) and len(resolved[0]['passages']) == 1
    direction = same and sum(a*b for a, b in zip(gates[0]['direction'], gates[1]['direction'])) > .999999
    # Physical connection overrides describe distinct required events.
    compatible = bool(direction and drafts[0].get('connection_override') == drafts[1].get('connection_override') and (not drafts[0].get('connection_override') or drafts[0].get('entry_radius_m',1) == drafts[1].get('entry_radius_m',1)))
    if run.get('share_gate') and not compatible:
        raise ValueError('Cannot share gate: pairs, forward crossing directions or connection requirements differ')
    return {'compatible': compatible, 'confirmed': bool(run.get('share_gate')), 'pair': sorted(pair(gates[0])) if same else [],
            'direction': gates[0].get('direction'), 'reason': 'Same pair and forward crossing' if compatible else 'Separate crossing requirements; review the return approach',
            'scoring': 'planned task semantics only; no official scoring credit'}


def validate_run(object_map, run, actual_start=None):
    from .clearance import validate_route
    errors, preferred, towers = [], [], []
    def reject(reason):
        errors.append({'reason': reason, 'location': None})
    try:
        selected_tasks(run)
        if run.get('attempt', {}).get('mode') != 'full':
            reject('Competition runs require complete tasks')
        for key, value in run['settings'].items():
            if run.get(key) != value:
                reject('Flattened run settings differ from reviewed settings: '+key)
        if run.get('generation_identity') != identity(object_map, run):
            reject('Run inputs changed: Generate and approve a new complete run')
        if not run.get('attempt', {}).get('captured_at'):
            reject('Generate a fresh run start before approval')
        if run.get('attempt', {}).get('start_snapshot') != run.get('start'):
            reject('Run start changed: Generate again')
        relationship = shared_gate(object_map, run)
        if relationship != run.get('shared_crossing'):
            reject('Shared-crossing relationship changed')
        budget = finite(run['execution_budget_s'])
        if not 10 <= budget <= 7200:
            reject('Execution budget must be within boat limits: 10..7200 seconds')
        blocks = run.get('blocks', [])
        expected = [t for t in run['selected_tasks'] if not (t == 'gate' and run.get('share_gate'))]
        if [b['task'] for b in blocks] != expected:
            reject('Run must contain every selected complete task block')
        if any(b.get('tasks') != (['gate','slalom'] if b['task']=='slalom' and run.get('share_gate') else [b['task']]) for b in blocks):
            reject('Task/block sharing metadata changed')
        if any(b.get('stopped_finish') != (i == len(blocks)-1) for i,b in enumerate(blocks)):
            reject('Only the final task may have a stopped finish')
        if blocks and run.get('finish_radius_m') != run['task_setup'][blocks[-1]['task']]['finish_radius_m']:
            reject('Final finish radius changed')
        cursor = 0
        points = run['waypoints']
        if not 1 <= len(points) <= 500:
            reject('run requires 1..500 waypoints')
        for i, block in enumerate(blocks):
            lo, hi = block['waypoint_start'], block['waypoint_end']
            if lo != cursor or not lo < hi <= len(points):
                raise ValueError('Invalid global task waypoint ranges')
            start = run['start'] if lo == 0 else points[lo-1]
            d = task_input(run, block['task'], start, i == len(blocks)-1)
            d['waypoints'] = points[lo:hi]
            # Preserve generated progress for checking the actual initial connection.
            d['attempt'].update(block['attempt'])
            if lo == 0 and actual_start is not None:
                d['start'] = actual_start
            result = validate_route(object_map, d, transit_finish=i != len(blocks)-1)
            for e in result['errors']:
                errors.append({**e, 'task': block['task'], 'waypoint_start': lo})
            preferred.extend({**s, 'leg': s['leg']+lo} for s in result['preferred_shortfalls'])
            towers.extend({**s, 'leg': s['leg']+lo} for s in result['tower_shortfalls'])
            cursor = hi
        ref = object_map['geographic_reference']
        route = [run['start'], *points]
        sections = run.get('route_sections', [])
        if {s['leg'] for s in sections} != set(range(len(points))):
            reject('Every emitted GPS leg needs a task/connector section')
        for leg in range(len(points)):
            parts = [s for s in sections if s['leg']==leg]
            if not parts:
                continue
            block = next((b for b in blocks if b['waypoint_start'] <= leg < b['waypoint_end']), None)
            a,b = [to_local(p,ref) for p in route[leg:leg+2]]
            previous = a
            for section in parts:
                u,v = to_local(section['start'],ref),to_local(section['end'],ref)
                if not block or section['task'] != block['task'] or section['kind'] not in ('task','connector'):
                    reject('Invalid task/connector section association')
                if math.dist(previous,u) > .001 or segment_distance(u,a,b) > .001 or segment_distance(v,a,b) > .001:
                    reject('Task/connector sections do not follow the emitted GPS segment')
                previous = v
            if math.dist(previous,b) > .001:
                reject('Task/connector sections do not reach the emitted waypoint')
        if cursor != len(points):
            reject('Unassigned connector or task waypoints')
        if not blocks or run.get('finish') != run['task_setup'][blocks[-1]['task']]['finish'] or run.get('finish') != points[-1]:
            reject('Run final finish changed')
        if actual_start is not None:
            # An approved run is a fresh full attempt, never a resume from progress.
            ref = object_map['geographic_reference']
            if math.dist(to_local(actual_start, ref), to_local(run['start'], ref)) > 1:
                reject('Boat moved more than 1 m from the approved run start: Generate and approve a new complete run')
    except (ValueError, KeyError, TypeError, IndexError) as error:
        reject(str(error))
    return {'valid': not errors, 'errors': errors, 'preferred_shortfalls': preferred, 'tower_shortfalls': towers,
            'map_verification': 'live / unverified', 'bound_scope': 'operator-selected point buffers; independent physical evaluation required'}
