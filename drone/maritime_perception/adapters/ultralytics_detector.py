"""Optional real detector integration. No weights download or synthetic fallback."""
from pathlib import Path

import numpy as np

from ..validation import Unavailable


class UltralyticsDetector:
    def __init__(self, weights, class_map):
        if not Path(weights).is_file():
            raise Unavailable("detector_weights_unavailable")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise Unavailable("ultralytics_unavailable") from exc
        self.model = YOLO(str(Path(weights).resolve()), task="detect")
        self.class_map = class_map

    def detect(self, image, metadata, *, pixel_sigma_px, reference_method="bbox_centre_unvalidated"):
        if not np.isfinite(pixel_sigma_px) or pixel_sigma_px <= 0:
            raise Unavailable("pixel_uncertainty_required")
        if image is None or image.ndim != 3 or image.shape[2] != 3:
            raise Unavailable("invalid_detector_image")
        if metadata["input_image_size"] != [image.shape[1], image.shape[0]]:
            raise Unavailable("detector_resolution_mismatch")
        result = self.model.predict(source=image, verbose=False)[0]
        detections = []
        for index, box in enumerate(result.boxes):
            class_id = int(box.cls.item())
            if class_id not in self.class_map:
                continue
            xyxy = box.xyxy[0].cpu().numpy()
            detections.append({"id": f"{metadata['id']}_d{index}", "class_id": self.class_map[class_id],
                               "pixel_uv": ((xyxy[:2]+xyxy[2:])/2).tolist(),
                               "pixel_covariance": (np.eye(2)*pixel_sigma_px**2).tolist(),
                               "reference_method": reference_method})
        # Ultralytics restores predictions to source-image coordinates. Metadata stamp is unchanged.
        return dict(metadata, detections=detections)
