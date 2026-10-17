"""Transport independent online course planner. Coordinates come from vision.

Initial gate defines forward/left axes; no course coordinates or marker identities
are supplied. Red stays right, green stays left. Mission length is configuration.
"""
from dataclasses import dataclass
import math


@dataclass
class Landmark:
    identity: int
    category: str
    x: float
    y: float
    seen: float
    count: int = 1


class Mission:
    def __init__(self, turns=4, clearance=2.0):
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
        self.next_id = 0
        self.departure = None

    def observe(self, category, x, y, now):
        if category not in ('red', 'green') or not all(map(math.isfinite, (x, y, now))):
            return
        matches = [b for b in self.landmarks if b.category == category and math.hypot(b.x-x, b.y-y) < 1.3]
        if matches:
            b = min(matches, key=lambda b: math.hypot(b.x-x, b.y-y))
            # Bounded smoothing retains landmarks when they leave the cameras.
            b.x += .2*(x-b.x)
            b.y += .2*(y-b.y)
            b.count += 1
            b.seen = now
        else:
            self.landmarks.append(Landmark(self.next_id, category, x, y, now))
            self.next_id += 1

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

    def update(self, x, y, yaw, now):
        if self.stage in ('complete', 'fault'):
            return None
        ready = [b for b in self.landmarks if b.count >= 3 and now-b.seen < 3 and b.identity not in self.used]
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
            self.target = self.world(2.2, 0)
            self.active_ids = [red.identity, green.identity]
            self.stage = 'gate_a'
        s, t = self.coordinates(x, y)
        if self.target is not None:
            goal_s, goal_t = self.coordinates(*self.target)
            # Clear the plane with the entire vessel before advancing.
            if s >= goal_s-.15:
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


def velocity(x, y, yaw, target, speed=.65):
    if target is None:
        return 0., 0.
    dx, dy = target[0]-x, target[1]-y
    distance = math.hypot(dx, dy)
    if distance < .1:
        return 0., 0.
    # The downstream vessel controller receives an ENU desired velocity vector.
    magnitude = min(speed, distance*.5)
    return magnitude*dx/distance, magnitude*dy/distance


def guidance(x, y, yaw, target):
    """ENU velocity and yaw rate for a vessel accepting both setpoints."""
    vx, vy = velocity(x, y, yaw, target)
    if not (vx or vy):
        return 0., 0., 0.
    desired = math.atan2(vy, vx)
    error = math.atan2(math.sin(desired-yaw), math.cos(desired-yaw))
    speed = math.hypot(vx, vy)*max(.2, math.cos(error))
    desired_rate = max(-.5, min(.5, 1.3*error))
    return speed*math.cos(desired), speed*math.sin(desired), desired_rate
