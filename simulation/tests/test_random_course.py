"""Full-course layout randomization: physical constraints, truth separation, replay."""
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'simulation/scripts'))
from random_course import generate, observations, expected_roles, validate_layout, surface_gap, check_compiler
from export_competition import export_objects
from shared.geometry import to_local
from gcs.app.imports import import_points
from gcs.app.course_compiler import validate_assignments


class RandomCourseTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT/'simulation/scenarios/competition.json').read_text())

    def test_repeatable_independent_source_and_all_physical_objects(self):
        before = deepcopy(self.source)
        a = generate(self.source, 42)
        self.assertEqual(a, generate(self.source, 42))
        self.assertNotEqual(a, generate(self.source, 43))
        self.assertEqual(self.source, before)
        self.assertEqual(len(a['buoys']), 23)
        self.assertEqual(len(a['props']), 6)
        self.assertEqual(a['boat_pose'], before['boat_pose'])
        for key in ('buoys', 'props'):
            for obj, source in zip(a[key], before[key]):
                self.assertEqual({k: v for k, v in obj.items() if k != 'pose'},
                                 {k: v for k, v in source.items() if k not in ('pose', 'reference_ft')})
        self.assertEqual(len(a['stations']), 10)

    def test_presets_many_seeds_have_valid_full_scene_and_role_geometry(self):
        for variation in ('mild', 'moderate', 'strong'):
            for seed in range(30):
                with self.subTest(seed=seed, variation=variation):
                    config = generate(self.source, seed, variation)
                    validate_layout(config)
                    points, ids = observations(config)
                    validate_assignments(import_points(json.dumps(points)), expected_roles(ids))
                    self.assertLessEqual(config['generation']['accepted_attempt'], 100)

    def test_explicit_rotation_rotates_every_object_station_and_footprint(self):
        a, b = [generate(self.source, 42, rotation_deg=angle) for angle in (0, 73)]
        c, s = math.cos(math.radians(73)), math.sin(math.radians(73))
        def check(p, q):
            self.assertAlmostEqual(q[0], c*p[0]-s*p[1])
            self.assertAlmostEqual(q[1], s*p[0]+c*p[1])
        for key in ('buoys', 'props'):
            for first, second in zip(a[key], b[key]):
                p, q = first['pose'], second['pose']
                check((p['x'], p['y']), (q['x'], q['y']))
                self.assertAlmostEqual(q['yaw_deg']-p['yaw_deg'], 73)
        for p, q in zip(a['stations'], b['stations']):
            check(p['world_position'], q['world_position'])

    def test_truth_never_leaks_through_import(self):
        config = generate(self.source, 7)
        points, ids = observations(config)
        self.assertEqual((points, ids), observations(config))
        self.assertEqual(len(points['points']), 29)
        self.assertEqual(set(ids.values()), {p['id'] for p in points['points']})
        for row in points['points']:
            self.assertEqual(set(row), {'id', 'latitude', 'longitude', 'object_type', 'category'})
        m = import_points(json.dumps(points))
        self.assertEqual(sum(p['object_type'] == 'buoy' and p['category'] in ('red', 'green') for p in m['buoys']), 14)
        self.assertEqual(sum(p['object_type'] == 'detector' for p in m['buoys']), 2)
        by_name = {o['name']: o for o in config['buoys']+config['props']}
        for obj in m['buoys']:
            name = next(k for k, v in ids.items() if v == obj['id'])
            xy = to_local(obj['centre'], m['geographic_reference'])
            self.assertLess(math.dist(xy, [by_name[name]['pose'][k] for k in ('x', 'y')]), 1e-8)

    def test_physical_constraints_reject_overlap_spawn_and_crossing(self):
        config = generate(self.source, 42)
        for kind in ('overlap', 'spawn', 'bounds', 'crossing', 'nan'):
            broken = deepcopy(config)
            if kind == 'overlap':
                broken['props'][0]['pose'] = deepcopy(broken['buoys'][1]['pose'])
            elif kind == 'spawn':
                broken['buoys'][0]['pose'].update(x=0, y=0)
            elif kind == 'bounds':
                broken['props'][0]['pose']['x'] = 150
            elif kind == 'nan':
                broken['props'][0]['pose']['x'] = math.nan
            else:
                by_name = {o['name']: o for o in broken['buoys']}
                a, b = by_name['evade_left_0'], by_name['evade_left_2']
                a['pose'], b['pose'] = b['pose'], a['pose']
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_layout(broken)
        box = {'size_m': [4, 6, .5], 'pose': {'x': 0, 'y': 0, 'yaw_deg': 45}}
        circle = {'radius_m': .24, 'pose': {'x': 0, 'y': 0}}
        self.assertLess(surface_gap(box, circle), 0)
        self.assertLess(surface_gap(box, box), 0)

    def test_invalid_inputs(self):
        for kwargs in ({'seed': True}, {'seed': 1.2}, {'seed': 1, 'variation': 'anything'},
                       {'seed': 1, 'rotation_deg': math.inf}, {'seed': 1, 'rotation_deg': True}):
            with self.assertRaises(ValueError):
                generate(self.source, **kwargs)

    def test_renderer_seed_matches_bundle_and_exports_collision_geometry(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for seed in (None, 42):
                command = [sys.executable, str(ROOT/'simulation/scripts/render_scenario.py'),
                           '--scenario', str(ROOT/'simulation/scenarios/competition.json'),
                           '--base-world', str(ROOT/'simulation/worlds/blueboat_rgbd_base.sdf'),
                           '--output-world', str(directory/'world.sdf'),
                           '--manifest', str(directory/'manifest.json'), '--cameras', 'off']
                if seed is not None:
                    command += ['--course-seed', str(seed), '--variation', 'moderate']
                subprocess.run(command, check=True, capture_output=True)
                manifest = json.loads((directory/'manifest.json').read_text())
                world = ET.parse(directory/'world.sdf')
                result = export_objects(world, manifest, {'latitude': 51.566151, 'longitude': -4.034345})
                result['geographic_reference'] = {'latitude': 51.566151, 'longitude': -4.034345}
                if seed is None:
                    self.assertNotIn('generation', manifest)
                    continue
                config = generate(self.source, seed)
                self.assertEqual(manifest['generation'], config['generation'])
                objects = {o['id']: o for o in result['buoys']+result['obstacles']}
                for obj in config['buoys']+config['props']:
                    record = objects[obj['name']]
                    self.assertEqual(record['world_centre'], [obj['pose'][k] for k in ('x', 'y', 'z')])
                    if 'size_m' in obj:
                        self.assertEqual(record['type'], 'polygon')
                        self.assertEqual(len(record['footprint']), 4)

    def test_recognition_of_unhinted_generated_full_maps(self):
        for variation, seed in (('mild', 0), ('moderate', 42), ('strong', 1)):
            with self.subTest(variation=variation, seed=seed):
                config = generate(self.source, seed, variation)
                points, ids = observations(config)
                report = check_compiler(points, ids)
                self.assertIsNotNone(report['intended_joint_rank'])
                self.assertLessEqual(report['intended_joint_rank'], 5)
                self.assertLessEqual(report['result']['expanded_states'], 200000)
                # Truncation is reported even when the intended course is found.
                self.assertTrue(report['result']['search_exhausted'])

    def test_cli_bundle_replays_renderer_and_refuses_overwrite(self):
        logs = ROOT/'simulation/logs'
        logs.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=logs) as temporary:
            output = Path(temporary)/'bundle'
            command = [sys.executable, str(ROOT/'simulation/scripts/generate_course.py'),
                       '--seed', '51', '--variation', 'strong', '--rotation-deg', '73',
                       '--check-compiler', '--output', str(output)]
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual({p.name for p in output.iterdir()},
                             {'scenario.json', 'observations.json', 'truth.json', 'manifest.json',
                              'world.sdf', 'preview.svg', 'preview.html', 'compile-check.json'})
            ET.parse(output/'preview.svg')
            config = generate(self.source, 51, 'strong', 73)
            self.assertEqual(json.loads((output/'scenario.json').read_text()), json.loads(json.dumps(config)))
            report = json.loads((output/'compile-check.json').read_text())
            self.assertIsNotNone(report['intended_joint_rank'])
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            retry = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(retry.returncode, 0)
            self.assertIn('already exists', retry.stderr)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
            replay = Path(temporary)/'replay.sdf'
            subprocess.run([sys.executable, str(ROOT/'simulation/scripts/render_scenario.py'),
                            '--scenario', str(ROOT/'simulation/scenarios/competition.json'),
                            '--course-seed', '51', '--variation', 'strong', '--rotation-deg', '73',
                            '--base-world', str(ROOT/'simulation/worlds/blueboat_rgbd_base.sdf'),
                            '--output-world', str(replay), '--manifest', str(Path(temporary)/'replay.json'),
                            '--cameras', 'off'], check=True, capture_output=True)
            self.assertEqual(replay.read_bytes(), before['world.sdf'])


if __name__ == '__main__':
    unittest.main()
