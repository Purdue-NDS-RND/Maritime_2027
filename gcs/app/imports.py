"""GPS point imports. Original observations are immutable workspace inputs."""
import csv
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from shared.geometry import finite
from shared.object_map import validate_map

# Visible defaults are conservative guesses, requiring operator confirmation.
SIZE_DEFAULTS = {'buoy': .25, 'detector': .5, 'unknown': .5}


def import_points(content, format='json'):
    raw = list(csv.DictReader(io.StringIO(content))) if format == 'csv' else json.loads(content)
    if isinstance(raw, dict) and 'schema_version' in raw:
        return validate_map(raw)
    rows = raw.get('points') if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise ValueError('GPS import needs a nonempty points list')
    objects = []
    for i, row in enumerate(rows):
        kind = row.get('object_type') or row.get('type') or 'unknown'
        radius = row.get('radius_m')
        objects.append({'id': str(row.get('id') or f'point_{i+1}'), 'type': 'cylinder',
                        'object_type': kind, 'category': row.get('color') or row.get('category') or 'unknown',
                        'centre': {'latitude': float(row['latitude']), 'longitude': float(row['longitude'])},
                        'radius_m': finite(float(radius)) if radius not in (None, '') else SIZE_DEFAULTS.get(kind,.5),
                        'height_m': float(row.get('height_m') or 1), 'size_assumed': radius in (None,'')})
    return validate_map({'schema_version': 3, 'source': 'live', 'captured_at': datetime.now(timezone.utc).isoformat(),
                         'geographic_reference': deepcopy(objects[0]['centre']), 'buoys': objects,
                         'obstacles': [], 'stations': [], 'size_defaults_m': SIZE_DEFAULTS, 'imported_points': deepcopy(rows)})
