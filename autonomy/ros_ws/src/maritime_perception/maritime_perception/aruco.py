"""Detect marker rectangles in pixels. No calibration, depth, or pose input."""

from dataclasses import dataclass

import cv2
import numpy as np


CATEGORIES = ("white", "red", "green", "blue")


@dataclass(frozen=True)
class BoundingBox:
    marker_id: int  # Category code, never a physical buoy/track identity.
    category: str
    center_x: float
    center_y: float
    width: float
    height: float


class ArucoBoxDetector:
    def __init__(self, dictionary="DICT_4X4_50", marker_ids=(0, 1, 2, 3),
                 marker_categories=CATEGORIES):
        if not dictionary.startswith("DICT_") or not hasattr(cv2.aruco, dictionary):
            raise ValueError(f"Unknown ArUco dictionary: {dictionary}")
        if (not marker_ids or len(marker_ids) != len(marker_categories)
                or len(set(marker_ids)) != len(marker_ids)
                or any(category not in CATEGORIES for category in marker_categories)):
            raise ValueError("Use unique marker IDs and one supported category per ID")
        codebook = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
        if any(type(marker_id) is not int or not 0 <= marker_id < len(codebook.bytesList)
               for marker_id in marker_ids):
            raise ValueError("Marker IDs must be integers within the selected dictionary")
        self.categories = dict(zip(marker_ids, marker_categories))
        self.dictionary = codebook
        self.parameters = cv2.aruco.DetectorParameters_create()

    def detect(self, image):
        """Accept uint8 BGR or grayscale; return only recognized marker boxes."""
        if (image.dtype != np.uint8 or image.ndim not in (2, 3)
                or (image.ndim == 3 and image.shape[2] != 3)):
            raise ValueError("Expected a uint8 grayscale or BGR image")
        corners, identifiers, _ = cv2.aruco.detectMarkers(
            image, self.dictionary, parameters=self.parameters)
        boxes = []
        if identifiers is None:
            return boxes
        for points, identifier in zip(corners, identifiers.flatten()):
            marker_id = int(identifier)
            if marker_id not in self.categories:
                continue
            # Corners are discarded here. All downstream algorithms get boxes.
            minimum = points.reshape(4, 2).min(axis=0)
            maximum = points.reshape(4, 2).max(axis=0)
            center = (minimum + maximum) / 2
            size = maximum - minimum
            boxes.append(BoundingBox(marker_id, self.categories[marker_id],
                                     float(center[0]), float(center[1]),
                                     float(size[0]), float(size[1])))
        return sorted(boxes, key=lambda box: (box.marker_id, box.center_x, box.center_y))


def annotate(image, boxes):
    """Return an independent BGR debug image; never change the source image."""
    result = image.copy()
    for box in boxes:
        top_left = (round(box.center_x - box.width / 2), round(box.center_y - box.height / 2))
        bottom_right = (round(box.center_x + box.width / 2), round(box.center_y + box.height / 2))
        cv2.rectangle(result, top_left, bottom_right, (0, 255, 0), 2)
        cv2.putText(result, f"{box.category} ({box.marker_id})", top_left,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
    return result
