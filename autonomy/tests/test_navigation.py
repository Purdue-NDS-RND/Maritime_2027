import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ros_ws/src/maritime_navigation'))
from maritime_navigation.mission import Mission, guidance, velocity


class CourseTests(unittest.TestCase):
    def test_full_course_from_online_observations(self):
        mission = Mission()
        buoys = [('red', 7, -2), ('green', 7, 2), ('red', 13, 0), ('green', 19, 0),
                 ('red', 25, 0), ('green', 31, 0), ('red', 37, -2), ('green', 37, 2)]
        x = y = yaw = rate = 0.
        positions = []
        for i in range(2000):
            now = i*.1
            for color, bx, by in buoys:
                if 0 < bx-x < 12:
                    mission.observe(color, bx, by, now)
            target = mission.update(x, y, yaw, now)
            vx, vy, desired_rate = guidance(x, y, yaw, target)
            rate += .2*(desired_rate-rate)
            yaw += .1*rate
            speed = math.hypot(vx, vy)
            x += .1*speed*math.cos(yaw)
            y += .1*speed*math.sin(yaw)
            positions.append((x, y))
            if mission.stage in ('complete', 'fault'):
                break
        self.assertEqual(mission.stage, 'complete', mission.events)
        self.assertEqual(mission.events, ['gate_a', 'turn_1', 'turn_2', 'turn_3', 'turn_4', 'gate_b'])
        for color, bx, by in buoys:
            self.assertGreater(min(math.hypot(px-bx, py-by) for px, py in positions), 1.4)
            crossing = min(positions, key=lambda p: abs(p[0]-bx))
            self.assertGreater(crossing[1]-by if color == 'red' else by-crossing[1], 1.4)
        self.assertGreater(x, 38.9)

    def test_gate_is_relative_to_observation_frame(self):
        m = Mission(turns=0)
        angle = .7
        def transform(x, y):
            return (40+x*math.cos(angle)-y*math.sin(angle),
                    -12+x*math.sin(angle)+y*math.cos(angle))
        for i in range(5):
            for color, x, y in [('red', 7, -2), ('green', 7, 2)]:
                m.observe(color, *transform(x, y), i)
        target = m.update(40, -12, angle, 5)
        self.assertAlmostEqual(target[0], transform(9.2, 0)[0])
        self.assertAlmostEqual(target[1], transform(9.2, 0)[1])
        m.update(*transform(9.2, 0), angle, 6)
        self.assertEqual(m.stage, 'complete')

    def test_no_motion_without_confirmed_gate(self):
        m = Mission()
        for i in range(5):
            m.observe('red', 7, -2, i)
        self.assertIsNone(m.update(0, 0, 0, 5))
        self.assertEqual(velocity(0, 0, 0, None), (0., 0.))

    def test_old_landmarks_cannot_select_a_new_target(self):
        m = Mission()
        for i in range(5):
            m.observe('red', 7, -2, i)
            m.observe('green', 7, 2, i)
        self.assertIsNone(m.update(0, 0, 0, 8))
        m.observe('red', 7, -2, 8.5)
        m.observe('green', 7, 2, 8.5)
        self.assertIsNotNone(m.update(0, 0, 0, 9))

    def test_reversed_gate_rejected(self):
        m = Mission()
        for i in range(5):
            m.observe('red', 7, 2, i)
            m.observe('green', 7, -2, i)
        self.assertIsNone(m.update(0, 0, 0, 5))

    def test_gate_only_and_repeated_category_tracks(self):
        m = Mission(turns=0)
        for i in range(5):
            for c, x, y in [('red', 7, -2), ('green', 7, 2), ('red', 15, -2)]:
                m.observe(c, x, y, i)
        self.assertEqual(len(m.landmarks), 3)
        self.assertIsNotNone(m.update(0, 0, 0, 5))
        m.update(9.2, 0, 0, 6)
        self.assertEqual(m.stage, 'complete')


if __name__ == '__main__':
    unittest.main()
