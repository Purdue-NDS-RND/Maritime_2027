"""Versioned observation/assignment interchange, with no execution inputs."""
from copy import deepcopy
import json
from .imports import import_points, point_map
from .course_profile import identity
from .course_compiler import validate_hints, validate_assignments

FORMAT = 'maritime-reviewed-course'


def load_course(content, format='json'):
    raw = json.loads(content) if format == 'json' else None
    if not isinstance(raw, dict) or raw.get('format') != FORMAT:
        object_map = import_points(content, format)
        return {'map': object_map, 'original_map': deepcopy(object_map), 'hints': {}, 'assignments': {}}
    if raw.get('version') != 1 or raw.get('profile') != identity():
        raise ValueError('Unsupported course file or profile version')
    object_map = point_map(raw['cleaned_map'])
    original = point_map(raw['original_observations'])
    hints = validate_hints(object_map, raw.get('hints', {}))
    assignments = validate_assignments(object_map, raw.get('selected_assignments', {}), hints)
    return {'map': object_map, 'original_map': original, 'hints': hints,
            'assignments': {task: {'roles': roles, 'status': 'review_required'} for task, roles in assignments.items()}}


def save_course(state):
    if not state['map']:
        raise ValueError('Import a map first')
    return {'format': FORMAT, 'version': 1, 'profile': identity(),
            'original_observations': deepcopy(state['original_map']), 'cleaned_map': deepcopy(state['map']),
            'hints': deepcopy(state['compiler_hints']),
            'selected_assignments': {task: deepcopy(value['roles']) for task, value in state['course_assignments'].items()}}
