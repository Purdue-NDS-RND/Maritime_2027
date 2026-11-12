"""Tower zones measured from GPS points, or legacy physical surfaces."""
from .geometry import finite


def tower_policy(draft):
    policy = draft.get('tower_avoidance')
    if policy is None:
        return None
    if not isinstance(policy, dict):
        raise ValueError('tower avoidance must be an object')
    def distances(value):
        hard, soft = finite(value['hard_m']), finite(value['soft_m'])
        if hard < 0 or soft < hard:
            raise ValueError('tower distances require 0 <= hard exclusion <= soft avoidance')
        return {'hard_m': hard, 'soft_m': soft}
    result = distances(policy)
    result['strength'] = finite(policy.get('strength', 10))
    if not 0 <= result['strength'] <= 100:
        raise ValueError('tower avoidance strength must be between 0 and 100')
    overrides = policy.get('overrides', {})
    if not isinstance(overrides, dict) or any(not isinstance(key, str) for key in overrides):
        raise ValueError('tower overrides must be keyed by object ID')
    result['overrides'] = {key: distances(value) for key, value in overrides.items()}
    return result


def zones(obj, draft, policy=None):
    required = finite(draft['clearance_m'])
    if obj.get('object_type') != 'detector':
        return required, finite(draft.get('preferred_buffer_m', required))
    policy = tower_policy(draft) if policy is None else policy
    if policy is None:
        return required, finite(draft.get('preferred_buffer_m', required))
    value = policy['overrides'].get(obj['id'], policy)
    return value['hard_m'], value['soft_m']
