"""Pure, bounded local-geometry course recognition. Never changes observations.

Best-first role searches feed a joint, disjoint-object interpretation search.
Task pools are bounded too: hitting any pool/state/time bound is reported as
truncation, even when complete proposals were found. Scores are costs, not odds.
"""
from copy import deepcopy
import heapq
import itertools
import math
import time
from shared.geometry import to_local, segment_distance
from shared.course import dot, sub, intersects
from shared.task_geometry import channel_geometry, unit
from shared.object_map import validate_map
from shared.run_builder import digest
from .course_profile import PROFILE, SLALOM, CHANNEL, GATE, ROLE_COLOURS, identity


def huber(residual):
    """0.5*rho(r**2), rho(z)=z (z<=1), otherwise 2*sqrt(z)-1."""
    value = abs(residual)
    return .5 * value * value if value <= 1 else value - .5


def eligible(obj):
    return (obj.get('object_type') == 'buoy' and obj.get('category') in ('red', 'green')
            and obj.get('type') in ('point', 'cylinder'))


def validate_hints(object_map, hints):
    if not isinstance(hints, dict) or len(hints) > len(ROLE_COLOURS):
        raise ValueError('Hints must map known course roles to observed object IDs')
    objects = {o['id']: o for o in [*object_map['buoys'], *object_map.get('obstacles', [])]}
    used = set()
    for role, key in hints.items():
        if role not in ROLE_COLOURS or key not in objects:
            raise ValueError('Hint references an unknown role or observation')
        if not eligible(objects[key]) or objects[key].get('category') != ROLE_COLOURS[role]:
            raise ValueError('Hint requires a confirmed navigation buoy of the compatible color: '+role)
        if key in used:
            raise ValueError('Conflicting hints reuse one observation in incompatible roles')
        used.add(key)
    return deepcopy(hints)


def validate_assignments(object_map, tasks, hints=None):
    """Validate saved/selected roles jointly, including the starting gate alias."""
    if not isinstance(tasks, dict) or set(tasks) - {'gate', 'slalom', 'channel'}:
        raise ValueError('Unknown compiled task')
    merged = {}
    for task, roles in tasks.items():
        expected = {'gate': GATE, 'slalom': SLALOM, 'channel': CHANNEL}[task]
        if not isinstance(roles, dict) or set(roles) != set(expected):
            raise ValueError('Incomplete assignments for '+task)
        for role, key in roles.items():
            if role in merged and merged[role] != key:
                raise ValueError('Starting gate must alias the slalom entrance')
            merged[role] = key
    validate_hints(object_map, merged)
    for role, key in (hints or {}).items():
        if role in merged and merged[role] != key:
            raise ValueError('Selected assignments conflict with operator hints')
        if key in merged.values() and merged.get(role) != key:
            raise ValueError('Selected assignments reuse a pinned observation')
    points = {o['id']: to_local(o['centre'], object_map['geographic_reference']) for o in [*object_map['buoys'], *object_map.get('obstacles', [])]}
    for task, roles in tasks.items():
        _measure(object_map, task, roles, points)
    return deepcopy(tasks)


def binding(object_map, hints):
    return digest({'map': object_map, 'profile': identity(), 'hints': hints})


