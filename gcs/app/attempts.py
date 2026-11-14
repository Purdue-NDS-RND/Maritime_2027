"""Capture start authorization independently of persistent task geometry."""
from copy import deepcopy
from datetime import datetime, timezone
import math
from shared.geometry import to_local
from shared.task_geometry import remaining_suggestion


def capture_start(draft, status=None):
    result = deepcopy(draft)
    attempt = result.setdefault('attempt', {'mode': 'full', 'start_source': 'live'})
    attempt.pop('initial_progress',None)
    attempt.pop('started_inside_channel',None)
    source = attempt.get('start_source', 'live')
    if source == 'live':
        if not status or not status.get('position') or any(
                not isinstance(status.get(key), (int, float)) or not math.isfinite(status[key]) or not 0 <= status[key] <= 3
                for key in ('position_age_s', 'heartbeat_age_s')):
            raise ValueError('Live boat start requires position and heartbeat ages of at most three seconds. Select Manual start explicitly for offline planning.')
        result['start'] = deepcopy(status['position'])
        attempt['position_age_s'] = status['position_age_s']
        attempt['heartbeat_age_s'] = status['heartbeat_age_s']
    elif source != 'manual':
        raise ValueError('select Live boat or Manual start')
    attempt['start_source'] = source
    attempt['captured_at'] = datetime.now(timezone.utc).isoformat()
    attempt['start_snapshot'] = deepcopy(result['start'])
    return result


def check_remaining_snapshot(object_map, draft):
    attempt = draft.get('attempt', {})
    if attempt.get('mode') == 'remaining':
        confirmed = attempt.get('selection_position')
        if not attempt.get('selection_confirmed') or not confirmed:
            raise ValueError('Confirm or change the first remaining section before generation.')
        ref = object_map['geographic_reference']
        if math.dist(to_local(confirmed, ref), to_local(draft['start'], ref)) > 1:
            raise ValueError('Boat moved more than 1 m since remaining-section review. Review and confirm the selection again.')


def suggest_remaining(object_map, draft):
    return {'first_section': remaining_suggestion(object_map, draft), 'selection_confirmed': False,
            'selection_position': deepcopy(draft['start'])}
