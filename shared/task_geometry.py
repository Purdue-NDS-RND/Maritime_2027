"""Version 2 reviewed task geometry; coordinates stay in the map reference frame."""
from copy import deepcopy
import math
import hashlib
import json
from .geometry import to_local, to_gps
from .course import inside, intersects, polygon_valid, contained, dot, sub


def unit(delta):
    length = math.hypot(*delta)
    if length < 1e-6:
        raise ValueError('ambiguous local travel direction: correct anchors or set a direction override')
    return tuple(v / length for v in delta)


def chain_data(points):
    distances = [0.0]
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        if length < 1e-6:
            raise ValueError('channel chain has duplicate adjacent points')
        distances.append(distances[-1] + length)
    if len(points) < 2:
        raise ValueError('each channel chain needs at least two ordered objects')
    return [v / distances[-1] for v in distances]


def merge_fractions(values):
    # GPS round trips can split an identical geometric fraction by a few ulps.
    # Coalesce only numerical duplicates, retaining real uneven sections.
    result=[]
    for value in sorted(values):
        if result and value-result[-1]<=1e-8:
            result[-1]=(result[-1]+value)/2
        else:
            result.append(value)
    return result


def interpolate(points, fractions, fraction):
    for i in range(len(points) - 1):
        if fraction <= fractions[i + 1] + 1e-9:
            t = (fraction - fractions[i]) / (fractions[i + 1] - fractions[i])
            return tuple(a + t * (b - a) for a, b in zip(points[i], points[i + 1]))
    return points[-1]


def segment_within(a, b, polygon):
    """Check every interval cut by polygon edges, including concave notches."""
    if not inside(a,polygon) or not inside(b,polygon):
        return False
    cross=lambda u,v:u[0]*v[1]-u[1]*v[0]
    delta=sub(b,a); cuts=[0.0,1.0]
    for c,d in zip(polygon,polygon[1:]+polygon[:1]):
        edge=sub(d,c); denominator=cross(delta,edge)
        if abs(denominator)>1e-12:
            t=cross(sub(c,a),edge)/denominator
            u=cross(sub(c,a),delta)/denominator
            if 0<=t<=1 and 0<=u<=1:
                cuts.append(t)
    cuts=sorted(cuts)
    return all(inside(tuple(a[i]+(lo+hi)/2*delta[i] for i in (0,1)),polygon) for lo,hi in zip(cuts,cuts[1:]))


def channel_geometry(object_map, draft):
    ref = object_map['geographic_reference']
    objects = {o['id']: o for o in object_map['buoys']}
    chains = draft.get('channel_chains', {})
    left, right = [[to_local(objects[key]['centre'], ref) for key in chains.get(side, [])]
                   for side in ('left', 'right')]
    lf, rf = chain_data(left), chain_data(right)
    polygon = left + list(reversed(right))
    if not polygon_valid(polygon):
        raise ValueError('channel chains cross or form a self-intersecting boundary; correct chain order')
    reviewed = [to_local(p, ref) for p in draft.get('channel', [])] or polygon
    if not polygon_valid(reviewed):
        raise ValueError('invalid reviewed channel polygon')
    fractions = merge_fractions(lf + rf)
    sections = [(interpolate(left, lf, t), interpolate(right, rf, t)) for t in fractions]
    # End connections touch the polygon boundary. Every interior connection must
    # stay in permitted water and connections may not intersect one another.
    for i, (a, b) in enumerate(sections):
        if not inside(a, reviewed) or not inside(b, reviewed):
            raise ValueError(f'channel section {i + 1} leaves the reviewed boundary')
        if not segment_within(a,b,reviewed):
            raise ValueError(f'channel section {i + 1} leaves permitted water')
        for c, d in sections[:i]:
            if intersects(a, b, c, d):
                raise ValueError(f'channel section {i + 1} crosses another section; correct progression')
    centres = [tuple((x + y) / 2 for x, y in zip(a, b)) for a, b in sections]
    if any(math.dist(a, b) < 1e-6 for a, b in zip(centres, centres[1:])):
        raise ValueError('ambiguous channel progression')
    return reviewed, sections, centres


