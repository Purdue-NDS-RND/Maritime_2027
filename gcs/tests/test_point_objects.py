"""Centre-based drone imports, clearance, preferences and workspace migration."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from gcs.app.imports import import_points, point_map
from gcs.app.workspace import Workspace
from shared.clearance import validate_route
from shared.course import Course
from shared.geometry import to_gps
from shared.object_map import validate_map


class PointObjectsTests(unittest.TestCase):
    reference = {'latitude': 51.5, 'longitude': -4}

    def gps(self, x, y):
        return to_gps(x, y, self.reference)

    def point(self, x, y, **extra):
        return {**self.gps(x, y), **extra}

    def draft(self):
        return {'task': 'custom', 'start': self.gps(-5, 0), 'finish': self.gps(5, 0),
                'waypoints': [self.gps(5, 0)], 'speed_m_s': .5, 'clearance_m': 1,
                'preferred_buffer_m': 3, 'finish_radius_m': .5, 'sizes_confirmed': True,
                'passages': []}

    def test_explicit_and_missing_unknown_have_no_dimensions(self):
        rows = [self.point(0, 0, object_type='unknown'), self.point(4, 0),
                self.point(8, 0, id='tower', object_type='detector')]
        result = import_points(json.dumps({'points': rows}))
        self.assertEqual([o['object_type'] for o in result['buoys']], ['unknown', 'unknown', 'detector'])
        self.assertEqual([o['id'] for o in result['buoys']], ['point_1', 'point_2', 'tower'])
        for obj in result['buoys']:
            self.assertEqual(obj['type'], 'point')
            self.assertTrue({'radius_m', 'height_m', 'footprint'}.isdisjoint(obj))
        self.assertEqual(result['imported_points'], rows)
        csv_map = import_points('latitude,longitude,object_type\n51.5,-4,unknown\n', 'csv')
        self.assertEqual(csv_map['buoys'][0]['object_type'], 'unknown')

    def test_legacy_dimensions_do_not_add_hidden_point_clearance(self):
        rows = [self.point(0, 1.1, radius_m=4, height_m=2)]
        object_map = import_points(json.dumps({'points': rows}))
        draft = self.draft()
        self.assertTrue(validate_route(object_map, draft)['valid'])
        draft['clearance_m'] = 1.2
        self.assertFalse(validate_route(object_map, draft)['valid'])
        # Original input remains available for comparison, but not geometry.
        self.assertEqual(object_map['imported_points'], rows)

    def test_tower_cost_decreases_with_centre_distance_and_hard_never_yields(self):
        object_map = import_points(json.dumps([self.point(0, 0, object_type='detector')]))
        draft = self.draft()
        draft['tower_avoidance'] = {'hard_m': 1, 'soft_m': 5, 'strength': 10, 'overrides': {}}
        course = Course(object_map, draft)
        costs = [course.tower_cost((0, distance), (0, distance)) for distance in (1.1, 2, 4, 5.1)]
        self.assertTrue(all(a > b for a, b in zip(costs, costs[1:])))
        for distance, expected in ((.9, False), (1.1, True)):
            draft.update(start=self.gps(-5, distance), finish=self.gps(5, distance), waypoints=[self.gps(5, distance)])
            result = validate_route(object_map, draft)
            self.assertEqual(result['valid'], expected)
        self.assertTrue(result['tower_shortfalls'])

    def test_start_and_stopping_disk_use_the_same_centre_distance(self):
        object_map = import_points(json.dumps([self.point(0, 0)]))
        draft = self.draft()
        draft['start'] = self.gps(.9, 0)
        self.assertFalse(validate_route(object_map, draft)['valid'])
        draft.update(start=self.gps(5, 0), finish=self.gps(1.4, 0), waypoints=[self.gps(1.4, 0)])
        result = validate_route(object_map, draft)
        self.assertTrue(any('finish area' in error['reason'] for error in result['errors']))
        draft.update(finish=self.gps(1.6, 0), waypoints=[self.gps(1.6, 0)])
        self.assertTrue(validate_route(object_map, draft)['valid'])

    def test_migration_backs_up_original_and_revokes_approval_without_losing_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(directory)
            state = workspace.read()
            original = import_points(json.dumps([self.point(0, 0)]))
            original['buoys'][0].update(type='cylinder', radius_m=.5, height_m=1, size_assumed=True)
            route = self.draft()
            state.update(map=original, original_map=deepcopy(original), draft=route,
                         tasks={'manual': deepcopy(route)}, course={}, approval={'retained_in_backup': True})
            path = Path(directory) / 'workspace.json'
            before = json.dumps(state, indent=2).encode()
            path.write_bytes(before)
            migrated = Workspace(directory).read()
            backup = next(Path(directory).glob('workspace-before-point-objects-*.json'))
            self.assertEqual(backup.read_bytes(), before)
            self.assertEqual(migrated['original_map'], original)
            self.assertEqual(migrated['map'], point_map(original))
            self.assertIsNone(migrated['approval'])
            self.assertEqual(migrated['draft']['waypoints'], route['waypoints'])
            self.assertEqual(migrated['tasks']['manual']['waypoints'], route['waypoints'])
            self.assertFalse(migrated['draft']['sizes_confirmed'])
            again = Workspace(directory).read()
            self.assertEqual(again, migrated)
            self.assertEqual(len(list(Path(directory).glob('workspace-before-point-objects-*.json'))), 1)

    def test_point_geometry_cannot_hide_a_radius(self):
        object_map = import_points(json.dumps([self.point(0, 0)]))
        object_map['buoys'][0]['radius_m'] = .5
        with self.assertRaisesRegex(ValueError, 'without physical dimensions'):
            validate_map(object_map)
