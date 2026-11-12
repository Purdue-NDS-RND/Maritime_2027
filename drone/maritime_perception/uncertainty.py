"""First-order propagation with named common unit-normal error sources."""
import numpy as np
from scipy.stats import chi2

from .contracts import Observation
from .validation import covariance, root_cov


def numerical_jacobian(function, dimensions=20):
    steps = np.r_[np.full(2, 1e-3), np.full(3, 1e-4), np.full(3, 1e-6),
                  np.full(4, 1e-3), np.full(3, 1e-4), np.full(3, 1e-6), 1e-4, 1e-5]
    return np.column_stack([(function(np.eye(dimensions)[i]*steps[i])-
                             function(-np.eye(dimensions)[i]*steps[i]))/(2*steps[i])
                            for i in range(dimensions)])


def ellipse(cov, probability=.95):
    cov = covariance(cov, 2)
    values, vectors = np.linalg.eigh(cov)
    scale = chi2.ppf(probability, 2)
    angle = None if np.isclose(values[0], values[1], atol=1e-12, rtol=1e-7) else float(np.arctan2(vectors[1, 1], vectors[0, 1]) % np.pi)
    return {"probability": probability, "semi_major_m": float(np.sqrt(scale*max(values[1], 0))),
            "semi_minor_m": float(np.sqrt(scale*max(values[0], 0))), "angle_ccw_from_east_rad": angle}


class ProjectionUncertainty:
    def __init__(self, projector):
        self.projector = projector

    def propagate(self, pixel, pixel_cov, pose, frame, detection, clock):
        p = self.projector
        mean = p.project(pixel, pose, frame["image_domain"])
        jac = numerical_jacobian(lambda delta: p.project(pixel, pose, frame["image_domain"], delta))
        independent = jac[:, :2] @ pixel_cov @ jac[:, :2].T
        independent += np.outer(jac[:, 19], jac[:, 19])*clock["independent_sigma_s"]**2
        factors = {key: jac[:, 2:8] @ value for key, value in pose.factors.items()}
        factors["calibration:"+p.calibration.calibration_id+":K"] = jac[:, 8:12] @ root_cov(p.calibration.intrinsics_cov)
        factors["calibration:"+p.calibration.calibration_id+":mount"] = jac[:, 12:18] @ root_cov(p.calibration.mount_cov)
        factors["water:"+p.water_id] = jac[:, 18:19]*p.water_sigma
        factors["clock:"+clock["mapping_id"]] = jac[:, 19:20]*clock["shared_sigma_s"]
        factors = {key: factor for key, factor in factors.items() if np.any(factor)}
        return Observation(detection["id"], detection["class_id"], pose.stamp_ns, mean,
                           covariance(independent, 2, positive=True), factors,
                           frame["id"], p.calibration.calibration_id)