def resolve_geometry(object_map, draft):
    """Return derived geometry without modifying persistent setup or attempts."""
    result = deepcopy(draft)
    if result.get('geometry_version') != 2 or not result.get('planner_task'):
        return result
    ref = object_map['geographic_reference']
    ids = {o['id']: o for o in object_map['buoys']}
    gps = lambda p: to_gps(*p, ref)
    result.pop('entry', None)
    result.pop('exit', None)
    if draft.get('connection_override'):
        result['entry'] = draft['connection_override']
    if result['planner_task'] == 'channel':
        polygon, sections, centres = channel_geometry(object_map, draft)
        result['channel'] = [gps(p) for p in polygon]
        result['reviewed_channel'] = result['channel']
        result['derived_sections'] = [{'id': f'section_{i+1}', 'a': gps(a), 'b': gps(b), 'centre': gps(centres[i])}
                                      for i, (a, b) in enumerate(sections)]
        # Crossings lie inside the end caps so containment can activate at full
        # required clearance. The reviewed boundary itself is never expanded.
        pad = result['clearance_m'] + result['finish_radius_m'] + 1
        first_direction = unit(sub(centres[1], centres[0]))
        last_direction = unit(sub(centres[-1], centres[-2]))
        first = tuple(centres[0][i] + first_direction[i] * pad for i in (0, 1))
        if contained(centres[0],centres[0],polygon,result['clearance_m']) or math.dist(centres[0],centres[1])<=pad:
            first=centres[0]
        last = tuple(centres[-1][i] - last_direction[i] * pad for i in (0, 1))
        if contained(centres[-1],centres[-1],polygon,pad):
            last=centres[-1]
        if len(centres)>2 and dot(sub(last,centres[-2]),last_direction)<=0:
            raise ValueError('last channel section conflicts with the finish allowance; extend reviewed permitted water and move finish beyond the last section')
        anchors = [first, *centres[1:-1], last]
        if len(anchors) == 2 and dot(sub(last, first), first_direction) <= 0:
            raise ValueError('channel too short for required start/finish allowance')
        result['passages'] = []
        for i, centre in enumerate(anchors):
            a, b = sections[i]
            direction = first_direction if i == 0 else last_direction if i == len(anchors)-1 else unit(sub(anchors[i+1], anchors[i-1]))
            tangent = unit(sub(b, a))
            normal = (tangent[1], -tangent[0])
            if dot(normal, direction) < 0:
                normal = tuple(-v for v in normal)
            result['passages'].append({'kind': 'section', 'id': f'section_{i+1}', 'centre': gps(centre),
                                       'direction': list(normal), 'half_width_m': math.dist(a, b)/2})
        for section,passage in zip(result['derived_sections'],result['passages']):
            section['direction']=passage['direction']
        result['channel_entrance'] = True
    else:
        anchors = []
        for p in result.get('passages', []):
            if p['kind'] == 'gate':
                a, b = [to_local(ids[p[key]]['centre'], ref) for key in ('red', 'green')]
                anchors.append(tuple((x+y)/2 for x, y in zip(a, b)))
            else:
                anchors.append(to_local(ids[p['buoy']]['centre'], ref))
        for i, p in enumerate(result.get('passages', [])):
            if p.get('direction_override'):
                p['direction'] = list(unit(p['direction_override']))
            elif len(anchors) == 1:
                p['direction'] = list(unit(result['direction']))
            else:
                p['direction'] = list(unit(sub(anchors[min(i+1, len(anchors)-1)], anchors[max(0, i-1)])))
        for p in result.get('passages', []):
            if p['kind']=='gate':
                a,b=[to_local(ids[p[key]]['centre'],ref) for key in ('red','green')]
                tangent=unit(sub(b,a)); normal=(tangent[1],-tangent[0])
                alignment=dot(normal,p['direction'])
                if abs(alignment)<.1:
                    raise ValueError('ambiguous gate crossing direction: '+p['id'])
                p['direction']=list(normal if alignment>0 else tuple(-v for v in normal))
        result['derived_sections'] = [{'id': p['id'], 'centre': gps(a), 'direction': p['direction']}
                                      for p, a in zip(result.get('passages', []), anchors)]
    attempt = result.get('attempt', {})
    mode = attempt.get('mode', 'full')
    if mode not in ('full', 'remaining'):
        raise ValueError('attempt mode must be full or remaining')
    first = attempt.get('first_section', 0) if mode == 'remaining' else 0
    if not isinstance(first, int) or isinstance(first, bool) or not 0 <= first < len(result['passages']):
        raise ValueError('select a valid first included passage or channel section')
    if mode == 'remaining' and not attempt.get('selection_confirmed'):
        raise ValueError('confirm the remaining section before generation')
    if result['planner_task']=='channel':
        access=sections[min(first,len(sections)-2)]
        result['channel_access']=[gps(p) for p in access]
        if first:
            chains=draft['channel_chains']
            paths=[[to_local(ids[key]['centre'],ref) for key in chains[side]] for side in ('left','right')]
            fractions=[chain_data(path) for path in paths]
            t=merge_fractions(fractions[0]+fractions[1])[min(first,len(sections)-2)]
            tails=[[interpolate(path,values,t),*[p for p,v in zip(path,values) if v>t+1e-9]] for path,values in zip(paths,fractions)]
            selected=tails[0]+list(reversed(tails[1]))
            if not polygon_valid(selected) or any(not segment_within(a,b,polygon) for a,b in zip(selected,selected[1:]+selected[:1])):
                raise ValueError('invalid selected channel section boundary')
            result['channel']=[gps(p) for p in selected]

    result['excluded_sections'] = [p['id'] for p in result['passages'][:first]]
    result['passages'] = result['passages'][first:]
    result['partial_attempt'] = mode == 'remaining'
    return result


def remaining_suggestion(object_map, draft):
    """Suggest only a unique local section; never confirm or award completion."""
    candidate = deepcopy(draft)
    candidate['attempt'] = {'mode': 'full'}
    resolved = resolve_geometry(object_map, candidate)
    ref = object_map['geographic_reference']
    start = to_local(draft['start'], ref)
    centres = [to_local(p['centre'], ref) for p in resolved['derived_sections']]
    matches = []
    from .geometry import segment_distance
    for i, (a, b) in enumerate(zip(centres, centres[1:])):
        forward = unit(sub(b, a))
        along = dot(sub(start, a), forward)
        if 0 <= along < math.dist(a, b) and segment_distance(start, a, b) <= math.dist(a, b)/2:
            matches.append(i+1)
    return matches[0] if len(matches) == 1 else None


def setup_identity(object_map,draft):
    keys=('geometry_version','planner_task','passages','direction','planning_area','channel','channel_chains','connection_override','finish','finish_radius_m','entry_radius_m','exit_radius_m')
    return hashlib.sha256(json.dumps({'map':object_map,'setup':{key:draft.get(key) for key in keys},'scope':{key:draft.get('attempt',{}).get(key) for key in ('mode','first_section','start_source')}},sort_keys=True).encode()).hexdigest()