def _measure(object_map, task, roles, points):
    """Incremental nonnegative costs; only assigned neighboring roles contribute."""
    components = {'distance': 0., 'heading': 0., 'compactness': 0., 'tower': 0.}
    measurements = []
    scale = PROFILE['distance_scale_fraction']

    def measure(label, value, nominal, weight=1):
        residual = (value - nominal) / (scale * nominal)
        components['distance'] += weight * huber(residual)
        measurements.append({'label': label, 'actual_m': value, 'nominal_m': nominal,
                             'normalized_residual': residual, 'unusual': abs(residual) > 1})

    def point(role):
        return points[roles[role]] if role in roles else None

    def pair(a, b, compact=False):
        x, y = point(a), point(b)
        if x is None or y is None:
            return None
        width = math.dist(x, y)
        if width < 1e-6:
            raise ValueError('Degenerate opening')
        if compact:
            # No nominal gate width: a weak preference for a compact pair.
            components['compactness'] += .08 * width / PROFILE['slalom_spacing_m']
            measurements.append({'label': a.rsplit('.', 1)[0]+' width (unspecified)', 'actual_m': width})
        return tuple((x[i] + y[i])/2 for i in (0, 1))

    anchors = []
    if task in ('gate', 'slalom'):
        entry = pair(*GATE, compact=True)
        if entry is not None:
            anchors.append(entry)
        if task == 'slalom':
            for role in SLALOM[2:6]:
                if role not in roles:
                    break
                anchors.append(point(role))
            end = pair(*SLALOM[-2:], compact=True)
            if end is not None:
                anchors.append(end)
            for i, (a, b) in enumerate(zip(anchors, anchors[1:])):
                if math.dist(a, b) < 1e-6:
                    raise ValueError('Degenerate slalom progression')
                measure(f'slalom spacing {i+1}', math.dist(a, b), PROFILE['slalom_spacing_m'])
            # Local non-reversing progress is a preference; curves remain legal.
            for i, (a, b) in enumerate(zip(anchors, anchors[1:])):
                if any(intersects(a, b, c, d) for c, d in zip(anchors[:max(0, i-1)], anchors[1:i])):
                    raise ValueError('Slalom progression crosses itself')
            for a, b, c in zip(anchors, anchors[1:], anchors[2:]):
                components['heading'] += .15 * (1 - dot(unit(sub(b, a)), unit(sub(c, b))))
            for keys, centre, near in ((GATE, entry, anchors[1] if len(anchors)>1 else None),
                                       (SLALOM[-2:], end, anchors[-2] if end and len(anchors)>1 else None)):
                if centre is not None and near is not None:
                    tangent = unit(sub(point(keys[1]), point(keys[0])))
                    if abs(dot(tangent, unit(sub(near, centre)))) > .995:
                        raise ValueError('Gate does not open across local progression')
    else:
        centres = []
        for i in range(1, 4):
            a, b = f'channel.red.{i}', f'channel.green.{i}'
            centre = pair(a, b)
            if centre is not None:
                centres.append(centre)
                measure(f'channel width {i}', math.dist(point(a), point(b)), PROFILE['channel_width_m'])
        for colour in ('red', 'green'):
            chain = [point(f'channel.{colour}.{i}') for i in range(1, 4) if f'channel.{colour}.{i}' in roles]
            for i, (a, b) in enumerate(zip(chain, chain[1:])):
                if math.dist(a, b) < 1e-6:
                    raise ValueError('Degenerate channel chain')
                measure(f'{colour} spacing {i+1}', math.dist(a, b), PROFILE['channel_length_m']/2)
            if len(chain) == 3:
                measure(colour+' length', sum(math.dist(a, b) for a, b in zip(chain, chain[1:])), PROFILE['channel_length_m'], .25)
                components['heading'] += .15 * (1-dot(unit(sub(chain[1], chain[0])), unit(sub(chain[2], chain[1]))))
        if len(roles) == len(CHANNEL):
            chains = {side: [roles[f'channel.{colour}.{i}'] for i in range(1, 4)]
                      for side, colour in (('left', 'red'), ('right', 'green'))}
            channel_geometry(object_map, {'channel_chains': chains})
            # Supporting proximity evidence, capped per interpretation. Any tower
            # count is allowed; absent towers neither forbid nor invent a channel.
            towers = [to_local(o['centre'], object_map['geographic_reference'])
                      for o in [*object_map['buoys'], *object_map.get('obstacles', [])] if o.get('object_type') == 'detector']
            edges = [[point(f'channel.{colour}.{i}') for i in range(1, 4)] for colour in ('red', 'green')]
            if towers:
                support = max(math.exp(-min(segment_distance(t, a, b) for chain in edges for a, b in zip(chain, chain[1:]))/3) for t in towers)
                components['tower'] = .15 * (1-support)
    return components, measurements


