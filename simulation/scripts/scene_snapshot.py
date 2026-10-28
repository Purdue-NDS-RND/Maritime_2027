#!/usr/bin/env python3
"""Capture and verify run inputs inside the simulator before Gazebo starts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scene_geometry_id(directory, identity):
    directory = Path(directory)
    world = ET.parse(directory / 'world.sdf')
    for plugin in list(world.findall('./world/plugin')):
        if plugin.get('name') == 'maritime::RunEvidence':
            world.find('world').remove(plugin)
    relevant = {name: sha for name, sha in identity['files'].items()
                if name.startswith('models/') or name in ('ArduPilotPlugin.cc', 'SIM_JSON.cpp', 'SIM_Aircraft.cpp', 'Location.cpp')}
    payload = {'world': ET.tostring(world.getroot(), encoding='unicode'),
               'files': relevant, 'reference': identity['geographic_reference']}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def verify(directory):
    directory = Path(directory)
    identity = json.loads((directory / 'scene.json').read_text())
    modern = 'snapshot_sha256' in identity
    key = 'snapshot_sha256' if modern else 'scene_id'
    expected = identity.pop(key)
    actual = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if actual != expected:
        raise ValueError('scene identity was modified')
    for name, sha in identity['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe snapshot path')
        if digest(directory / name) != sha:
            raise ValueError(f'scene file changed: {name}')
    if modern and identity['scene_id'] != scene_geometry_id(directory, identity):
        raise ValueError('physical scene identity mismatch')
    identity[key] = expected
    return identity


def capture(world_path, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / 'scene.json').exists():
        raise ValueError('refusing to replace a scene snapshot')
    world_path = Path(world_path)
    tree = ET.parse(world_path)
    roots = [Path(p) for p in os.environ['GZ_SIM_RESOURCE_PATH'].split(':')]
    copied = set()

    def copy_model(name):
        if name in copied:
            return
        if not name or Path(name).name != name:
            raise ValueError('unsupported model URI')
        candidates = [p / name for p in roots if (p / name / 'model.sdf').is_file()]
        if not candidates:
            raise ValueError(f'missing model: {name}')
        source = candidates[0]
        shutil.copytree(source, directory / 'models' / name)
        copied.add(name)
        model = ET.parse(source / 'model.sdf')
        for uri in model.findall('.//uri'):
            text = uri.text or ''
            if text.startswith(('model://', 'models://')):
                dependency = text.split('://', 1)[1].split('/')[0]
                if dependency != name:
                    copy_model(dependency)

    for uri in tree.findall('.//mesh/uri'):
        text = uri.text or ''
        if text.startswith(('model://', 'models://')):
            copy_model(text.split('://', 1)[1].split('/')[0])
    for include in tree.findall('.//include'):
        uri = include.findtext('uri', '')
        if not uri.startswith('model://'):
            raise ValueError(f'unsupported include: {uri}')
        copy_model(uri[8:])
    if os.environ.get('SCENARIO') == 'slalom':
        plugin = ET.SubElement(tree.find('world'), 'plugin',
                               filename='libRunEvidence.so', name='maritime::RunEvidence')
        ET.SubElement(plugin, 'path').text = str(directory.parent / 'truth.jsonl')
    tree.write(directory / 'world.sdf', encoding='utf-8', xml_declaration=True)
    # Mesh references in the copied BlueBoat point at the unmodified base model.
    if any(name.startswith('blueboat_') for name in copied):
        copy_model('blueboat')
    manifest = Path('/sim/generated-worlds/active.manifest.json')
    if os.environ.get('SCENARIO', 'none') != 'none':
        shutil.copy2(manifest, directory / 'manifest.json')
    shutil.copy2('/opt/boat_sim/config/blueboat.parm', directory / 'blueboat.parm')
    shutil.copy2('/usr/local/bin/start-sim.sh', directory / 'start-sim.sh')
    for source, name in [('/opt/ardupilot_gazebo/src/ArduPilotPlugin.cc', 'ArduPilotPlugin.cc'),
                         ('/opt/ardupilot/libraries/SITL/SIM_JSON.cpp', 'SIM_JSON.cpp'),
                         ('/opt/ardupilot/libraries/SITL/SIM_Aircraft.cpp', 'SIM_Aircraft.cpp'),
                         ('/opt/ardupilot/libraries/AP_Common/Location.cpp', 'Location.cpp')]:
        shutil.copy2(source, directory / name)
    files = {str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    identity = {'schema_version': 1, 'run_id': os.environ['RUN_ID'],
                'captured_at': datetime.now(timezone.utc).isoformat(), 'files': files,
                'settings': {key: os.environ.get(key) for key in
                             ('WORLD', 'SCENARIO', 'CAMERA_ENABLED', 'CAMERA_FPS', 'BOAT_MODEL', 'WIPE_PARAMS')},
                'geographic_reference': {'latitude': 51.566151, 'longitude': -4.034345},
                'alignment': 'unverified'}
    identity['scene_id'] = scene_geometry_id(directory, identity)
    identity['snapshot_sha256'] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    (directory / 'scene.json').write_text(json.dumps(identity, indent=2) + '\n')
    verify(directory)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--world', type=Path)
    args = parser.parse_args()
    if args.world:
        capture(args.world, args.directory)
    else:
        print(json.dumps(verify(args.directory)))
