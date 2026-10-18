"""Transport independent online course planner. Coordinates and persistent identities come from the shared buoy map.

Initial gate defines forward/left axes; no course coordinates or marker identities
are supplied. Red stays right, green stays left. Mission length is configuration.
"""
from dataclasses import dataclass
import math


def observation_goals(x, y, yaw):
    """Bounded opposing viewpoints, used only in the declared clear start area."""
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x+dx*c-dy*s, y+dx*s+dy*c, yaw)
            for dx, dy in ((3., 1.5), (2., -1.5), (0., 1.5), (0., -1.5))]


def search_goal(mission, pose, bounds, attempt):
    """A short viewpoint move, without guessing a missing buoy's range."""
    if mission.forward is None or attempt >= 4:
        return None
    s, t = mission.coordinates(*pose[:2])
    side = 2. if mission.passed % 2 == 0 else -2.
    if abs(side-t) < 1. or attempt % 2:
        side = -side
    x, y = mission.world(s+1.+attempt//2, side)
    # Leave room for the hull to turn at the viewpoint. The actual route and
    # physical obstacles are still checked by Nav2 and the movement gate.
    margin = 1.5
    if not (bounds[0]+margin <= x <= bounds[2]-margin
            and bounds[1]+margin <= y <= bounds[3]-margin):
        return None
    return x, y, math.atan2(mission.forward[1], mission.forward[0])


@dataclass
class Landmark:
    identity: str
    category: str
    x: float
    y: float
    seen: float
    count: int = 1


class Mission:
    def __init__(self, turns=4, clearance=3.0):
        if turns < 0 or clearance < 1.5:
            raise ValueError('Invalid course/clearance')
        self.turns = turns
        self.clearance = clearance
        self.landmarks = []
        self.origin = None
        self.forward = None
        self.left = None
        self.target = None
        self.active_ids = []
        self.used = set()
        self.stage = 'acquire_gate'
        self.passed = 0
        self.events = []
        self.departure = None
        self.gate_plane_s = None
        self.gate_width = None

    def coordinates(self, x, y):
        dx, dy = x-self.origin[0], y-self.origin[1]
        return dx*self.forward[0]+dy*self.forward[1], dx*self.left[0]+dy*self.left[1]

    def world(self, s, t):
        return (self.origin[0]+s*self.forward[0]+t*self.left[0],
                self.origin[1]+s*self.forward[1]+t*self.left[1])

    def gate_pair(self, candidates, heading):
        pairs = []
        for red in candidates:
            for green in candidates:
                if red.category != 'red' or green.category != 'green':
                    continue
                dx, dy = green.x-red.x, green.y-red.y
                width = math.hypot(dx, dy)
                # Red->green must point left across the course, within 20 deg.
                if 2.6 <= width <= 6.0 and (-dx*math.sin(heading)+dy*math.cos(heading))/width > .94:
                    pairs.append((red, green))
        return pairs

    def refresh_target(self):
        """Keep a committed course leg attached to its current map identities."""
        if self.target is None or self.forward is None:
            return
        active = [b for b in self.landmarks if b.identity in self.active_ids]
        if len(active) != len(self.active_ids):
            self.stage = 'fault'
            self.events.append('active_course_track_missing')
            self.target = None
            return
        if self.stage in ('gate_a', 'gate_b'):
            coordinates = [self.coordinates(b.x, b.y) for b in active]
            plane = sum(s for s, _ in coordinates)/2
            centre = sum(t for _, t in coordinates)/2
            self.gate_plane_s = plane
            self.gate_width = abs(coordinates[0][1]-coordinates[1][1])
            target = self.world(plane-2.0 if self.departure is not None else plane+2.2, centre)
            departure = self.world(plane+2.2, centre) if self.departure is not None else None
        elif self.stage.startswith('turn_'):
            buoy = active[0]
            s, t = self.coordinates(buoy.x, buoy.y)
            side = t+(self.clearance if buoy.category == 'red' else -self.clearance)
            target = self.world(s-1.8 if self.departure is not None else s+1.5, side)
            departure = self.world(s+1.5, side) if self.departure is not None else None
        else:
            return
        # Small posterior changes should not continually cancel Nav2 actions.
        if math.dist(target, self.target) > .3:
            self.target, self.departure = target, departure

    def update(self, x, y, yaw, now):
        if self.stage in ('complete', 'fault'):
            return None
        # Shared-map confirmation persists through occlusion. Whole-map progress
        # is gated by the supervisor; individual age is represented in covariance.
        ready = [b for b in self.landmarks if b.count >= 3 and b.category in ('red', 'green')
                 and b.identity not in self.used]
        if self.forward is None:
            pairs = self.gate_pair(ready, yaw)
            pairs = [p for p in pairs if all((b.x-x)*math.cos(yaw)+(b.y-y)*math.sin(yaw) > 1 for b in p)]
            if not pairs:
                return None
            red, green = min(pairs, key=lambda p: math.hypot((p[0].x+p[1].x)/2-x, (p[0].y+p[1].y)/2-y))
            width = math.hypot(green.x-red.x, green.y-red.y)
            self.left = ((green.x-red.x)/width, (green.y-red.y)/width)
            self.forward = (self.left[1], -self.left[0])
            self.origin = ((red.x+green.x)/2, (red.y+green.y)/2)
            self.gate_plane_s, self.gate_width = 0., width
            self.target = self.world(2.2, 0)
            self.active_ids = [red.identity, green.identity]
            self.stage = 'gate_a'
        s, t = self.coordinates(x, y)
        if self.target is not None:
            goal_s, goal_t = self.coordinates(*self.target)
            # Clear the plane with the entire vessel before advancing.
            if s >= goal_s-.35 and math.hypot(s-goal_s, t-goal_t) <= .4:
                if abs(t-goal_t) > .85:
                    self.stage = 'fault'
                    self.events.append('missed_course_target')
                    return None
                if self.departure is not None:
                    self.target, self.departure = self.departure, None
                    return self.target
                self.used.update(self.active_ids)
                self.events.append(self.stage)
                if self.stage == 'gate_b' or (self.stage == 'gate_a' and self.turns == 0):
                    self.stage = 'complete'
                    self.target = None
                    return None
                if self.stage.startswith('turn_'):
                    self.passed += 1
                self.target = None
        if self.target is None:
            ahead = [b for b in ready if b.identity not in self.used and self.coordinates(b.x, b.y)[0] > s+.5]
            if not ahead:
                self.stage = 'search'
                return None
            if self.passed < self.turns:
                expected = 'red' if self.passed % 2 == 0 else 'green'
                ahead = [b for b in ahead if b.category == expected]
                if not ahead:
                    self.stage = 'search'
                    return None
            nearest = min(ahead, key=lambda b: self.coordinates(b.x, b.y)[0])
            ns, nt = self.coordinates(nearest.x, nearest.y)
            if self.passed == self.turns:
                pairs = self.gate_pair(ahead, math.atan2(self.forward[1], self.forward[0]))
                if not pairs:
                    self.stage = 'search_exit'
                    return None
                red, green = min(pairs, key=lambda p: sum(self.coordinates(b.x, b.y)[0] for b in p))
                rs, rt = self.coordinates(red.x, red.y)
                gs, gt = self.coordinates(green.x, green.y)
                self.gate_plane_s = (rs+gs)/2
                self.gate_width = abs(gt-rt)
                self.target = self.world((rs+gs)/2-2.0, (rt+gt)/2)
                self.departure = self.world((rs+gs)/2+2.2, (rt+gt)/2)
                self.active_ids = [red.identity, green.identity]
                self.stage = 'gate_b'
            else:
                # Approach the required side BEFORE reaching the buoy's plane.
                side = nt+(self.clearance if nearest.category == 'red' else -self.clearance)
                self.target = self.world(ns-1.8, side)
                self.departure = self.world(ns+1.5, side)
                self.active_ids = [nearest.identity]
                self.stage = f'turn_{self.passed+1}'
        return self.target
