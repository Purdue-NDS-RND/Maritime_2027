#!/usr/bin/env python3
"""Generate a repeatable full-course test bundle without starting a simulator."""
import argparse
import html
import json
from pathlib import Path
import subprocess
import sys

from random_course import PRESETS, footprint, generate, observations, expected_roles, check_compiler

SIMULATION = Path(__file__).resolve().parents[1]
COLOURS = {'red': '#df5056', 'green': '#2f9b68', 'blue': '#4285d4', 'orange': '#ed9339',
           'purple': '#9a6ac2', 'yellow': '#cfb237', 'cyan': '#36aeb6', 'zebra': '#555',
           'black': '#333', 'brown': '#977150'}


def preview(config):
    objects = config['buoys'] + config['props']
    points = [(o['pose']['x'], o['pose']['y']) for o in objects] + [(0, 0)]
    lo = [min(p[i] for p in points)-9 for i in (0, 1)]
    hi = [max(p[i] for p in points)+9 for i in (0, 1)]
    width, height = hi[0]-lo[0], hi[1]-lo[1]
    # metres in the drawing, north stays up at every rotation.
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{lo[0]} {-hi[1]} {width} {height}" role="img" aria-label="Generated full competition course, north up">',
                '<rect x="-200" y="-200" width="400" height="400" fill="#edf4f6"/>']
    for o in objects:
        p = o['pose']
        colour = COLOURS[o['category']]
        title = html.escape(o['name'])
        if 'size_m' in o:
            poly = ' '.join(f'{x},{-y}' for x, y in footprint(o))
            elements.append(f'<polygon points="{poly}" fill="{colour}"><title>{title}</title></polygon>')
        else:
            r = max(.5, o.get('radius_m', .24))
            elements.append(f'<circle cx="{p["x"]}" cy="{-p["y"]}" r="{r}" fill="{colour}" stroke="white" stroke-width=".15"><title>{title}</title></circle>')
    elements.append('<path d="M -1.5 0 L 1 0.7 L 1 -0.7 Z" fill="#222"><title>Boat spawn, heading west</title></path>')
    for s in config['stations']:
        if s['id'] == 'deployment_radius':
            continue
        x, y = s['world_position']
        label = html.escape(s['id'].capitalize())
        elements.append(f'<text x="{x}" y="{-y}" font-family="sans-serif" font-size="1.25" fill="#303945" text-anchor="middle">{label}</text>')
    elements.append(f'<text x="{hi[0]-5}" y="{-hi[1]+4}" font-family="sans-serif" font-size="2">N ↑</text></svg>')
    return '\n'.join(elements)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--variation', choices=PRESETS, default='moderate')
    parser.add_argument('--rotation-deg', type=float)
    parser.add_argument('--output', type=Path, help='new directory under simulation/logs')
    parser.add_argument('--check-compiler', action='store_true', help='record unhinted recognition ranks against separate scene truth')
    args = parser.parse_args()
    rotation_suffix = '' if args.rotation_deg is None else f'-rot-{args.rotation_deg:g}'
    directory = (args.output or SIMULATION/f'logs/random-courses/{args.variation}-seed-{args.seed}{rotation_suffix}').resolve()
    if not directory.is_relative_to((SIMULATION/'logs').resolve()):
        parser.error('output must be under ignored simulation/logs')
    source = json.loads((SIMULATION/'scenarios/competition.json').read_text())
    try:
        config = generate(source, args.seed, args.variation, args.rotation_deg)
    except ValueError as error:
        parser.error(str(error))
    if directory.exists():
        parser.error(f'{directory} already exists; choose --output with a new directory')
    directory.mkdir(parents=True)
    points, identities = observations(config)
    for filename, data in (('scenario.json', config), ('observations.json', points),
                           ('truth.json', {'generation': config['generation'], 'object_ids': identities,
                                           'assignments': expected_roles(identities)})):
        (directory/filename).write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    subprocess.run([sys.executable, str(SIMULATION/'scripts/render_scenario.py'),
                    '--scenario', str(directory/'scenario.json'),
                    '--base-world', str(SIMULATION/'worlds/blueboat_rgbd_base.sdf'),
                    '--output-world', str(directory/'world.sdf'),
                    '--manifest', str(directory/'manifest.json'), '--cameras', 'off'], check=True)
    (directory/'preview.svg').write_text(preview(config))
    g = config['generation']
    launch = f'SCENARIO=competition COURSE_SEED={args.seed} COURSE_VARIATION={args.variation}'
    if args.rotation_deg is not None:
        launch += f' COURSE_ROTATION_DEG={args.rotation_deg:g}'
    launch += ' WATER=calm make run'
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Course seed {args.seed}</title><style>body{{font:16px system-ui;margin:24px;background:#f7f8fa;color:#25303d}}main{{max-width:1080px;margin:auto}}h1{{margin-bottom:8px}}img{{width:100%;height:65vh;background:#edf4f6;border-radius:12px}}code{{display:block;background:#e9edf2;padding:12px;overflow:auto}}a{{color:#2360a5}}</style>
<main><h1>Course seed {args.seed} · {args.variation}</h1><p>Rotation {g['rotation_deg']:.1f}° · all 29 objects · north is up. Hover objects for their simulator names.</p>
<img src="preview.svg" alt="Full generated course"><p><a href="observations.json" download>Download GPS observations for GCS import</a></p>
<p>Import → review the map → compile → confirm tasks. Assignments and routes start empty. This file is a synthetic test map, not the active simulator map.</p>
<p>To launch matching Gazebo geometry, run from <b>simulation/</b> after stopping any existing simulation:</p><code>{html.escape(launch)}</code>
<p>For actual movement, export and align the running scene through the normal workflow. Layout validity does not establish navigability at your selected clearance or boat performance.</p></main></html>'''
    (directory/'preview.html').write_text(page)
    if args.check_compiler:
        report = check_compiler(points, identities)
        (directory/'compile-check.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
        print(f'Unhinted intended interpretation rank: {report["intended_joint_rank"]}; '
              f'search truncated: {report["result"]["search_exhausted"]}. See compile-check.json.')
    print(f'Preview: {directory / "preview.html"}\nGCS import: {directory / "observations.json"}\nMatching simulator (from simulation/): {launch}')


if __name__ == '__main__':
    main()
