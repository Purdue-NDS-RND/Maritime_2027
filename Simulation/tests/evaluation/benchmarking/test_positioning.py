"""Known camera geometry, degeneracy, association, and invalid-depth cases."""
from dataclasses import replace
import unittest

import cv2
import numpy as np

from maritime_localization.depth import DepthLocalizer
from maritime_localization.geometry import camera_ray
from maritime_localization.interfaces import Observation
from maritime_localization.triangulation import TriangulationLocalizer, intersect_rays, TriangulationSettings
from maritime_perception.aruco import BoundingBox

K = np.array([[400., 0., 320.], [0., 400., 240.], [0., 0., 1.]])


def observation(origin=(0., 0., 0.), points=((1., .5, 10.),), stamp=1, rotation=None, depth=False):
    transform = np.eye(4)
    transform[:3, 3] = origin
    if rotation is not None:
        transform[:3, :3] = rotation
    boxes = []
    for point in points:
        local = transform[:3, :3].T @ (np.array(point)-origin)
        pixel = K @ (local / local[2])
        boxes.append(BoundingBox(1, "red", pixel[0], pixel[1], 20., 20.))
    return Observation(stamp, "optical", tuple(boxes), K, (),
                       np.full((480, 640), 10., np.float32) if depth else None, transform, "map")


class DepthTests(unittest.TestCase):
    def test_optical_z_and_transformed_off_axis_point(self):
        rotation = np.array([[0., 0., 1.], [-1., 0., 0.], [0., -1., 0.]])
        estimate, = DepthLocalizer().process(observation((4., 5., 1.), ((14., 4., .5),), rotation=rotation, depth=True))
        np.testing.assert_allclose(estimate.position_m, [14., 4.], atol=1e-8)
        self.assertIsNone(estimate.track_id)

    def test_invalid_depth_holes_and_outliers(self):
        for value in (np.nan, np.inf, 0., -1., 100.):
            obs = observation(depth=True)
            obs.depth_m[:] = value
            self.assertEqual(DepthLocalizer().process(obs), [])
        obs = observation(depth=True)
        obs.depth_m[260, 360] = np.nan
        obs.depth_m[259, 359] = 70.
        estimate, = DepthLocalizer().process(obs)
        np.testing.assert_allclose(estimate.position_m, [1., .5])

    def test_mixed_surfaces_rejected(self):
        obs = observation(depth=True)
        obs.depth_m[:, 360:] = 20.
        self.assertEqual(DepthLocalizer().process(obs), [])

    def test_edge_clipping_and_outside_image(self):
        obs = observation(depth=True)
        edge = BoundingBox(1, "red", 0., 0., 20., 20.)
        self.assertEqual(len(DepthLocalizer().process(replace(obs, boxes=(edge,)))), 1)
        self.assertEqual(DepthLocalizer().process(replace(obs, boxes=(replace(edge, center_x=-1.),))), [])

    def test_distortion_is_undone(self):
        obs = observation(depth=True)
        distortion = (.2, -.01, .001, -.002, 0.)
        pixel, _ = cv2.projectPoints(np.array([[1., .5, 10.]]), np.zeros(3), np.zeros(3), K, np.array(distortion))
        x, y = pixel.reshape(2)
        box = replace(obs.boxes[0], center_x=x, center_y=y)
        estimate, = DepthLocalizer().process(replace(obs, boxes=(box,), distortion=distortion))
        np.testing.assert_allclose(estimate.position_m, [1., .5], atol=1e-6)
        with self.assertRaisesRegex(ValueError, "Unsupported distortion"):
            DepthLocalizer().process(replace(obs, distortion_model="unknown"))

    def test_missing_depth_or_pose_fails(self):
        with self.assertRaises(ValueError):
            DepthLocalizer().process(observation())
        with self.assertRaises(ValueError):
            DepthLocalizer().process(replace(observation(depth=True), camera_to_reference=None))


