"""Validate version 1 buoy maps and version 2 fixed-object maps."""
import re
from .geometry import finite, to_local


def validate_map(data):
    if type(data['schema_version']) is not int or data['schema_version'] not in (1,2) or not data['scene_id'] or not data['run_id']:
        raise ValueError('unsupported or unidentified map')
    reference = data['geographic_reference']
    to_local(reference, reference)
    if not isinstance(data['buoys'], list) or not data['buoys']:
        raise ValueError('map must contain buoys')
    obstacles = data['obstacles'] if data['schema_version'] == 2 else data.get('obstacles', [])
    if not isinstance(obstacles, list) or (data['schema_version'] == 1 and obstacles):
        raise ValueError('unsupported obstacles')
    names = set()
    for obj in [*data['buoys'], *obstacles]:
        if not isinstance(obj['id'], str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', obj['id']):
            raise ValueError('unsupported object ID')
        if obj['id'] in names:
            raise ValueError('duplicate object identity')
        names.add(obj['id'])
        to_local(obj['centre'], reference)
        if data['schema_version'] == 2 and not 0 < finite(obj['height_m']) < 10:
            raise ValueError('invalid object height')
        if obj['type'] == 'cylinder':
            if not 0 < finite(obj['radius_m']) < 10:
                raise ValueError('unsupported cylinder geometry')
        elif obj['type'] == 'polygon' and data['schema_version'] == 2 and obj in obstacles:
            vertices = obj['footprint']
            if not isinstance(vertices, list) or not 3 <= len(vertices) <= 32:
                raise ValueError('polygon needs 3..32 vertices')
            points = [to_local(p,reference) for p in vertices]
            # Strict convexity and consistent winding, including all non-edge vertices,
            # rejects duplicate, collinear, concave and self-intersecting footprints.
            signs = []
            for i,a in enumerate(points):
                b = points[(i+1)%len(points)]
                for j,c in enumerate(points):
                    if j not in (i,(i+1)%len(points)):
                        cross = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                        signs.append(cross)
            if not (all(v>1e-9 for v in signs) or all(v< -1e-9 for v in signs)):
                raise ValueError('footprint must be a nondegenerate convex polygon')
        else:
            raise ValueError('unsupported object geometry')
    if data['schema_version'] == 2:
        to_local(data['start_pose']['position'],reference)
        if not 0 <= finite(data['start_pose']['heading_deg']) < 360:
            raise ValueError('invalid start heading')
        station_ids = set()
        for station in data['stations']:
            if not isinstance(station['id'],str) or station['id'] in station_ids or not isinstance(station['label'],str):
                raise ValueError('invalid station annotation')
            station_ids.add(station['id'])
            to_local(station['position'],reference)
            if 'radius_m' in station and (finite(station['radius_m']) <= 0 or station.get('blocking') is not False):
                raise ValueError('station overlays must be positive and nonblocking')
    return data
