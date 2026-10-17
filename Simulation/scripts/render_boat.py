#!/usr/bin/env python3
"""Select a camera-equipped boat without changing the scene or water."""
import argparse
import copy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, help='Update the archived scene identity and boat pose')
    parser.add_argument('--boat-model', choices=('single', 'dual'), required=True)
    args = parser.parse_args()
    tree = ET.parse(args.source)
    world = tree.find('world')
    boats = [item for item in world.findall('include') if item.findtext('name') == 'blueboat']
    if len(boats) != 1:
        raise SystemExit('World must include exactly one named blueboat')
    boats[0].find('uri').text = 'model://blueboat_' + ('dual_rgbd' if args.boat_model == 'dual' else 'rgbd')
    if not any('sensors-system' in item.get('filename', '') for item in world.findall('plugin')):
        base = ET.parse(Path(__file__).resolve().parents[1] / 'worlds/blueboat_rgbd_base.sdf')
        world.append(copy.deepcopy(base.find("./world/plugin[@filename='gz-sim-sensors-system']")))
    if args.manifest is not None:
        manifest = json.loads(args.manifest.read_text())
        pose = list(map(float, boats[0].findtext('pose', '0 0 0 0 0 0').split()))
        if len(pose) != 6 or not all(math.isfinite(v) for v in pose) or pose[3:5] != [0., 0.]:
            raise SystemExit('Boat manifest requires a finite level mounting pose')
        manifest['world'] = world.get('name')
        manifest['boat_model'] = args.boat_model
        manifest['boat_pose'] = dict(zip(('x', 'y', 'z', 'yaw_rad'), [*pose[:3], pose[5]]))
        args.manifest.write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space='  ')
    tree.write(args.output, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    main()
