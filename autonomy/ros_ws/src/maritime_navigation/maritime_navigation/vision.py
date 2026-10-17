"""Metric RGB fiducial observations; marker size is a calibration input."""
import cv2
import numpy as np


def marker_positions(image, intrinsic, distortion, marker_size=.5):
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters_create()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    corners, ids, _ = cv2.aruco.detectMarkers(image, dictionary, parameters=parameters)
    if ids is None:
        return []
    half = marker_size/2
    square = np.array([[-half, half, 0], [half, half, 0],
                       [half, -half, 0], [-half, -half, 0]], dtype=np.float64)
    output = []
    for corner, marker_id in zip(corners, ids.flatten()):
        if marker_id not in (1, 2):
            continue
        points = corner.reshape(4, 2)
        if min(np.linalg.norm(points-np.roll(points, 1, axis=0), axis=1)) < 8:
            continue
        ok, rotation, translation = cv2.solvePnP(square, points.astype(float), intrinsic,
                                                distortion, flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if (not ok or not np.isfinite(translation).all()
                or translation[2, 0] <= .5 or np.linalg.norm(translation) > 16):
            continue
        projected, _ = cv2.projectPoints(square, rotation, translation, intrinsic, distortion)
        if np.sqrt(np.mean((projected.reshape(4, 2)-points)**2)) > 2:
            continue
        # Conservative radial correction from front face toward buoy centre.
        point = translation.reshape(3)
        point += .314*point/np.linalg.norm(point)
        output.append(('red' if marker_id == 1 else 'green', point))
    return output
