"""Static point-route validation with an operator-selected total buffer."""
import math
from .geometry import finite, segment_distance, to_local


def validate_route(object_map, draft):
    errors = []
    def reject(reason, location=None):
        errors.append({'reason': reason, 'location': location})
    if object_map.get('schema_version') != 1:
        reject('unsupported object map version')
    if not isinstance(object_map.get('alignment'), dict) or object_map['alignment'].get('outcome') != 'passed':
        reject('scene geographic alignment is unverified')
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
    start = to_local(draft['start'], reference)
    route = [start, *points]
    for index, (a,b) in enumerate(zip(route, route[1:])):
        for buoy in object_map['buoys']:
            centre = to_local(buoy['centre'], reference)
            gap = segment_distance(centre, a, b) - buoy['radius_m'] - radius
            if gap < 0:
                reject(f'leg {index} violates clearance buffer at {buoy["id"]} by {-gap:.3f} m', list(centre))
    finish = to_local(draft['finish'], reference)
    if not points or math.dist(points[-1], finish) > 0.001:
        reject('final waypoint must equal the selected finish centre', list(finish))
    finish_radius = finite(draft['finish_radius_m'])
    if not 0 < finish_radius <= 1:
        reject('finish radius must be in (0, 1] m')
    for buoy in object_map['buoys']:
        centre = to_local(buoy['centre'], reference)
        if math.dist(finish,centre) < radius + buoy['radius_m'] + finish_radius:
            reject('finish area violates clearance at ' + buoy['id'], list(centre))
    buoy_ids = {b['id']: b for b in object_map['buoys']}
    seen = set()
    passages = draft.get('passages', [])
    if not isinstance(passages, list):
        raise ValueError('passages must be an ordered list')
    for passage in passages:
        if not isinstance(passage.get('id'), str) or passage['id'] in seen:
            raise ValueError('unique passage IDs required')
        seen.add(passage['id'])
        if passage.get('kind') == 'gate':
            if passage.get('red') not in buoy_ids or passage.get('green') not in buoy_ids or passage['red'] == passage['green']:
                reject('gate must identify two distinct mapped buoys')
        elif passage.get('kind') == 'turn':
            if passage.get('buoy') not in buoy_ids or passage.get('side') not in ('left','right'):
                reject('turn must identify a mapped buoy and passing side')
        else:
            reject('unsupported course passage kind')
    crossing_order = []
    for passage in passages:
        if passage.get('kind') == 'gate' and passage.get('red') in buoy_ids and passage.get('green') in buoy_ids:
            red = to_local(buoy_ids[passage['red']]['centre'], reference)
            green = to_local(buoy_ids[passage['green']]['centre'], reference)
            if abs(red[0]-green[0]) > .10:
                reject('this fixed-course validator requires a gate perpendicular to +X')
                continue
            plane = (red[0]+green[0])/2
            low = min(red[1],green[1]) + max(buoy_ids[passage['red']]['radius_m'],buoy_ids[passage['green']]['radius_m']) + radius
            high = max(red[1],green[1]) - max(buoy_ids[passage['red']]['radius_m'],buoy_ids[passage['green']]['radius_m']) - radius
        elif passage.get('kind') == 'turn' and passage.get('buoy') in buoy_ids:
            centre = to_local(buoy_ids[passage['buoy']]['centre'], reference)
            plane = centre[0]
            offset = radius + buoy_ids[passage['buoy']]['radius_m']
            low, high = ((centre[1]+offset, math.inf) if passage.get('side')=='left'
                         else (-math.inf, centre[1]-offset))
        else:
            continue
        crossings = []
        for leg,(a,b) in enumerate(zip(route,route[1:])):
            if a[0] <= plane < b[0]:
                f = (plane-a[0])/(b[0]-a[0]); y = a[1]+f*(b[1]-a[1])
                crossings.append(leg+f)
                if not low <= y <= high:
                    reject('passage violates opening/side: '+passage['id'], [plane,y])
            if b[0] <= plane < a[0]:
                reject('reverse passage is unsupported: '+passage['id'], [plane,a[1]])
        if len(crossings) != 1:
            reject('route must cross passage once: '+passage['id'], [plane,0])
        else:
            crossing_order.append(crossings[0])
    if crossing_order != sorted(crossing_order):
        reject('route crosses passages in the wrong order')
    task = draft.get('task', 'custom')
    if task in ('gate_only','slalom'):
        kinds = [p.get('kind') for p in passages]
        expected = ['gate'] if task == 'gate_only' else ['gate','turn','turn','turn','turn','gate']
        if kinds != expected:
            reject('select the complete ordered '+task+' passage list')
    elif task != 'custom':
        reject('unsupported course task')
    return {'valid': not errors, 'errors': errors, 'swept_radius_m': radius,
            'bound_scope': 'operator-selected total buffer; hull size and tracking error are not inferred'}
