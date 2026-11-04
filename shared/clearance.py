"""Static point-route validation with an operator-selected total buffer."""
import math
from .geometry import finite, segment_distance, to_local, polygon_clearance
from .object_map import validate_map
from .course import validate_course
from .avoidance import tower_policy, zones


def validate_route(object_map, draft, *, transit_finish=False):
    if draft.get('planning_mode') == 'competition':
        from .competition import validate_run
        return validate_run(object_map, draft)
    # Only composite block callers authorize a transit endpoint. An ordinary
    # draft cannot disable its stopped finish by adding a JSON field.
    draft = {**draft, 'transit_finish': transit_finish}
    validate_map(object_map)
    errors = []
    def reject(reason, location=None):
        errors.append({'reason': reason, 'location': location})
    if object_map.get('schema_version') not in (1,2,3):
        reject('unsupported object map version')
    if object_map['schema_version'] != 3 and (not isinstance(object_map.get('alignment'), dict) or object_map['alignment'].get('outcome') != 'passed'):
        reject('scene geographic alignment is unverified')
    if object_map['schema_version']==3 and not draft.get('sizes_confirmed'):
        reject('review the GPS object map and total centre-based buffers before planning')
    reference = object_map['geographic_reference']
    points = [to_local(point, reference) for point in draft['waypoints']]
    if not 1 <= len(points) <= 500:
        reject('route requires 1..500 waypoints')
    speed, clearance = finite(draft['speed_m_s']), finite(draft['clearance_m'])
    if speed <= 0:
        reject('target speed must be positive')
    if clearance < 0:
        reject('total clearance buffer must be nonnegative')
    radius = clearance
    policy = tower_policy(draft)
    start = to_local(draft['start'], reference)
    route = [start, *points]
    obstacles = [*object_map['buoys'], *object_map.get('obstacles', [])]
    def gap_to_object(obj, a, b):
        if obj['type'] in ('point', 'cylinder'):
            return segment_distance(to_local(obj['centre'],reference),a,b)-obj.get('radius_m', 0)
        polygon = [to_local(p,reference) for p in obj['footprint']]
        distance = min(polygon_clearance(polygon,a,0),polygon_clearance(polygon,b,0))
        for c,d in zip(polygon,polygon[1:]+polygon[:1]):
            # Segment intersection, including touching or collinear overlap.
            def cross(p,q,r):
                return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
            if (max(min(a[0],b[0]),min(c[0],d[0])) <= min(max(a[0],b[0]),max(c[0],d[0]))
                    and max(min(a[1],b[1]),min(c[1],d[1])) <= min(max(a[1],b[1]),max(c[1],d[1]))
                    and cross(a,b,c)*cross(a,b,d) <= 0 and cross(c,d,a)*cross(c,d,b) <= 0):
                return -1e-9
            distance = min(distance,segment_distance(c,a,b),segment_distance(d,a,b))
        return distance
    for index, (a,b) in enumerate(zip(route, route[1:])):
        for obj in obstacles:
            gap = gap_to_object(obj,a,b)-zones(obj,draft,policy)[0]
            if gap < -1e-7:
                reject(f'leg {index} violates clearance buffer at {obj["id"]} by {-gap:.3f} m', list(to_local(obj['centre'],reference)))
    finish = to_local(draft['finish'], reference)
    if not points or math.dist(points[-1], finish) > 0.001:
        reject('final waypoint must equal the selected finish centre', list(finish))
    finish_radius = finite(draft['finish_radius_m'])
    if not 0 < finish_radius <= 1:
        reject('finish radius must be in (0, 1] m')
    for obj in obstacles:
        if gap_to_object(obj,finish,finish) < zones(obj,draft,policy)[0] + (0 if draft.get('transit_finish') else finish_radius):
            reject('finish area violates clearance at ' + obj['id'], list(to_local(obj['centre'],reference)))
    course_errors, sections = validate_course(object_map, draft)
    errors.extend(course_errors)
    task = draft.get('task', 'custom')
    if task in ('gate_only','slalom'):
        kinds = [p.get('kind') for p in draft.get('passages', [])]
        expected = ['gate'] if task == 'gate_only' else ['gate','turn','turn','turn','turn','gate']
        if kinds != expected:
            reject('select the complete ordered '+task+' passage list')
    elif task != 'custom':
        reject('unsupported course task')
    return {'tower_shortfalls': [{'leg':i,'object_id':obj['id'],'clearance_m':gap_to_object(obj,a,b),'preferred_m':zones(obj,draft,policy)[1]} for i,(a,b) in enumerate(zip(route,route[1:])) for obj in obstacles if policy is not None and obj.get('object_type')=='detector' and gap_to_object(obj,a,b)<zones(obj,draft,policy)[1]], 'preferred_shortfalls': sections, 'map_verification': 'live / unverified' if object_map['schema_version']==3 else 'simulator alignment passed', 'valid': not errors, 'errors': errors, 'swept_radius_m': radius,
            'bound_scope': 'operator-selected total buffer; hull size and tracking error are not inferred'}
