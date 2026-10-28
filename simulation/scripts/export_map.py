#!/usr/bin/env python3
"""Export ONLY a verified immutable scene snapshot, never scenario sources."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.geometry import to_gps
from scene_snapshot import verify


def export(directory, expected_scene_id, active_run_id, alignment=None):
    directory = Path(directory)
    identity = verify(directory)
    if identity['scene_id'] != expected_scene_id or identity['run_id'] != active_run_id:
        raise ValueError('scene identity does not match active simulator')
    manifest = json.loads((directory / 'manifest.json').read_text())
    world = ET.parse(directory / 'world.sdf')
    includes = {item.findtext('name'): item for item in world.findall('./world/include')}
    boat = includes['blueboat']
    model = ET.parse(directory / 'models' / boat.findtext('uri').split('://')[1] / 'model.sdf')
    bridge = model.find("./model/plugin[@name='ArduPilotPlugin']")
    for tag, expected in [('gazeboXYZToNED', [0, 0, 0, 180, 0, 90]),
                          ('modelXYZToAirplaneXForwardZDown', [0, 0, 0, 180, 0, 0])]:
        element = bridge.find(tag)
        if element.get('degrees') != 'true' or list(map(float, element.text.split())) != expected:
            raise ValueError(f'unsupported bridge transform: {tag}')
    imu = model.find("./model/link[@name='imu_link']")
    if imu is None or any(float(n) != 0 for n in imu.findtext('pose', '0 0 0 0 0 0').split()):
        raise ValueError('unsupported IMU reference offset')
    if alignment is not None:
        if (alignment['scene_id'] != expected_scene_id or alignment['run_id'] != active_run_id
                or alignment['outcome'] != 'passed' or alignment['maximum_position_error_m'] >= 0.10):
            raise ValueError('alignment evidence does not match scene or tolerance')
    buoys = []
    for item in manifest['buoys']:
        include = includes.pop(item['name'])
        pose = list(map(float, include.findtext('pose').split()))
        if len(pose) != 6 or pose[3:5] != [0, 0]:
            raise ValueError('unsupported buoy mounting orientation')
        if pose[:3] != [item['model_pose'][key] for key in ('x', 'y', 'z')]:
            raise ValueError('manifest/world pose mismatch')
        uri = include.findtext('uri')
        if uri != item['model_uri'] or '/' in uri[8:]:
            raise ValueError('model identity mismatch')
        root = ET.parse(directory / 'models' / uri[8:] / 'model.sdf')
        collisions = root.findall('.//collision')
        if len(collisions) != 1:
            raise ValueError('unsupported buoy collision count')
        collision = collisions[0]
        cylinder = collision.find('geometry/cylinder')
        mounting = list(map(float, collision.findtext('pose', '0 0 0 0 0 0').split()))
        if cylinder is None or mounting[:2] != [0, 0] or mounting[3:] != [0, 0, 0]:
            raise ValueError('unsupported buoy geometry')
        radius, height = float(cylinder.findtext('radius')), float(cylinder.findtext('length'))
        if not (0 < radius < 10 and 0 < height < 10):
            raise ValueError('invalid buoy geometry')
        buoys.append({'id': item['name'], 'category': item['category'], 'type': 'cylinder',
                      'centre': to_gps(*pose[:2], identity['geographic_reference']),
                      'world_centre': pose[:3], 'radius_m': radius, 'height_m': height,
                      'initial_marker_plane_center': item['marker_plane_center']})
    if set(includes) != {'blueboat'}:
        raise ValueError('unexpected or missing models')
    return {'schema_version': 1, 'scene_id': identity['scene_id'], 'run_id': identity['run_id'], 'snapshot_sha256': identity.get('snapshot_sha256', identity['scene_id']),
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'geographic_reference': identity['geographic_reference'],
            'alignment': alignment or {'outcome': 'unverified'}, 'buoys': buoys}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--active-run-id', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--alignment', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(export(args.snapshot, args.scene_id, args.active_run_id, json.loads(args.alignment.read_text()) if args.alignment else None), indent=2) + '\n')
