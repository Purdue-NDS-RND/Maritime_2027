"""Retained camera geometry: distortion recovery and invalid calibration gates."""
from dataclasses import replace
import unittest

import cv2
import numpy as np

from maritime_localization.geometry import camera_ray, validate_observation
from maritime_localization.interfaces import Observation
from maritime_perception.aruco import BoundingBox


class CameraGeometryTests(unittest.TestCase):
    def setUp(self):
        self.matrix = np.array([[400., 0., 320.], [0., 400., 240.], [0., 0., 1.]])
        self.observation = Observation(1, 'optical', self.matrix, (), np.eye(4), 'map')

    def test_distorted_pixel_recovers_original_optical_ray(self):
        point = np.array([[[1., .5, 10.]]])
        for model, coefficients in [('plumb_bob', (.2, -.01, .001, -.002, 0.)),
                                    ('equidistant', (.01, -.002, 0., 0.))]:
            with self.subTest(model=model):
                distortion = np.array(coefficients)
                project = cv2.fisheye.projectPoints if model == 'equidistant' else cv2.projectPoints
                pixel, _ = project(point, np.zeros(3), np.zeros(3), self.matrix, distortion)
                x, y = pixel.reshape(2)
                box = BoundingBox(1, 'red', x, y, 20., 20.)
                observation = replace(self.observation, distortion_model=model, distortion=coefficients)
                validate_observation(observation)
                np.testing.assert_allclose(camera_ray(observation, box), [.1, .05, 1.], atol=1e-8)

    def test_invalid_calibration_or_reference_transform_is_rejected(self):
        for changes in [dict(distortion_model='unknown'), dict(camera_to_reference=None),
                        dict(camera_matrix=np.zeros((3, 3))), dict(reference_frame='')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_observation(replace(self.observation, **changes))
