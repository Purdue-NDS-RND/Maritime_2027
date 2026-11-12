"""Seeded full-course scene variations, independent of recognition and boat control.

Bounds are development stress inputs, not event rules or GPS accuracy estimates.
Generation rejects whole samples; it never fixes a sample using compiler output.
"""
from copy import deepcopy
import hashlib
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.geometry import polygon_clearance, transform_polygon, to_gps, segment_distance
from shared.course import polygon_valid, intersects

VERSION = 1
REFERENCE = {'latitude': 51.566151, 'longitude': -4.034345}
# spacing/width fraction, local heading change, stagger metres, gate skew,
# independent channel connection-angle deviation (degrees).
PRESETS = {
    'mild': (.10, 5., .4, 8., 15.),
    'moderate': (.20, 10., .9, 18., 30.),
    'strong': (.30, 18., 1.5, 30., 50.),
}
MAX_RADIUS_M = 120.
MIN_SURFACE_GAP_M = .5
SPAWN_RADIUS_M = 1.5


def rotate(point, angle):
    x, y = point
    return (x * math.cos(angle) - y * math.sin(angle),
            x * math.sin(angle) + y * math.cos(angle))


def advance(point, distance, heading):
    return tuple(a + b for a, b in zip(point, rotate((distance, 0), heading)))


def footprint(obj):
    pose = obj['pose']
    if 'size_m' in obj:
        x, y, _ = obj['size_m']
        return transform_polygon([(-x/2, -y/2), (x/2, -y/2), (x/2, y/2), (-x/2, y/2)],
                                 pose['x'], pose['y'], math.radians(pose['yaw_deg']))
    return (pose['x'], pose['y']), obj.get('radius_m', .24)


def surface_gap(first, second):
    """Exact planar circle/convex-box separation; negative means overlap."""
    a, b = footprint(first), footprint(second)
    ap, bp = 'size_m' in first, 'size_m' in second
    if not ap and not bp:
        return math.dist(a[0], b[0]) - a[1] - b[1]
    if ap and not bp:
        return polygon_clearance(a, *b)
    if bp and not ap:
        return polygon_clearance(b, *a)
    edges = lambda p: list(zip(p, p[1:] + p[:1]))
    if any(intersects(x, y, u, v) for x, y in edges(a) for u, v in edges(b)):
        return -1.
    if polygon_clearance(a, b[0], 0) <= 0 or polygon_clearance(b, a[0], 0) <= 0:
        return -1.
    return min(segment_distance(p, x, y) for points, poly in ((a, b), (b, a))
               for p in points for x, y in edges(poly))


def validate_layout(config):
    """Scene constraints, intentionally independent of the course compiler."""
    objects = config['buoys'] + config['props']
    names = [obj['name'] for obj in objects]
    if len(names) != len(set(names)):
        raise ValueError('duplicate object identity')
    spawn = {'pose': config['boat_pose'] | {'yaw_deg': 0}, 'radius_m': SPAWN_RADIUS_M}
    for i, obj in enumerate(objects):
        p = obj['pose']
        if not all(type(p[k]) in (int, float) and math.isfinite(p[k]) for k in ('x', 'y', 'z', 'yaw_deg')):
            raise ValueError('nonfinite scene pose')
        if math.hypot(p['x'], p['y']) > MAX_RADIUS_M:
            raise ValueError('course exceeds 120 m generation area')
        if surface_gap(obj, spawn) < MIN_SURFACE_GAP_M:
            raise ValueError('object too close to boat spawn')
        for other in objects[:i]:
            if surface_gap(obj, other) < MIN_SURFACE_GAP_M:
                raise ValueError('physical objects overlap or have less than 0.5 m separation')
    positions = {o['name']: (o['pose']['x'], o['pose']['y']) for o in objects}
    left = [positions[f'evade_left_{i}'] for i in range(3)]
    right = [positions[f'evade_right_{i}'] for i in range(3)]
    if not polygon_valid(left + right[::-1]):
        raise ValueError('crossing channel boundary')
    # Ordered openings must not cross; chain progression cannot reverse.
    for i, (a, b) in enumerate(zip(left, right)):
        if math.dist(a, b) < 3:
            raise ValueError('degenerate channel opening')
        for c, d in list(zip(left, right))[:i]:
            if intersects(a, b, c, d):
                raise ValueError('crossing channel openings')
    gate = lambda letter: tuple((positions[f'dodge_gate_{letter}_red'][i] + positions[f'dodge_gate_{letter}_green'][i])/2 for i in (0, 1))
    anchors = [gate('a'), *[positions[f'dodge_turn_{i}'] for i in range(1, 5)], gate('b')]
    for i, (a, b) in enumerate(zip(anchors, anchors[1:])):
        if math.dist(a, b) < 3:
            raise ValueError('degenerate slalom progression')
        if any(intersects(a, b, c, d) for c, d in zip(anchors[:max(0, i-1)], anchors[1:i])):
            raise ValueError('crossing slalom progression')