def compile_course(object_map, hints=None, *, max_seconds=5, max_states=200000, pool_limit=80):
    started = time.monotonic()
    deadline = started + min(5., max(0., max_seconds))
    max_states = min(200000, max(0, max_states))
    validate_map(object_map)
    hints = validate_hints(object_map, hints or {})
    objects = sorted((o for o in [*object_map['buoys'], *object_map.get('obstacles', [])] if eligible(o)),
                     key=lambda o: (o['centre']['latitude'], o['centre']['longitude'], o['category']))
    points = {o['id']: to_local(o['centre'], object_map['geographic_reference']) for o in objects}
    by_colour = {c: [o['id'] for o in objects if o['category'] == c] for c in ('red', 'green')}
    counter = itertools.count()
    expanded = 0
    limits = set()
    pools = {}
    partials = {}

    def available():
        if time.monotonic() >= deadline:
            limits.add('time_limit')
            return False
        if expanded >= max_states:
            limits.add('state_limit')
            return False
        return True

    # Separate queues ensure an expensive ambiguous task cannot starve the other
    # task. Joint disjointness is enforced before any interpretation is returned.
    for task, order, fraction in (('channel', CHANNEL, .3), ('slalom', SLALOM, .55), ('gate', GATE, .02)):
        queue = [(0., next(counter), {})]
        complete = []
        best_partial = {}
        task_start = expanded
        budget = max(1, int(max_states*fraction))
        task_deadline = min(deadline, time.monotonic()+max(0, deadline-time.monotonic())*(.3 if task=='channel' else .75 if task=='slalom' else .4))
        while queue and available():
            if expanded-task_start >= budget or time.monotonic() >= task_deadline:
                limits.add(task+'_budget')
                break
            cost, _, roles = heapq.heappop(queue)
            expanded += 1
            if len(roles) > len(best_partial):
                best_partial = roles
            if len(roles) == len(order):
                complete.append({'roles': roles, 'cost': cost})
                if len(complete) >= pool_limit:
                    limits.add(task+'_candidate_limit')
                    break
                continue
            role = order[len(roles)]
            choices = [hints[role]] if role in hints else by_colour[ROLE_COLOURS[role]]
            for key in choices:
                if not available():
                    break
                if key in roles.values() or any(other != role and key == value for other, value in hints.items()):
                    continue
                proposal = {**roles, role: key}
                try:
                    components, _ = _measure(object_map, task, proposal, points)
                except ValueError:
                    continue
                heapq.heappush(queue, (sum(components.values()), next(counter), proposal))
        pools[task] = complete
        partials[task] = best_partial

    # None is an explicit unresolved task, preferable to a very poor forced fit.
    # This cost is a development ranking choice, never a placement cutoff.
    options = {t: sorted([*pools[t], {'roles': {}, 'cost': 8.}], key=lambda c: c['cost']) for t in ('slalom', 'channel', 'gate')}
    queue = [(0., next(counter), {})]
    candidates = []
    seen = set()
    while queue and available():
        lower_bound, _, tasks = heapq.heappop(queue)
        if len(candidates) >= 5 and lower_bound > sorted(c['score'] for c in candidates)[4]:
            limits.add('interpretation_limit')
            break
        expanded += 1
        if len(tasks) < 2:
            task = ('slalom', 'channel')[len(tasks)]
            for option in options[task]:
                next_tasks = {**tasks, task: option}
                ids = [key for value in next_tasks.values() for key in value['roles'].values()]
                if len(ids) != len(set(ids)):
                    continue
                heapq.heappush(queue, (sum(v['cost'] for v in next_tasks.values()), next(counter), next_tasks))
            continue
        if len(tasks) == 2:
            if tasks['slalom']['roles']:
                roles = {role: tasks['slalom']['roles'][role] for role in GATE}
                choices = [{'roles': roles, 'cost': 0.}]
            else:
                choices = options['gate']
            used = {key for value in tasks.values() for key in value['roles'].values()}
            for option in choices:
                if not tasks['slalom']['roles'] and used.intersection(option['roles'].values()):
                    continue
                proposal = {**tasks, 'gate': option}
                heapq.heappush(queue, (sum(v['cost'] for v in proposal.values()), next(counter), proposal))
            continue
        assigned = {task: value['roles'] for task, value in tasks.items() if value['roles']}
        if assigned.get('slalom'):
            assigned['gate'] = {role: assigned['slalom'][role] for role in GATE}
        if not assigned:
            continue
        signature = digest(assigned)
        if signature in seen:
            continue
        seen.add(signature)
        details = {}
        for task, roles in assigned.items():
            components, measurements = _measure(object_map, task, roles, points)
            details[task] = {'score_components': components, 'measurements': measurements, 'status': 'proposal'}
        connection = 0.
        if 'slalom' in assigned and 'channel' in assigned:
            s, c = assigned['slalom'], assigned['channel']
            # The illustrated gap is between the near exit buoy and channel
            # boundary, not a center-to-center diagonal or inter-task angle.
            actual = min(math.dist(points[s[r]], points[c[q]]) for r in SLALOM[-2:] for q in CHANNEL[:2])
            connection = .05 * huber((actual-PROFILE['connection_gap_m'])/(PROFILE['connection_gap_m']*.3))
            details['connection'] = {'actual_m': actual, 'nominal_m': PROFILE['connection_gap_m'], 'cost': connection}
        cost = sum(value['cost'] for value in tasks.values()) + connection
        candidates.append({'id': signature, 'tasks': assigned, 'score': cost, 'details': details,
                           'unresolved': [t for t in ('gate', 'slalom', 'channel') if t not in assigned]})
    candidates.sort(key=lambda c: c['score'])
    candidates = candidates[:5]
    return {'profile': identity(), 'binding': binding(object_map, hints), 'candidates': candidates,
            'partials': partials, 'expanded_states': expanded, 'elapsed_s': time.monotonic()-started,
            'search_exhausted': bool(limits), 'limits': sorted(limits),
            'status': 'proposals' if candidates else 'unresolved',
            'diagnostics': ['Proposals require review. Costs are not probabilities. No optimality or uniqueness is asserted.',
                            'Search truncated; additional interpretations may exist.' if limits else 'Search completed within configured bounds.']}
