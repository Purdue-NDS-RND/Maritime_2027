"""Water choice must affect physics and rendering without changing scene assets."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('render_water', ROOT/'scripts/render_water.py')
water = importlib.util.module_from_spec(spec)
spec.loader.exec_module(water)


class WaterTests(unittest.TestCase):
    def check_presets(self, source, directory, manifest=None):
        original = source.read_bytes()
        original_tree = ET.parse(source)
        original_boat = ET.canonicalize(ET.tostring(original_tree.find('.//include[name="blueboat"]')), strip_text=True)
        for preset, amplitude in (('calm', 0.), ('normal', .08), ('harsh', .25)):
            output = directory/f'{preset}.sdf'
            metadata = directory/'water.json'
            manifest_before = manifest.read_bytes() if manifest else None
            water.render(source, output, preset, metadata)
            tree = ET.parse(output)
            blocks = tree.findall('.//model[@name="water_surface"]//wave')
            self.assertEqual(len(blocks), 2)
            self.assertEqual([float(block.findtext('amplitude')) for block in blocks], [amplitude]*2)
            self.assertEqual({e.tag: e.text for e in blocks[0]}, {e.tag: e.text for e in blocks[1]})
            self.assertEqual(ET.canonicalize(ET.tostring(tree.find('.//include[name="blueboat"]')), strip_text=True), original_boat)
            self.assertEqual(len(tree.findall('.//include')), len(original_tree.findall('.//include')))
            self.assertEqual(json.loads(metadata.read_text())['preset'], preset)
            if manifest:
                self.assertEqual(manifest.read_bytes(), manifest_before)
        self.assertEqual(source.read_bytes(), original)

    def test_all_direct_worlds(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name in ('calm', 'waves', 'harbor', 'rgbd_base'):
                with self.subTest(world=name):
                    self.check_presets(ROOT/f'worlds/blueboat_{name}.sdf', Path(temporary))

    def test_all_buoy_scenes_keep_roster_and_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for scene in ('one', 'gate', 'multi', 'repeated_red', 'slalom'):
                source, manifest = directory/'scene.sdf', directory/'manifest.json'
                subprocess.run(['python3', str(ROOT/'scripts/render_scenario.py'),
                    '--scenario', str(ROOT/f'scenarios/{scene}.json'),
                    '--base-world', str(ROOT/'worlds/blueboat_rgbd_base.sdf'),
                    '--output-world', str(source), '--manifest', str(manifest), '--seed', '42'],
                    check=True, capture_output=True)
                roster = json.loads(manifest.read_text())['buoys']
                self.check_presets(source, directory, manifest)
                self.assertEqual(json.loads(manifest.read_text())['buoys'], roster)
                self.assertEqual(json.loads(manifest.read_text())['seed'], 42)

    def test_unsupported_world_fails_without_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory/'input.sdf'
            source.write_text('<sdf><world name="empty"/></sdf>')
            with self.assertRaisesRegex(ValueError, 'water_surface'):
                water.render(source, directory/'output.sdf', 'normal')
            self.assertFalse((directory/'output.sdf').exists())


if __name__ == '__main__':
    unittest.main()
