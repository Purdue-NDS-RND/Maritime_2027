"""Durable drafts and immutable approved revisions."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import uuid
from shared.clearance import validate_route
from shared.object_map import validate_map


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()




class Workspace:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.path = self.directory / 'workspace.json'
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'map': None, 'draft': None, 'approval': None}
        if self.state.get('map') and 'original_map' not in self.state:
            self.state['original_map'] = deepcopy(self.state['map'])
        # Old clearance values excluded the hull and tracking allowance. Never
        # reinterpret them as a total buffer or retain the old authorization.
        if self.state.get('draft') and 'navigation_profile_id' in self.state['draft']:
            backup = self.directory / ('workspace-before-point-buffer-' + str(uuid.uuid4()) + '.json')
            backup.write_bytes(self.path.read_bytes())
            self.state['draft'].pop('navigation_profile_id')
            self.state['draft'].pop('start_heading_deg', None)
            self.state['draft']['clearance_m'] = None
            self.state['approval'] = None
            self.state['migration_notice'] = 'Route retained. Set a total clearance buffer, then validate and approve again.'
            self.save()

    def save(self):
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, indent=2, allow_nan=False) + '\n')
        temp.replace(self.path)

    def read(self):
        with self.lock:
            return deepcopy(self.state)

    def edit(self, data):
        with self.lock:
            # Any edit revokes approval, even changing back to old values.
            if data.get('new_import') and self.state.get('map'):
                backup=self.directory/('workspace-before-map-import-'+str(uuid.uuid4())+'.json')
                backup.write_text(json.dumps(self.state,indent=2,allow_nan=False)+'\n')
            updated = deepcopy(self.state)
            updated['approval'] = None
            updated.setdefault('tasks', {})
            previous = updated.get('draft') or {}
            previous_task = previous.get('planner_task') or ('manual' if previous.get('task') == 'custom' else None)
            if previous_task:
                updated['tasks'][previous_task] = deepcopy(previous)
            for key in ('course', 'selected_task'):
                if key in data:
                    updated[key] = deepcopy(data[key])
            if 'course' in data and (not isinstance(data['course'], dict) or any(k not in ('gate','slalom','channel') or not isinstance(v,dict) for k,v in data['course'].items())):
                raise ValueError('course must contain gate/slalom/channel configurations')
            if 'selected_task' in data and data['selected_task'] not in ('gate','slalom','channel','manual'):
                raise ValueError('unsupported selected task')
            if 'selected_task' in data:
                updated['draft'] = deepcopy(updated['tasks'].get(data['selected_task']))
            if 'course' in data or 'map' in data:
                for saved in updated['tasks'].values():
                    saved['course_confirmed'] = False
                if updated.get('draft'):
                    updated['draft']['course_confirmed'] = False
            if data.get('new_import'):
                # Previous course/drafts remain in the import backup, not attached
                # to unrelated object identities in the newly imported map.
                updated.update(tasks={},course={},draft=None,selected_task=None)
            if 'map' in data:
                updated['map'] = deepcopy(validate_map(data['map']))
                for config in updated.get('course', {}).values():
                    config['course_confirmed'] = False
                    config['sizes_confirmed'] = False
                if 'original_map' not in updated or data.get('new_import'):
                    updated['original_map'] = deepcopy(updated['map'])
            if 'draft' in data:
                if not isinstance(data['draft'], dict):
                    raise ValueError('draft must be an object')
                if 'navigation_profile_id' in data['draft']:
                    raise ValueError('legacy profile-based draft: reload and choose a total clearance buffer')
                # Validate JSON finiteness before persistence.
                json.dumps(data['draft'], allow_nan=False)
                updated['draft'] = deepcopy(data['draft'])
                if updated['draft'].get('planner_task'):
                    updated['tasks'][updated['draft']['planner_task']] = deepcopy(updated['draft'])
                elif updated['draft'].get('task') == 'custom':
                    updated['tasks']['manual'] = deepcopy(updated['draft'])
            if (updated.get('draft') or {}).get('planner_task') and updated.get('course'):
                task = updated['draft']['planner_task']
                config = updated['course'].get(task, {})
                updated['draft'].update(deepcopy(config))
                updated['draft']['course_revision'] = sha({'map': updated['map'], 'course': updated['course']})
                updated['tasks'][task] = deepcopy(updated['draft'])
            if 'map' in data:
                for saved in [*updated['tasks'].values(), updated.get('draft')]:
                    if saved:
                        saved['sizes_confirmed'] = False
                        saved['course_confirmed'] = False
            json.dumps(updated, allow_nan=False)
            updated.pop('migration_notice', None)
            self.state = updated
            self.save()
            return self.read()

    def validate(self):
        with self.lock:
            if not self.state['map'] or not self.state['draft']:
                raise ValueError('import map and create route first')
            draft = self.state['draft']
            if draft.get('planner_task') and draft.get('course_revision') != sha({'map': self.state['map'], 'course': self.state.get('course')}):
                return {'valid': False, 'errors': [{'reason': 'course changed: review assignments and regenerate', 'location': None}]}
            return validate_route(self.state['map'], draft)

    def approve(self):
        with self.lock:
            result = self.validate()
            if not result['valid']:
                raise ValueError(json.dumps(result))
            inputs = {'map': self.state['map'], 'draft': self.state['draft']}
            revision = sha(inputs)
            approval_id = str(uuid.uuid4())
            draft = inputs['draft']
            mission = {'mission_id': approval_id, 'waypoints': draft['waypoints'], 'speed_m_s': draft['speed_m_s'],
                       'finish_radius_m': draft['finish_radius_m'], 'finish_speed_m_s': 0.2, 'finish_settle_s': 5,
                       'timeout_s': 300, 'max_start_distance_m': 100}
            envelope = {'approval_id': approval_id, 'revision_sha256': revision,
                        'mission': mission}
            approval = {'approved_at': datetime.now(timezone.utc).isoformat(), 'inputs': inputs,
                        'validation': result, 'envelope': envelope}
            with (self.directory / (approval_id + '.json')).open('x') as stream:
                json.dump(approval, stream, indent=2, allow_nan=False)
            self.state['approval'] = approval
            self.save()
            return deepcopy(approval)

    def approved(self):
        with self.lock:
            approval = self.state['approval']
            if approval is None:
                raise ValueError('current draft has no approval')
            if self.state['draft'].get('planner_task') and not self.validate()['valid']:
                raise ValueError('course changed; regenerate, review and approve again')
            if sha({'map': self.state['map'], 'draft': self.state['draft']}) != approval['envelope']['revision_sha256']:
                raise ValueError('approved inputs changed; approve again')
            return deepcopy(approval)
