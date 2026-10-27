"""Camera geometry, scene selection and dynamics-preserving model generation."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class BoatModels(unittest.TestCase):
    def test_payload_geometry_and_topics(self):
        single = ET.parse(ROOT / 'models/blueboat_rgbd/camera_payload.sdf')
        dual = ET.parse(ROOT / 'models/blueboat_dual_rgbd/camera_payload.sdf')
        sensors = dual.findall('.//sensor')
        self.assertEqual(len(sensors), 2)
        for i, sensor in enumerate(sensors):
            pose = list(map(float, sensor.findtext('pose').split()))
            self.assertAlmostEqual(pose[5], (-1 if i == 0 else 1) * math.pi / 4)
            self.assertEqual(pose[:3], [.35, -.1 if i == 0 else .1, .4])
            self.assertEqual(sensor.findtext('camera/optical_frame_id'), f'camera_{i}_optical_frame')
            for field in ('horizontal_fov', 'image/width', 'image/height', 'lens/intrinsics/fx'):
                self.assertEqual(sensor.findtext('camera/' + field), single.findtext('.//camera/' + field))
        self.assertEqual(len({s.findtext('topic') for s in sensors}), 2)
        self.assertFalse(dual.findall('.//inertial') or dual.findall('.//collision'))

    def test_both_models_preserve_source_dynamics(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.sdf'
            text = '<sdf version="1.9"><model name="blueboat"><link name="base_link"><inertial><mass>42</mass></inertial><collision name="hull"/></link><plugin name="dynamics" filename="upstream"/></model></sdf>'
            source.write_text(text)
            for model, directory in [('single', 'blueboat_rgbd'), ('dual', 'blueboat_dual_rgbd')]:
                output = Path(tmp) / f'{model}.sdf'
                subprocess.run(['python3', str(ROOT / 'scripts/augment_blueboat_model.py'),
                    '--source', str(source), '--payload', str(ROOT / f'models/{directory}/camera_payload.sdf'),
                    '--output', str(output), '--expected-sha256', hashlib.sha256(text.encode()).hexdigest(),
                    '--boat-model', model], check=True, capture_output=True)
                tree = ET.parse(output)
                self.assertEqual(tree.findtext('.//mass'), '42')
                self.assertEqual(tree.find('.//plugin').attrib, {'name': 'dynamics', 'filename': 'upstream'})
                self.assertEqual(len(tree.findall('.//sensor')), 1 if model == 'single' else 2)

    def test_every_world_accepts_both_models_and_keeps_water(self):
        with tempfile.TemporaryDirectory() as tmp:
            for world in ('blueboat_waves', 'blueboat_harbor', 'blueboat_calm', 'blueboat_rgbd_base'):
                for model in ('single', 'dual'):
                    output = Path(tmp) / 'world.sdf'
                    source = ROOT / f'worlds/{world}.sdf'
                    manifest = Path(tmp) / 'manifest.json'
                    manifest.write_text(json.dumps(dict(world='blueboat_rgbd', boat_pose={})))
                    subprocess.run(['python3', str(ROOT / 'scripts/render_boat.py'), '--source', str(source),
                        '--output', str(output), '--boat-model', model, '--manifest', str(manifest)], check=True)
                    tree = ET.parse(output)
                    expected = 'model://blueboat_' + ('rgbd' if model == 'single' else 'dual_rgbd')
                    self.assertEqual(tree.findtext("./world/include[name='blueboat']/uri"), expected)
                    self.assertEqual(tree.findtext('.//amplitude'), ET.parse(source).findtext('.//amplitude'))
                    self.assertEqual(len(tree.findall("./world/plugin[@filename='gz-sim-sensors-system']")), 1)
                    metadata = json.loads(manifest.read_text())
                    self.assertEqual(metadata['world'], tree.find('world').get('name'))
                    self.assertEqual(metadata['boat_model'], model)
                    self.assertEqual(metadata['boat_pose']['y'], 3. if world == 'blueboat_harbor' else 0.)



if __name__ == '__main__':
    unittest.main()
