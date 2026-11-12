"""Page-session planner state. Never reads or writes the operator data directory."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import threading
import uuid
from shared.object_map import validate_map
from shared.run_builder import INPUTS, digest, validate_run
from shared.clearance import validate_route
from .settings import defaults, effective_settings, validate_settings
from .run_builder import new_run
from .course_compiler import binding, validate_hints, validate_assignments


def empty_state():
    return {'map': None, 'original_map': None, 'run_draft': new_run(), 'approval': None,
            'planning_mode': 'run', 'game_settings': defaults(), 'revision': 0,
            'run_consumed': False, 'return_target': None, 'execution': None,
            'compiler_hints': {}, 'compilation': None, 'course_assignments': {},
            'map_history': {'undo': [], 'redo': []}}


class SessionWorkspace:
    def __init__(self):
        self.lock = threading.RLock()
        self.state = empty_state()
        self.authority_epoch = 0
        self.started_approval = None
        self.cancelled = threading.Event()

    def read(self):
        with self.lock:
            return deepcopy(self.state)

    def reset(self):
        with self.lock:
            revision = self.state['revision']+1
            self.state = {**empty_state(), 'revision': revision}
            self.started_approval = None
            self.authority_epoch += 1
            self.cancelled.set()
            return self.read()

    def edit(self, data):
        with self.lock:
            if data.get('revision') != self.state['revision']:
                raise ValueError('Superseded input revision: reload this session state')
            updated = deepcopy(self.state)
            if data.get('new_import'):
                updated = {**empty_state(), 'revision': self.state['revision']}
                self.started_approval = None
            if 'map' in data:
                updated['map'] = deepcopy(validate_map(data['map']))
                if data.get('new_import'):
                    updated['original_map'] = deepcopy(updated['map'])
                    updated['run_draft'] = new_run(updated['map'])
            if 'run_draft' in data:
                value = data['run_draft']
                # Only operator inputs can enter through edit, never a saved path,
                # derived progress, captured start, approval or generated identity.
                if value.get('planning_mode', 'run') != 'run':
                    if value != self.state['run_draft']:
                        raise ValueError('Return drafts are frozen; prepare a fresh return after changing inputs')
                else:
                    run = new_run(updated['map'])
                    run.update({k: deepcopy(value[k]) for k in INPUTS if k in value})
                    run['attempt'] = {'mode': 'full', 'start_source': value.get('attempt', {}).get('start_source', 'live')}
                    for step in run['steps']:
                        if step['type'] != 'manual':
                            step['setup'].pop('waypoints', None)
                    updated['run_draft'] = run
            if 'game_settings' in data:
                settings = validate_settings(data['game_settings'])
                if settings.get('task_overrides'):
                    raise ValueError('Run builder uses shared settings only')
                updated['game_settings'] = settings
                updated['run_draft']['settings'] = effective_settings(settings)
            old = self.state['run_draft']
            run = updated['run_draft']
            if updated['map'] != self.state['map'] and not data.get('new_import'):
                updated['map_history']['undo'] = [*updated['map_history']['undo'], deepcopy(self.state['map'])][-100:]
                updated['map_history']['redo'] = []
                updated['compilation'] = None
                updated['course_assignments'] = {}
                # Removed/retyped objects cannot remain pinned. Undo restores the
                # observations only; recognition is always reviewed afresh.
                ids = {o['id']:o for o in [*updated['map']['buoys'], *updated['map'].get('obstacles', [])]}
                updated['compiler_hints'] = {r:k for r,k in updated['compiler_hints'].items() if k in ids and ids[k].get('object_type')=='buoy'}
                try:
                    validate_hints(updated['map'], updated['compiler_hints'])
                except ValueError:
                    updated['compiler_hints'] = {}
                if updated.get('run_setup'):
                    updated['run_setup']['sizes_confirmed'] = False
                    for step in updated['run_setup']['steps']:
                        step['setup']['course_confirmed'] = False
                run['sizes_confirmed'] = False
                run['shared_crossings'] = []
                for step in run.get('steps', []):
                    step['setup']['course_confirmed'] = False
            # Preserve a generated route only for an identical input save. An
            # ordinary UI edit or settings/map change discards every result.
            same = all(run.get(k) == old.get(k) for k in INPUTS if k != 'attempt') and run.get('attempt', {}).get('start_source') == old.get('attempt', {}).get('start_source') and updated['map'] == self.state['map']
            if same:
                updated['run_draft'] = deepcopy(old)
            else:
                run.pop('generation_identity', None)
                run['waypoints'] = []
            updated['approval'] = None
            updated['revision'] += 1
            json.dumps(updated, allow_nan=False)
            self.state = updated
            self.authority_epoch += 1
            return self.read()

    def check_revision(self, revision):
        if revision != self.state['revision']:
            raise ValueError('Superseded input revision: reload this session state')

    def clear_recognition(self):
        self.state['compilation'] = None
        self.state['course_assignments'] = {}
        self.state['approval'] = None
        run = self.state['run_draft']
        run['waypoints'] = []
        run.pop('generation_identity', None)
        run['shared_crossings'] = []
        for step in run.get('steps', []):
            step['setup']['course_confirmed'] = False

    def import_course(self, value, revision):
        with self.lock:
            self.edit({'map': value['map'], 'new_import': True, 'revision': revision})
            self.state.update(original_map=deepcopy(value['original_map']), compiler_hints=deepcopy(value['hints']),
                              course_assignments=deepcopy(value['assignments']))
            return self.read()

    def history(self, direction, revision):
        with self.lock:
            self.check_revision(revision)
            if direction not in ('undo', 'redo') or not self.state['map_history'][direction]:
                raise ValueError('No map edit to '+str(direction))
            history = deepcopy(self.state['map_history'])
            target = history[direction].pop()
            other = 'redo' if direction == 'undo' else 'undo'
            history[other].append(deepcopy(self.state['map']))
            self.edit({'revision': revision, 'map': target})
            self.state['map_history'] = history
            self.clear_recognition()
            return self.read()

    def set_hints(self, hints, revision):
        with self.lock:
            self.check_revision(revision)
            checked = validate_hints(self.state['map'], hints)
            self.clear_recognition()
            self.state['compiler_hints'] = checked
            self.state['revision'] += 1
            self.authority_epoch += 1
            return self.read()

    def begin_compilation(self, revision):
        with self.lock:
            self.check_revision(revision)
            if not self.state['map']:
                raise ValueError('Import a map first')
            self.clear_recognition()
            self.state['revision'] += 1
            self.authority_epoch += 1
            return self.read(), (self.state['revision'], self.authority_epoch)

    def publish_compilation(self, result, token):
        with self.lock:
            if token != (self.state['revision'], self.authority_epoch) or result['binding'] != binding(self.state['map'], self.state['compiler_hints']):
                raise ValueError('Superseded compilation discarded; review current map and compile again')
            self.state['compilation'] = deepcopy(result)
            self.state['revision'] += 1
            return self.read()

    def select_compilation(self, task, candidate_id, revision):
        with self.lock:
            self.check_revision(revision)
            result = self.state['compilation']
            if candidate_id:
                if not result or result['binding'] != binding(self.state['map'], self.state['compiler_hints']):
                    raise ValueError('Compile the current map first')
                candidate = next((c for c in result['candidates'] if c['id'] == candidate_id), None)
                if not candidate or task not in candidate['tasks']:
                    raise ValueError('Task is unresolved in this interpretation')
                roles = candidate['tasks'][task]
            else:
                value = self.state['course_assignments'].get(task)
                if not value:
                    raise ValueError('No restored assignment to review')
                roles = value['roles']
            selected = {t:v['roles'] for t,v in self.state['course_assignments'].items()}
            selected[task] = roles
            validate_assignments(self.state['map'], selected, self.state['compiler_hints'])
            updated = deepcopy(self.state)
            updated['course_assignments'][task] = {'roles': deepcopy(roles), 'status': 'accepted'}
            updated['approval'] = None
            run = updated['run_draft']
            run['waypoints'] = []
            run.pop('generation_identity', None)
            run['shared_crossings'] = []
            for step in run.get('steps', []):
                if step['type'] == task:
                    from .course_setup import prepare_task
                    step['setup'] = prepare_task(updated['map'], task, run['settings'], roles)['draft']
            updated['revision'] += 1
            self.state = updated
            self.authority_epoch += 1
            return self.read()

    def clear_assignment(self, task, revision):
        with self.lock:
            self.check_revision(revision)
            self.state['course_assignments'].pop(task, None)
            self.state['approval'] = None
            self.state['run_draft']['waypoints'] = []
            self.state['run_draft'].pop('generation_identity', None)
            self.state['run_draft']['shared_crossings'] = []
            self.state['revision'] += 1
            self.authority_epoch += 1
            return self.read()

    def begin_generation(self):
        with self.lock:
            self.state['approval'] = None
            run = self.state['run_draft']
            run.pop('generation_identity', None)
            run['waypoints'] = []
            run.pop('blocks', None)
            run.pop('route_sections', None)
            self.state['revision'] += 1
            self.authority_epoch += 1
            return self.read(), (self.state['revision'], self.authority_epoch)

    def publish(self, draft, token):
        with self.lock:
            if token != (self.state['revision'], self.authority_epoch):
                raise ValueError('Superseded generation discarded; review current inputs and Generate again')
            if draft.get('planning_mode') == 'return' and self.state['run_draft'].get('planning_mode') == 'run':
                self.state['run_setup'] = {**new_run(self.state['map']), **{k:deepcopy(self.state['run_draft'].get(k)) for k in INPUTS}}
            self.state.update(run_draft=deepcopy(draft), approval=None, run_consumed=False)
            self.cancelled.clear()
            self.state['revision'] += 1
            return self.read()

    def consume_run(self):
        # Cancellation is visible before acquiring any state lock.
        self.cancelled.set()
        with self.lock:
            self.state['run_consumed'] = True
            self.state['approval'] = None
            self.state['compilation'] = None
            for value in self.state['course_assignments'].values():
                value['status'] = 'review_required'
            self.authority_epoch += 1

    def validate(self):
        with self.lock:
            if not self.state['map']:
                raise ValueError('Import and review a map first')
            if self.state['run_consumed']:
                raise ValueError('Run started or interrupted: Generate and approve a fresh run')
            d = self.state['run_draft']
            if d.get('planning_mode') == 'return':
                if d.get('return_target') != self.state['return_target'] or d.get('generation_identity') != digest({k:v for k,v in d.items() if k != 'generation_identity'}):
                    raise ValueError('Return target or inputs changed: prepare a fresh return')
                return validate_route(self.state['map'], d)
            return validate_run(self.state['map'], d)

    def approve(self):
        with self.lock:
            result = self.validate()
            if not result['valid']:
                raise ValueError(json.dumps(result))
            inputs = deepcopy({'map': self.state['map'], 'draft': self.state['run_draft']})
            d = inputs['draft']
            approval_id = str(uuid.uuid4())
            mission = {'mission_id': approval_id, 'waypoints': d['waypoints'], 'speed_m_s': d['speed_m_s'],
                       'finish_radius_m': d['finish_radius_m'], 'finish_speed_m_s': .2, 'finish_settle_s': 5,
                       'timeout_s': d['execution_budget_s'], 'max_start_distance_m': 100}
            approval = {'approved_at': datetime.now(timezone.utc).isoformat(), 'inputs': inputs, 'validation': result,
                        'envelope': {'approval_id': approval_id, 'revision_sha256': digest(inputs), 'mission': mission}}
            self.state['approval'] = approval
            return deepcopy(approval)

    def approved(self):
        with self.lock:
            approval = self.state['approval']
            if not approval or self.state['run_consumed']:
                raise ValueError('No current execution authority: Generate, Validate and Approve a fresh run')
            if not self.validate()['valid'] or digest({'map': self.state['map'], 'draft': self.state['run_draft']}) != approval['envelope']['revision_sha256']:
                raise ValueError('Approved inputs changed')
            return deepcopy(approval)

    def start_succeeded(self, approval):
        with self.lock:
            # Reset/import while a Start was in flight must not restore a target.
            if self.started_approval != approval['envelope']['approval_id']:
                return
            if approval['inputs']['draft'].get('planning_mode') != 'return':
                self.state['return_target'] = deepcopy(approval['inputs']['draft']['start'])


def return_inputs(state):
    """Reuse only the current explicit builder inputs, never an outbound path."""
    active = state['run_draft']
    if active.get('planning_mode') != 'return':
        return deepcopy(active)
    run = deepcopy(state.get('run_setup'))
    if not run:
        raise ValueError('Review the current run inputs before preparing return')
    run['settings'] = deepcopy(active['settings'])
    return run
