"""Camera geometry checks run in the autonomy image (OpenCV required)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ros_ws/src/maritime_navigation'))
try:
    import cv2
    import numpy as np
    from maritime_navigation.vision import marker_positions
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, 'Run in the autonomy image for OpenCV geometry checks')
class VisionTests(unittest.TestCase):
    def test_known_size_rgb_range_and_color(self):
        intrinsic = np.array([[600., 0, 320], [0, 600., 240], [0, 0, 1]])
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        for marker_id, color in [(1, 'red'), (2, 'green')]:
            image = np.full((480, 640), 255, dtype=np.uint8)
            image[190:290, 270:370] = cv2.aruco.drawMarker(dictionary, marker_id, 100)
            observations = marker_positions(image, intrinsic, np.zeros(5))
            self.assertEqual(len(observations), 1)
            self.assertEqual(observations[0][0], color)
            self.assertAlmostEqual(observations[0][1][2], 3.314, delta=.08)
            self.assertLess(np.linalg.norm(observations[0][1][:2]), .03)

    def test_empty_and_unrecognized_images(self):
        image = np.full((480, 640), 255, dtype=np.uint8)
        intrinsic = np.array([[600., 0, 320], [0, 600., 240], [0, 0, 1]])
        self.assertEqual(marker_positions(image, intrinsic, np.zeros(5)), [])
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        image[190:290, 270:370] = cv2.aruco.drawMarker(dictionary, 3, 100)
        self.assertEqual(marker_positions(image, intrinsic, np.zeros(5)), [])