class TriangulationTests(unittest.TestCase):
    def test_known_static_target_recovers_xy_without_depth(self):
        method = TriangulationLocalizer()
        outputs = []
        for index in range(25):
            outputs += method.process(observation((index*.1, 0., 0.), stamp=index*100_000_000))
        self.assertGreater(len(outputs), 5)
        for estimate in outputs:
            np.testing.assert_allclose(estimate.position_m, [1., .5], atol=1e-8)
            self.assertEqual(estimate.track_id, "track-1")

    def test_rotating_translated_camera_preserves_reference_coordinates(self):
        method = TriangulationLocalizer()
        outputs = []
        for index in range(25):
            theta = index*.01
            rotation = np.array([[np.cos(theta), 0., np.sin(theta)], [0., 1., 0.],
                                 [-np.sin(theta), 0., np.cos(theta)]])
            outputs += method.process(observation((index*.1, .2, 0.), rotation=rotation,
                                                   stamp=index*100_000_000))
        self.assertGreater(len(outputs), 5)
        for estimate in outputs:
            np.testing.assert_allclose(estimate.position_m, [1., .5], atol=1e-8)

    def test_two_views_and_repeated_positions_do_not_establish_range(self):
        settings = TriangulationSettings()
        def view(x):
            origin = np.array([x, 0., 0.])
            direction = np.array([1., .5, 10.])-origin
            return origin, direction / np.linalg.norm(direction)
        self.assertIsNone(intersect_rays([view(0), view(2)], settings))
        self.assertIsNone(intersect_rays([view(0), view(2), view(2)], settings))

    def test_pure_rotation_and_forward_motion_have_no_range(self):
        for rotating in (True, False):
            method = TriangulationLocalizer()
            for index in range(12):
                theta = index*.01
                rotation = np.array([[np.cos(theta), 0., np.sin(theta)], [0., 1., 0.],
                                     [-np.sin(theta), 0., np.cos(theta)]]) if rotating else None
                obs = observation((0., 0., 0. if rotating else index*.1),
                                  points=((0., 0., 10.),), rotation=rotation, stamp=index)
                self.assertEqual(method.process(obs), [])

    def test_same_category_buoys_stay_separate_when_order_changes(self):
        method = TriangulationLocalizer()
        outputs = []
        for index in range(25):
            obs = observation((index*.1, 0., 0.), ((-1., .5, 10.), (2., .5, 10.)), index*100_000_000)
            outputs += method.process(replace(obs, boxes=obs.boxes[::-1]) if index % 2 else obs)
        identifiers = {estimate.track_id for estimate in outputs}
        self.assertEqual(len(identifiers), 2)
        for identifier in identifiers:
            xy = np.array([e.position_m for e in outputs if e.track_id == identifier])
            np.testing.assert_allclose(xy, np.tile(xy[0], (len(xy), 1)), atol=1e-8)
        self.assertEqual({round(e.position_m[0]) for e in outputs}, {-1, 2})

    def test_ambiguous_match_is_withheld(self):
        method = TriangulationLocalizer()
        method.process(observation(points=((-0.01, 0., 10.), (.01, 0., 10.))))
        self.assertEqual(method.process(observation((.1, 0., 0.), points=((0., 0., 10.),), stamp=2)), [])
        self.assertEqual(len(method.tracks), 2)
        self.assertTrue(all(track.last_seen_ns == 1 for track in method.tracks))

    def test_bad_intersections_rejected(self):
        def ray(origin, point):
            origin, point = np.array(origin, float), np.array(point, float)
            direction = point-origin
            return origin, direction / np.linalg.norm(direction)
        settings = TriangulationSettings()
        views = [ray((0, 0, 0), (1, 0, 10)), ray((1, 0, 0), (1, 0, 10)),
                 ray((2, 0, 0), (1, 0, 10))]
        self.assertIsNone(intersect_rays([*views, ray((2, 0, 0), (4, 4, 10))], settings))
        self.assertIsNone(intersect_rays([(o, -d) for o, d in views], settings))
        self.assertIsNone(intersect_rays([ray((0, 0, 0), (0, 0, 100)), ray((10, 0, 0), (0, 0, 100)), ray((20, 0, 0), (0, 0, 100))], settings))

    def test_reset_expiry_and_clock_rewind(self):
        method = TriangulationLocalizer()
        method.process(observation(stamp=100))
        method.process(observation(stamp=4_000_000_100))
        self.assertEqual(len(method.tracks), 1)
        self.assertEqual(method.tracks[0].identifier, "track-2")
        method.process(observation(stamp=1))
        self.assertEqual(method.tracks[0].identifier, "track-1")
        method.reset()
        self.assertEqual(method.tracks, [])

    def test_depth_is_forbidden(self):
        with self.assertRaisesRegex(ValueError, "must not include depth"):
            TriangulationLocalizer().process(observation(depth=True))

    def test_equidistant_ray(self):
        obs = observation()
        distortion = np.array([.01, -.002, 0., 0.])
        pixel, _ = cv2.fisheye.projectPoints(np.array([[[1., .5, 10.]]]), np.zeros(3), np.zeros(3), K, distortion)
        box = replace(obs.boxes[0], center_x=pixel[0, 0, 0], center_y=pixel[0, 0, 1])
        ray = camera_ray(replace(obs, distortion_model="equidistant", distortion=tuple(distortion)), box)
        np.testing.assert_allclose(ray, [.1, .05, 1.], atol=1e-8)


if __name__ == "__main__":
    unittest.main()
