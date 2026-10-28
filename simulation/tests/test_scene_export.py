import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'simulation/scripts')]
from shared.geometry import to_gps, to_local
from scene_snapshot import verify


class CoordinatesTests(unittest.TestCase):
    def test_axes_and_roundtrip(self):
        ref = {'latitude': 51.566151, 'longitude': -4.034345}
        self.assertGreater(to_gps(10, 0, ref)['longitude'], ref['longitude'])
        self.assertGreater(to_gps(0, 10, ref)['latitude'], ref['latitude'])
        for point in ((0, 0), (30, 10), (-8, 18)):
            actual = to_local(to_gps(*point, ref), ref)
            for a, b in zip(actual, point):
                self.assertAlmostEqual(a, b, places=7)

    def test_modified_identity_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'scene.json').write_text(json.dumps({'scene_id': 'fake', 'files': {}}))
            with self.assertRaisesRegex(ValueError, 'modified'):
                verify(directory)

    def test_cameras_off_preserves_buoys(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            for setting in ('on', 'off'):
                world, manifest = Path(directory, setting + '.sdf'), Path(directory, setting + '.json')
                subprocess.run([sys.executable, str(ROOT / 'simulation/scripts/render_scenario.py'),
                                '--scenario', str(ROOT / 'simulation/scenarios/slalom.json'),
                                '--base-world', str(ROOT / 'simulation/worlds/blueboat_rgbd_base.sdf'),
                                '--output-world', str(world), '--manifest', str(manifest), '--cameras', setting], check=True, capture_output=True)
                outputs.append(json.loads(manifest.read_text())['buoys'])
                if setting == 'off':
                    tree = ET.parse(world)
                    self.assertEqual(tree.findtext('./world/include/uri'), 'model://blueboat')
                    self.assertFalse(any('sensors-system' in p.get('filename', '') for p in tree.findall('./world/plugin')))
            self.assertEqual(*outputs)

class StableSceneTests(unittest.TestCase):
    def test_geometry_identity_excludes_recorder_destination(self):
        from scene_snapshot import scene_geometry_id
        with tempfile.TemporaryDirectory() as directory:
            identity={'files':{},'geographic_reference':{'latitude':1,'longitude':2}}
            path=Path(directory,'world.sdf')
            path.write_text('<sdf><world name="test"><plugin name="maritime::RunEvidence"><path>run1/truth</path></plugin></world></sdf>')
            first=scene_geometry_id(directory,identity)
            path.write_text('<sdf><world name="test"><plugin name="maritime::RunEvidence"><path>run2/truth</path></plugin></world></sdf>')
            self.assertEqual(first,scene_geometry_id(directory,identity))
            identity['geographic_reference']['latitude']=2
            self.assertNotEqual(first,scene_geometry_id(directory,identity))

class ExportTests(unittest.TestCase):
    def test_export_and_mismatched_active_scene_rejection(self):
        import hashlib
        import shutil
        import subprocess
        from export_map import export
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run([sys.executable,str(ROOT/'simulation/scripts/render_scenario.py'),
                            '--scenario',str(ROOT/'simulation/scenarios/slalom.json'),
                            '--base-world',str(ROOT/'simulation/worlds/blueboat_rgbd_base.sdf'),
                            '--output-world',str(root/'world.sdf'),'--manifest',str(root/'manifest.json'),
                            '--cameras','off'],check=True,capture_output=True)
            for i in (1,2):
                dest=root/'models'/f'aruco_buoy_id{i}';dest.mkdir(parents=True)
                shutil.copyfile(ROOT/f'simulation/models/aruco_buoy_id{i}/model.sdf',dest/'model.sdf')
            boat=root/'models/blueboat';boat.mkdir()
            (boat/'model.sdf').write_text('''<sdf><model><link name="imu_link"/><plugin name="ArduPilotPlugin">
                <gazeboXYZToNED degrees="true">0 0 0 180 0 90</gazeboXYZToNED>
                <modelXYZToAirplaneXForwardZDown degrees="true">0 0 0 180 0 0</modelXYZToAirplaneXForwardZDown>
                </plugin></model></sdf>''')
            identity={'run_id':'test-run','alignment':'unverified','geographic_reference':{'latitude':51.566151,'longitude':-4.034345},
                      'files':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()for p in root.rglob('*')if p.is_file()}}
            identity['scene_id']=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            (root/'scene.json').write_text(json.dumps(identity))
            result=export(root,identity['scene_id'],'test-run')
            self.assertEqual(len(result['buoys']),8)
            self.assertEqual(result['buoys'][0]['world_centre'],[7,-2,0])
            self.assertNotEqual(result['buoys'][0]['initial_marker_plane_center']['x'],7)
            self.assertEqual(result['buoys'][0]['radius_m'],.24)
            with self.assertRaisesRegex(ValueError,'active simulator'):
                export(root,identity['scene_id'],'stale-run')
            with self.assertRaisesRegex(ValueError,'active simulator'):
                export(root,'another-scene','test-run')
            (boat/'model.sdf').write_text('<sdf/>')
            with self.assertRaisesRegex(ValueError,'changed'):
                export(root,identity['scene_id'],'test-run')
