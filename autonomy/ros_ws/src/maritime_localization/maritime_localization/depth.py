"""Extension point for registered-depth buoy positioning."""

from maritime_localization.interfaces import Observation, PositionEstimate


class DepthLocalizer:
    implemented = False

    def reset(self):
        """Clear per-recording state when this method is implemented."""

    def process(self, observation: Observation) -> list[PositionEstimate]:
        raise NotImplementedError("Depth positioning is not implemented")
