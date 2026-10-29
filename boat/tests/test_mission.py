import json
from pathlib import Path
import tempfile
import unittest

from boat_app.mission import Mission, Point, distance_m


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/mission.json"


class MissionTests(unittest.TestCase):
    def load_changed(self, change):
        data = json.loads(EXAMPLE.read_text())
        change(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mission.json"
            path.write_text(json.dumps(data))
            return Mission.load(path)

    def test_example_and_fingerprint(self):
        mission = Mission.load(EXAMPLE)
        self.assertAlmostEqual(distance_m(Point(51.566151, -4.034345), mission.waypoints[0]), 12.009, places=2)
        self.assertEqual(mission.sha256, Mission.load(EXAMPLE).sha256)
        changed = self.load_changed(lambda data: data.update(speed_m_s=0.5))
        self.assertNotEqual(mission.sha256, changed.sha256)

    def test_speed_is_not_limited_to_a_calibrated_range(self):
        self.assertEqual(self.load_changed(lambda data: data.update(speed_m_s=7.5)).speed_m_s, 7.5)

    def test_rejects_unsafe_or_ambiguous_values(self):
        for key, value in (("speed_m_s", 0), ("speed_m_s", True),
                           ("finish_radius_m", float("nan")),
                           ("timeout_s", float("inf")), ("waypoints", []),
                           ("mission_id", ""), ("unknown", 1)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.load_changed(lambda data: data.update({key: value}))
        for point in ({"latitude": 91, "longitude": 0}, {"x": 1, "y": 2},
                      {"latitude": "51.5", "longitude": 0}):
            with self.subTest(point=point), self.assertRaises(ValueError):
                self.load_changed(lambda data: data.update(waypoints=[point]))

    def test_distance_direction_and_dateline(self):
        self.assertAlmostEqual(distance_m(Point(0, 0), Point(0, 0.001)), 111.195, places=2)
        self.assertAlmostEqual(distance_m(Point(0, 179.999), Point(0, -179.999)), 222.39, places=2)


if __name__ == "__main__":
    unittest.main()
