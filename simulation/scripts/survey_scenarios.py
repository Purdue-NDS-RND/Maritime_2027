#!/usr/bin/env python3
"""Deterministic imperfect point surveys; no simulator or vehicle mutation."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.geometry import to_gps, to_local, finite
from gcs.app.imports import import_points

LEVELS = (0, .25, .5, 1, 2)


def point_source(source):
    if isinstance(source, list):
        return {'points': deepcopy(source)}
    if 'schema_version' not in source:
        return deepcopy(source)
    return {'geographic_reference': deepcopy(source['geographic_reference']), 'captured_at': source.get('captured_at'),
            'points': [{'id': o['id'], **o['centre'], 'object_type': o.get('object_type', 'unknown'),
                        'category': o.get('category', 'unknown')} for o in [*source['buoys'], *source.get('obstacles', [])]]}


def perturb(source, seed, offset_m=0, point_error_m=0, remove_hints=False, missing=(), age_s=0, as_of=None):
    offset_m, point_error_m, age_s = map(finite, (offset_m, point_error_m, age_s))
    if min(offset_m, point_error_m, age_s) < 0:
        raise ValueError('error bounds and survey age must be nonnegative')
    original = point_source(source)
    # Explicit IDs and a fixed reference survive coordinate changes/removals.
    original_map = import_points(json.dumps(original))
    ref = original_map['geographic_reference']
    rng = random.Random(seed)
    angle = rng.uniform(-math.pi, math.pi)
    offset = (offset_m*math.cos(angle), offset_m*math.sin(angle))
    rows, changes = [], []
    unknown = set(missing) - {o['id'] for o in original_map['buoys']}
    if unknown:
        raise ValueError('missing-object IDs absent from input: '+', '.join(sorted(unknown)))
    for obj, row in zip(original_map['buoys'], original['points']):
        key = obj['id']
        if key in missing:
            changes.append({'id': key, 'operation': 'removed', 'original': deepcopy(row)})
            continue
        point = deepcopy(row)
        point['id'] = key
        x, y = to_local(obj['centre'], ref)
        radius = point_error_m*math.sqrt(rng.random())
        theta = rng.uniform(-math.pi, math.pi)
        delta = (offset[0]+radius*math.cos(theta), offset[1]+radius*math.sin(theta))
        point.update(to_gps(x+delta[0], y+delta[1], ref))
        removed = {}
        if remove_hints:
            for name in ('object_type', 'type', 'category', 'color', 'label', 'task', 'course_role'):
                if name in point:
                    removed[name] = point.pop(name)
        changes.append({'id': key, 'operation': 'perturbed', 'original': deepcopy(row), 'delta_m': delta,
                        'independent_error_m': [delta[i]-offset[i] for i in (0,1)], 'removed_hints': removed})
        rows.append(point)
    captured = original.get('captured_at')
    if age_s:
        if as_of is None:
            raise ValueError('aged snapshots require explicit --as-of timestamp for reproducibility')
        captured = (datetime.fromisoformat(as_of.replace('Z', '+00:00'))-timedelta(seconds=age_s)).isoformat()
    scenario = {'geographic_reference': deepcopy(ref), 'captured_at': captured, 'points': rows}
    return scenario, {'seed': seed, 'common_offset_m': offset, 'point_error_bound_m': point_error_m,
                      'age_s': age_s, 'as_of': as_of, 'original_captured_at': original.get('captured_at'),
                      'captured_at': captured, 'changes': changes,
                      'source_sha256': hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
                      'scope': 'exploratory stress input, not a hardware accuracy claim; boat and truth unchanged'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--offset-m', type=float, default=0)
    p.add_argument('--point-error-m', type=float, default=0)
    p.add_argument('--remove-hints', action='store_true')
    p.add_argument('--missing', nargs='*', default=[])
    p.add_argument('--age-s', type=float, default=0)
    p.add_argument('--as-of')
    p.add_argument('--sweep', action='store_true', help='0/.25/.5/1/2 m, seeds 0–2, both common and bounded point error')
    args = p.parse_args()
    logs = Path(__file__).resolve().parents[1]/'logs'
    output = args.output.resolve()
    if not output.is_relative_to(logs.resolve()):
        p.error('output must be under ignored simulation/logs')
    source = json.loads(args.source.read_text())
    output.mkdir(parents=True, exist_ok=False)
    (output/'source.json').write_bytes(args.source.read_bytes())
    cases = [(kind, level, seed) for kind in ('offset', 'point') for level in LEVELS for seed in range(3)] if args.sweep else [('case', args.offset_m, args.seed)]
    for kind, level, seed in cases:
        offset = level if kind == 'offset' else 0 if kind == 'point' else args.offset_m
        point = level if kind == 'point' else 0 if kind == 'offset' else args.point_error_m
        survey, record = perturb(source, seed, offset, point, args.remove_hints, args.missing, args.age_s, args.as_of)
        directory = output/f'{kind}-{level:g}-seed-{seed}'
        directory.mkdir()
        for name, data in [('survey.json',survey), ('changes.json',record)]:
            (directory/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    print(output)


if __name__ == '__main__':
    main()
