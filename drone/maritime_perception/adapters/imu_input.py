"""Thin callback connecting the IMU logger to the existing perception core."""


class PipelineImuSink:
    def __init__(self, pipeline, navigation_at, contract):
        self.pipeline, self.navigation_at, self.contract = pipeline, navigation_at, contract

    def __call__(self, sample):
        """navigation_at must supply verified same-time data, never latest data."""
        self.pipeline.add_imu_state({"imu": sample.to_record(),
                                     "navigation": self.navigation_at(sample.stamp_ns),
                                     "contract": self.contract})
