"""Camera cadence overrides must preserve every other model field."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_camera_rate', ROOT/'scripts/configure_camera_rate.py')
rate_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rate_config)


class CameraRateTests(unittest.TestCase):
    def test_only_camera_cadence_changes_for_both_boats(self):
        for name, count in [('blueboat_rgbd', 1), ('blueboat_dual_rgbd', 2)]:
            for rate in (15., 30.):
                with self.subTest(name=name, rate=rate), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source = root/'source'
                    source.mkdir()
                    fixture = ET.parse(ROOT/f'models/{name}/camera_payload.sdf').getroot()
                    link = fixture.find('.//link')
                    ET.SubElement(ET.SubElement(link, 'inertial'), 'mass').text = '42'
                    imu = ET.SubElement(link, 'sensor', name='imu', type='imu')
                    ET.SubElement(imu, 'update_rate').text = '1000'
                    ET.SubElement(fixture.find('model'), 'plugin', name='dynamics', filename='native')
                    content = ET.tostring(fixture)
                    (source/'model.sdf').write_bytes(content)
                    (source/'model.config').write_text('<model><name>boat</name></model>')
                    output = root/'output'
                    metadata = rate_config.configure(source, output, rate)
                    expected = ET.fromstring(content)
                    fields = expected.findall('.//sensor[@type="rgbd_camera"]/update_rate')
                    self.assertEqual(len(fields), count)
                    for field in fields:
                        field.text = f'{rate:g}'
                    self.assertEqual(ET.canonicalize(ET.tostring(expected), strip_text=True),
                        ET.canonicalize((output/'model.sdf').read_text(), strip_text=True))
                    self.assertEqual((source/'model.sdf').read_bytes(), content)
                    self.assertEqual((output/'model.config').read_bytes(), (source/'model.config').read_bytes())
                    self.assertEqual(len(metadata['cameras']), count)

    def test_invalid_rate_or_missing_cameras_cannot_create_a_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'source'
            source.mkdir()
            (source/'model.sdf').write_text('<sdf><model name="boat"/></sdf>')
            for rate in (float('nan'), float('inf'), 0, 7, 61, 15):
                with self.subTest(rate=rate), self.assertRaises(ValueError):
                    rate_config.configure(source, root/'output', rate)
                self.assertFalse((root/'output').exists())


if __name__ == '__main__':
    unittest.main()
