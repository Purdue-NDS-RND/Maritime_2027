"""Durable drafts and immutable approved revisions."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import threading
import uuid
from shared.clearance import validate_route
from shared.geometry import finite, to_local


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate_map(data):
    if data['schema_version'] != 1 or not data['scene_id'] or not data['run_id']:
        raise ValueError('unsupported or unidentified map')
    if not isinstance(data['buoys'], list) or not data['buoys']:
        raise ValueError('map must contain buoys')
    names = set()
    for buoy in data['buoys']:
        if not isinstance(buoy['id'], str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', buoy['id']):
            raise ValueError('unsupported buoy ID')
        if buoy['id'] in names:
            raise ValueError('duplicate buoy identity')
        names.add(buoy['id'])
        to_local(buoy['centre'], data['geographic_reference'])
        if buoy['type'] != 'cylinder' or not 0 < finite(buoy['radius_m']) < 10:
            raise ValueError('unsupported buoy geometry')
    return data


class Workspace:
    def __init__(self, directory, profiles):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.profiles = Path(profiles)
        self.lock = threading.RLock()
        self.path = self.directory / 'workspace.json'
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'map': None, 'draft': None, 'approval': None}

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
            updated = deepcopy(self.state)
            updated['approval'] = None
            if 'map' in data:
                updated['map'] = validate_map(data['map'])
            if 'draft' in data:
                if not isinstance(data['draft'], dict):
                    raise ValueError('draft must be an object')
                # Validate JSON finiteness before persistence.
                json.dumps(data['draft'], allow_nan=False)
                updated['draft'] = data['draft']
            self.state = updated
            self.save()
            return self.read()

    def profile(self):
        name = self.state['draft']['navigation_profile_id']
        if not isinstance(name, str) or Path(name).name != name or not name:
            raise ValueError('select a measured navigation profile')
        profile = json.loads((self.profiles / (name + '.json')).read_text())
        if profile['id'] != name:
            raise ValueError('profile identity mismatch')
        return profile

    def validate(self):
        with self.lock:
            if not self.state['map'] or not self.state['draft']:
                raise ValueError('import map and create route first')
            return validate_route(self.state['map'], self.state['draft'], self.profile())

    def approve(self):
        with self.lock:
            result = self.validate()
            if not result['valid']:
                raise ValueError(json.dumps(result))
            inputs = {'map': self.state['map'], 'draft': self.state['draft'], 'profile': self.profile()}
            revision = sha(inputs)
            approval_id = str(uuid.uuid4())
            draft = inputs['draft']
            mission = {'mission_id': approval_id, 'waypoints': draft['waypoints'], 'speed_m_s': draft['speed_m_s'],
                       'finish_radius_m': draft['finish_radius_m'], 'finish_speed_m_s': 0.2, 'finish_settle_s': 5,
                       'timeout_s': 300, 'max_start_distance_m': inputs['profile']['maximum_leg_m'] + 0.10}
            envelope = {'approval_id': approval_id, 'revision_sha256': revision,
                        'navigation_profile_id': draft['navigation_profile_id'], 'mission': mission}
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
            if sha({'map': self.state['map'], 'draft': self.state['draft'], 'profile': self.profile()}) != approval['envelope']['revision_sha256']:
                raise ValueError('approved inputs/profile changed; approve again')
            return deepcopy(approval)
