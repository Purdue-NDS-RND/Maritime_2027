"""Extension point for temporal RGB triangulation; never accepts depth."""

from maritime_localization.interfaces import Observation, PositionEstimate


class TriangulationLocalizer:
    implemented = False

    def reset(self):
        """Clear observation/association history between recordings."""

    def process(self, observation: Observation) -> list[PositionEstimate]:
        if observation.depth_m is not None:
            raise ValueError("RGB triangulation observations must not include depth")
        raise NotImplementedError("RGB triangulation is not implemented")
