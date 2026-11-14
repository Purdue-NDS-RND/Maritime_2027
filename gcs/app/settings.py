"""Shared course settings with explicit task and tower overrides."""
from copy import deepcopy
from shared.geometry import finite
from shared.avoidance import tower_policy

FIELDS = ('speed_m_s', 'clearance_m', 'preferred_buffer_m', 'tower_avoidance')
TASKS = ('gate', 'slalom', 'channel')


def defaults(draft=None):
    draft = draft or {}
    required = draft.get('clearance_m')
    required = 1.8 if required is None else required
    return {'version': 1, 'speed_m_s': draft.get('speed_m_s', .5), 'clearance_m': required,
            'preferred_buffer_m': draft.get('preferred_buffer_m', required),
            'tower_avoidance': deepcopy(draft.get('tower_avoidance') or
                {'hard_m': required, 'soft_m': max(10, required), 'strength': 10, 'overrides': {}}),
            'task_overrides': {}}


def validate_settings(settings):
    if not isinstance(settings, dict) or settings.get('version') != 1:
        raise ValueError('unsupported course settings version')
    result = deepcopy(settings)
    overrides = result.get('task_overrides', {})
    if not isinstance(overrides, dict) or any(task not in TASKS or not isinstance(value, dict) or any(k not in FIELDS for k in value) for task, value in overrides.items()):
        raise ValueError('invalid task settings overrides')
    for task in (None, *TASKS):
        value = {**result, **overrides.get(task, {})}
        speed = finite(value['speed_m_s'])
        hard, soft = finite(value['clearance_m']), finite(value['preferred_buffer_m'])
        if speed <= 0 or hard < 0 or soft < hard:
            raise ValueError('settings require positive speed and 0 <= required buffer <= preferred buffer')
        if tower_policy(value) is None:
            raise ValueError('configure tower hard and soft distances')
    return result


def effective_settings(settings, task=None):
    settings = validate_settings(settings)
    return deepcopy({key: settings.get('task_overrides', {}).get(task, {}).get(key, settings[key]) for key in FIELDS})