def generate(source, seed, variation='moderate', rotation_deg=None):
    if source.get('name') != 'competition':
        raise ValueError('full competition source required')
    if type(seed) is not int or variation not in PRESETS:
        raise ValueError('integer seed and mild/moderate/strong variation required')
    if rotation_deg is not None and (type(rotation_deg) not in (int, float) or not math.isfinite(rotation_deg)):
        raise ValueError('rotation must be finite degrees')
    rng = random.Random(seed)
    fraction, bend, stagger, skew, connection = PRESETS[variation]
    rotation = rng.uniform(0, 360) if rotation_deg is None else rotation_deg % 360
    angle = math.radians(rotation)
    uniform_angle = lambda extent: math.radians(rng.uniform(-extent, extent))
    for attempt in range(1, 101):
        config = deepcopy(source)
        objects = {o['name']: o for o in config['buoys'] + config['props']}
        def place(name, xy, heading=0):
            objects[name]['pose'].update(x=xy[0], y=xy[1], yaw_deg=math.degrees(heading))
        # Locally sampled progression, rather than a global axis-aligned warp.
        anchors, headings = [(-10.716, 0.)], [math.pi]
        for _ in range(5):
            h = headings[-1] + uniform_angle(bend)
            anchors.append(advance(anchors[-1], 9.144 * rng.uniform(1-fraction, 1+fraction), h))
            headings.append(h)
        widths = []
        for letter, i in (('a', 0), ('b', 5)):
            width = 4 * rng.uniform(1-fraction, 1+fraction)
            widths.append(width)
            normal = headings[i] - math.pi/2 + uniform_angle(skew)
            for colour, sign in (('red', 1), ('green', -1)):
                place(f'dodge_gate_{letter}_{colour}', advance(anchors[i], sign*width/2, normal))
        for i in range(1, 5):
            place(f'dodge_turn_{i}', advance(anchors[i], rng.uniform(-stagger, stagger), headings[i]-math.pi/2))
        connection_delta = uniform_angle(connection)
        channel_heading = headings[-1] + math.pi/2 + connection_delta
        channel_centres = [advance(anchors[-1], 10.668*rng.uniform(1-fraction, 1+fraction), headings[-1])]
        channel_headings = [channel_heading]
        for _ in range(2):
            channel_headings.append(channel_headings[-1] + uniform_angle(bend))
            channel_centres.append(advance(channel_centres[-1], 9.144*rng.uniform(1-fraction, 1+fraction), channel_headings[-1]))
        for i in range(3):
            width = 12.192*rng.uniform(1-fraction, 1+fraction)
            for side, sign in (('left', 1), ('right', -1)):
                p = advance(channel_centres[i], sign*width/2, channel_headings[i]-math.pi/2)
                p = advance(p, rng.uniform(-stagger, stagger), channel_headings[i])
                place(f'evade_{side}_{i}', p)
        for side, a, b in (('left', 1, 2), ('right', 0, 1)):
            p, q = [objects[f'evade_{side}_{i}']['pose'] for i in (a, b)]
            place(f'evade_detector_{side}', ((p['x']+q['x'])/2, (p['y']+q['y'])/2), channel_headings[a]-3*math.pi/2)
        # Keep the remaining full-course stations as rigid groups attached to
        # the channel exit, preserving their internal physical dimensions.
        downstream_angle = channel_headings[-1] - 3*math.pi/2
        def downstream(p):
            offset = rotate((p[0]+67.104, p[1]+18.288), downstream_angle)
            return tuple(a+b for a, b in zip(channel_centres[-1], offset))
        for obj in objects.values():
            if obj['task'] not in ('start', 'dodge', 'evade'):
                p = obj['pose']
                place(obj['name'], downstream((p['x'], p['y'])), math.radians(p['yaw_deg'])+downstream_angle)
        for station in config['stations']:
            if station['id'] == 'dodge':
                station['world_position'] = advance(anchors[2], 4.572, headings[2]-math.pi/2)
            elif station['id'] == 'evade':
                station['world_position'] = channel_centres[1]
            elif station['id'] != 'start':
                station['world_position'] = downstream(station['world_position'])
            station['world_position'] = rotate(station['world_position'], angle)
        for obj in objects.values():
            p = obj['pose']
            p['x'], p['y'] = rotate((p['x'], p['y']), angle)
            p['yaw_deg'] += rotation
            obj.pop('reference_ft', None)
            obj.pop('jitter', None)
        # Boat spawn/heading deliberately remain independent operator inputs.
        try:
            validate_layout(config)
        except ValueError:
            continue
        config['generation'] = {
            'version': VERSION, 'seed': seed, 'variation': variation, 'rotation_deg': rotation,
            'accepted_attempt': attempt, 'spacing_width_fraction': fraction,
            'local_bend_deg': bend, 'stagger_m': stagger, 'gate_skew_deg': skew,
            'connection_deviation_deg': math.degrees(connection_delta),
            'gate_widths_m': widths, 'minimum_surface_gap_m': MIN_SURFACE_GAP_M,
            'spawn_radius_m': SPAWN_RADIUS_M, 'maximum_radius_m': MAX_RADIUS_M,
            'source_sha256': hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest(),
        }
        config['approximation_notes'].append('Seeded development layout; variation bounds are not event rules or measured GPS accuracy. Boat spawn and heading remain fixed.')
        return config
    raise ValueError('No valid full-course layout after 100 attempts; choose a different seed or milder variation')


