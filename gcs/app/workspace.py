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
from .settings import defaults, validate_settings, effective_settings, FIELDS
from .imports import point_map


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()




class Workspace:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.path = self.directory / 'workspace.json'
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'map': None, 'draft': None, 'approval': None}
        if 'planning_mode' not in self.state and self.path.exists():
            backup = self.directory / ('workspace-before-competition-run-' + str(uuid.uuid4()) + '.json')
            backup.write_bytes(self.path.read_bytes())
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

        if self.state.get('workspace_version', 1) < 2:
            affected = [d for d in [self.state.get('draft'), *self.state.get('tasks', {}).values()] if d and d.get('planner_task')]
            affected.extend(self.state.get('course', {}).values())
            if affected:
                backup = self.directory / ('workspace-before-general-course-' + str(uuid.uuid4()) + '.json')
                backup.write_bytes(self.path.read_bytes())
                for draft in affected:
                    draft['geometry_version'] = 2
                    draft['course_confirmed'] = False
                    draft['legacy_assignments'] = True
                    if draft.get('planner_task'):
                        draft.setdefault('attempt', {'mode': 'full', 'start_source': 'live'})
                for config in self.state.get('course',{}).values():
                    config.pop('attempt',None)
                if (self.state.get('draft') or {}).get('planner_task'):
                    self.state['approval'] = None
                self.state['migration_notice'] = 'Task assignments and saved routes retained for review. Confirm geometry and regenerate before approving.'
            self.state['workspace_version'] = 2
            self.save()

        if 'game_settings' not in self.state:
            if self.path.exists():
                backup = self.directory / ('workspace-before-course-settings-' + str(uuid.uuid4()) + '.json')
                backup.write_bytes(self.path.read_bytes())
            settings = defaults(self.state.get('draft'))
            for task, draft in self.state.get('tasks', {}).items():
                if task in ('gate', 'slalom', 'channel'):
                    override = {key: deepcopy(draft[key]) for key in FIELDS if key in draft and draft[key] != settings[key]}
                    if override:
                        settings['task_overrides'][task] = override
            self.state['game_settings'] = settings
            self.save()

        object_map = self.state.get('map')
        if object_map and object_map['schema_version'] == 3 and any(
                obj['type'] != 'point' for obj in [*object_map['buoys'], *object_map.get('obstacles', [])]):
            backup = self.directory / ('workspace-before-point-objects-' + str(uuid.uuid4()) + '.json')
            backup.write_bytes(self.path.read_bytes())
            self.state['map'] = point_map(object_map)
            self.state['approval'] = None
            for draft in [self.state.get('draft'), *self.state.get('tasks', {}).values(), *self.state.get('course', {}).values()]:
                if draft:
                    draft['sizes_confirmed'] = False
                    draft['course_confirmed'] = False
                    draft.pop('generation_setup_sha256', None)
            self.state['migration_notice'] = 'Saved routes and original observations retained. Objects now use GPS points. Review total centre-based hard/soft distances, then regenerate and approve.'
            self.save()

        if 'planning_mode' not in self.state:
            self.state.update(planning_mode='single', run_draft=None, run_consumed=False)
            self.save()

        if self.state.get('planning_mode') == 'competition':
            # Process restart never restores execution authority for a run.
            self.state['run_consumed'] = True
            self.save()

    def active_draft(self):
        return self.state.get('run_draft') if self.state.get('planning_mode') == 'competition' else self.state.get('draft')

    def publish_run(self, draft):
        with self.lock:
            self.state.update(run_draft=deepcopy(draft), approval=None, run_consumed=False)
            self.save()
            return self.read()

    def consume_run(self):
        with self.lock:
            if self.state.get('planning_mode') == 'competition':
                self.state['run_consumed'] = True
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
            for config in updated.get('course', {}).values():
                if isinstance(config,dict):
                    for key in ('planning_notice','attempt','derived_sections','excluded_sections','partial_attempt','route_sections','generation_errors','generation_setup_sha256','start','waypoints'):
                        config.pop(key,None)
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
                updated.update(tasks={},course={},draft=None,selected_task=None,run_draft=None,run_consumed=False,planning_mode='single')
                settings=updated.get('game_settings',{})
                for value in [settings,*settings.get('task_overrides',{}).values()]:
                    if value.get('tower_avoidance'):
                        value['tower_avoidance']['overrides']={}
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
            if (updated.get('draft') or {}).get('planner_task') and (updated.get('course') or updated['draft'].get('geometry_version')==2):
                updated.setdefault('course', {})
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
            if 'game_settings' in data:
                updated['game_settings'] = validate_settings(data['game_settings'])
                updated['settings_configured'] = True
                # Keep saved waypoint data, but revoke its authority and require
                # new generation with the changed settings.
                for task, config in updated.get('course', {}).items():
                    config.update(effective_settings(updated['game_settings'], task))
                    config['course_confirmed'] = False
            if updated.get('settings_configured'):
                for saved in [*updated['tasks'].values(), updated.get('draft')]:
                    if saved:
                        saved.update(effective_settings(updated['game_settings'], saved.get('planner_task')))
                        if 'game_settings' in data:
                            saved['course_confirmed'] = False
                for task, config in updated.get('course', {}).items():
                    config.update(effective_settings(updated['game_settings'], task))
                if (updated.get('draft') or {}).get('planner_task'):
                    updated['draft']['course_revision'] = sha({'map': updated['map'], 'course': updated.get('course', {})})
                    updated['tasks'][updated['draft']['planner_task']] = deepcopy(updated['draft'])
            if 'planning_mode' in data:
                if data['planning_mode'] not in ('single', 'competition'):
                    raise ValueError('planning_mode must be single or competition')
                updated['planning_mode'] = data['planning_mode']
            if 'run_draft' in data:
                if not isinstance(data['run_draft'], dict):
                    raise ValueError('run_draft must be an object')
                updated['run_draft'] = deepcopy(data['run_draft'])
            changed = any(updated.get(k) != self.state.get(k) for k in ('map', 'course', 'game_settings'))
            if changed and updated.get('run_draft'):
                updated['run_draft'].pop('generation_identity', None)
                updated['run_draft'].pop('review_geometry', None)
                updated['run_draft']['waypoints'] = []
                if updated.get('map') != self.state.get('map'):
                    updated['run_draft']['sizes_confirmed'] = False
                    for config in updated['run_draft'].get('task_setup', {}).values():
                        config['sizes_confirmed'] = False
                        config['course_confirmed'] = False
            # A stale browser must not restore the former inside-channel finish.
            # Allow incomplete assignments to be edited; enforce the finish rule
            # as soon as their geometry can be resolved.
            current=updated.get('draft') or {}
            if current.get('planner_task')=='channel' and current.get('geometry_version')==2 and updated.get('map'):
                from shared.task_geometry import resolve_geometry
                try:
                    resolve_geometry(updated['map'],current)
                except (ValueError,KeyError,TypeError) as error:
                    if str(error).startswith('Channel finish must be beyond'):
                        raise ValueError(str(error)) from error
            json.dumps(updated, allow_nan=False)
            updated.pop('migration_notice', None)
            self.state = updated
            self.save()
            return self.read()

    def validate(self):
        with self.lock:
            if not self.state['map'] or not self.active_draft():
                raise ValueError('import map and create route first')
            draft = self.active_draft()
            if self.state.get('planning_mode') == 'competition':
                if self.state.get('run_consumed'):
                    return {'valid': False, 'errors': [{'reason': 'Run started, interrupted or GCS restarted: Generate and approve a new complete run', 'location': None}]}
                from shared.competition import validate_run
                return validate_run(self.state['map'], draft)
            if draft.get('planner_task') and draft.get('course_revision') != sha({'map': self.state['map'], 'course': self.state.get('course')}):
                return {'valid': False, 'errors': [{'reason': 'course changed: review assignments and regenerate', 'location': None}]}
            if draft.get('geometry_version')==2 and not draft.get('attempt',{}).get('captured_at'):
                return {'valid':False,'errors':[{'reason':'Generate a fresh attempt before validation and approval','location':None}]}
            if draft.get('geometry_version')==2:
                from shared.task_geometry import setup_identity
                if draft.get('generation_setup_sha256')!=setup_identity(self.state['map'],draft) or draft.get('attempt',{}).get('start_snapshot')!=draft['start']:
                    return {'valid':False,'errors':[{'reason':'Task setup or attempt start changed: regenerate and review the new attempt','location':None}]}
            return validate_route(self.state['map'], draft)

    def approve(self):
        with self.lock:
            result = self.validate()
            if not result['valid']:
                raise ValueError(json.dumps(result))
            inputs = deepcopy({'map': self.state['map'], 'draft': self.active_draft(), 'planning_mode': self.state['planning_mode']})
            if self.state['planning_mode'] == 'single':
                inputs.pop('planning_mode')
            revision = sha(inputs)
            approval_id = str(uuid.uuid4())
            draft = inputs['draft']
            mission = {'mission_id': approval_id, 'waypoints': draft['waypoints'], 'speed_m_s': draft['speed_m_s'],
                       'finish_radius_m': draft['finish_radius_m'], 'finish_speed_m_s': 0.2, 'finish_settle_s': 5,
                       'timeout_s': draft['execution_budget_s'] if self.state['planning_mode'] == 'competition' else 300, 'max_start_distance_m': 100}
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
            if self.state.get('planning_mode') == 'competition' and self.state.get('run_consumed'):
                raise ValueError('Run already started or interrupted: Generate and approve a new complete run')
            approval = self.state['approval']
            if approval is None:
                raise ValueError('current draft has no approval')
            if (self.active_draft().get('planner_task') or self.state.get('planning_mode') == 'competition') and not self.validate()['valid']:
                raise ValueError('course changed; regenerate, review and approve again')
            inputs = {'map': self.state['map'], 'draft': self.active_draft()}
            if self.state.get('planning_mode') == 'competition':
                inputs['planning_mode'] = 'competition'
            if sha(inputs) != approval['envelope']['revision_sha256']:
                raise ValueError('approved inputs changed; approve again')
            return deepcopy(approval)
