"""GPS point imports. Original observations are immutable workspace inputs."""
import csv
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from shared.object_map import validate_map


def point_map(data):
    """Use GPS centres for live planning; retain native simulator formats."""
    result = deepcopy(validate_map(data))
    if result['schema_version'] == 3:
        for obj in [*result['buoys'], *result.get('obstacles', [])]:
            obj['type'] = 'point'
            obj['object_type'] = obj.get('object_type') or 'unknown'
            for key in ('radius_m', 'height_m', 'footprint', 'size_assumed'):
                obj.pop(key, None)
        result.pop('size_defaults_m', None)
    return validate_map(result)


def import_points(content, format='json'):
    raw = list(csv.DictReader(io.StringIO(content))) if format == 'csv' else json.loads(content)
    if isinstance(raw, dict) and 'schema_version' in raw:
        result = point_map(raw)
        legacy_import_time = result.get('schema_version') == 3 and 'imported_points' in result and 'imported_at' not in result and 'survey_time_source' not in result
        result['survey_time_source'] = result.get('survey_time_source') or ('source' if result.get('captured_at') and not legacy_import_time else 'unknown')
        result['imported_at'] = datetime.now(timezone.utc).isoformat()
        return result
    rows = raw.get('points') if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise ValueError('GPS import needs a nonempty points list')
    objects = []
    for i, row in enumerate(rows):
        kind = str(row.get('object_type') or row.get('type') or 'unknown').strip().lower() or 'unknown'
        objects.append({'id': str(row.get('id') or f'point_{i+1}'), 'type': 'point',
                        'object_type': kind, 'category': row.get('color') or row.get('category') or 'unknown',
                        'centre': {'latitude': float(row['latitude']), 'longitude': float(row['longitude'])}})
    return validate_map({'schema_version': 3, 'source': 'live', 'survey_time_source': 'source' if isinstance(raw, dict) and raw.get('captured_at') else 'unknown', 'captured_at': raw.get('captured_at') if isinstance(raw, dict) else None,
                         'imported_at': datetime.now(timezone.utc).isoformat(),
                         'geographic_reference': deepcopy(raw.get('geographic_reference') or objects[0]['centre']) if isinstance(raw, dict) else deepcopy(objects[0]['centre']), 'buoys': objects,
                         'obstacles': [], 'stations': [], 'imported_points': deepcopy(rows)})