def observations(config):
    """Unassigned GPS observations with opaque shuffled IDs, plus separate truth.

    Neither task names nor object-name IDs reach the GCS import. Types/colors
    remain available for recognition; operator review is still required.
    """
    rng = random.Random(config['generation']['seed'])
    objects = deepcopy(config['buoys'] + config['props'])
    rng.shuffle(objects)
    rows, identities = [], {}
    for i, obj in enumerate(objects, 1):
        key = f'observed_{i:03d}'
        identities[obj['name']] = key
        kind = 'buoy' if obj in config['buoys'] else 'detector' if obj.get('kind') == 'detector' else 'obstacle'
        rows.append({'id': key, **to_gps(obj['pose']['x'], obj['pose']['y'], REFERENCE),
                     'object_type': kind, 'category': obj['category']})
    return {'geographic_reference': REFERENCE, 'points': rows}, identities


def expected_roles(identities):
    """Evaluation truth only; never supplied to the recognizer as hints."""
    slalom = {f'slalom.{end}.{colour}': identities[f'dodge_gate_{letter}_{colour}']
              for end, letter in (('entrance', 'a'), ('exit', 'b')) for colour in ('red', 'green')}
    slalom.update({f'slalom.turn.{i}': identities[f'dodge_turn_{i}'] for i in range(1, 5)})
    return {'gate': {k: v for k, v in slalom.items() if '.entrance.' in k}, 'slalom': slalom,
            'channel': {f'channel.{colour}.{i+1}': identities[f'evade_{side}_{i}']
                        for i in range(3) for colour, side in (('red', 'left'), ('green', 'right'))}}


def check_compiler(points, identities):
    from gcs.app.course_compiler import compile_course
    from gcs.app.imports import import_points
    result = compile_course(import_points(json.dumps(points)))
    truth = expected_roles(identities)
    ranks = {task: next((i for i, c in enumerate(result['candidates'], 1) if c['tasks'].get(task) == roles), None)
             for task, roles in truth.items()}
    joint = next((i for i, c in enumerate(result['candidates'], 1) if c['tasks'] == truth), None)
    return {'intended_joint_rank': joint, 'intended_task_ranks': ranks, 'result': result,
            'scope': 'unhinted recognition only; no route, clearance or movement acceptance'}
