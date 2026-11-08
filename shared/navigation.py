"""Task-free navigation with reviewed channel escape constraints."""
import math
from .course import Course, inside, contained, intersects, dot, sub
from .geometry import to_local, segment_distance
from .task_geometry import segment_within


class NavigationCourse(Course):
    def __init__(self, object_map, draft):
        super().__init__(object_map, draft)
        self.waters = []
        start = to_local(draft['start'], self.reference)
        for water in draft.get('navigation_water', []):
            polygon = [to_local(p, self.reference) for p in water['polygon']]
            opening = [to_local(p, self.reference) for p in water['opening']]
            centre = tuple(sum(p[i] for p in opening)/2 for i in (0,1))
            forward = water['direction']
            active = inside(start, polygon) and dot(sub(start, centre), forward) >= -1e-7
            if active and not contained(start, start, polygon, self.required):
                raise ValueError('unsafe planning start: channel boundary exclusion band')
            self.waters.append((polygon, opening, centre, forward, active))
        if sum(w[-1] for w in self.waters) > 1:
            raise ValueError('ambiguous overlapping reviewed channels')
        # One escape phase, without task passage or outbound progress objectives.
        self.planes = [None] if any(w[-1] for w in self.waters) else []
        self.windows = []
        self.remaining_distance = []

    def edge(self, a, b, progress):
        if self.clearance(a,b) < self.required-1e-7 or any(not contained(a,b,p,self.required) for p in self.polygons):
            return None
        next_progress = progress
        for polygon, opening, centre, forward, active in self.waters:
            u, v = dot(sub(a,centre),forward), dot(sub(b,centre),forward)
            # All downstream side/exit boundaries retain the mandatory buffer.
            for c,d in zip(polygon,polygon[1:]+polygon[:1]):
                x,y = dot(sub(c,centre),forward), dot(sub(d,centre),forward)
                if max(x,y) <= 1e-7:
                    continue
                if min(x,y) < 0:
                    p = tuple(c[i]+x/(x-y)*(d[i]-c[i]) for i in (0,1))
                    if x < 0: c = p
                    else: d = p
                if intersects(a,b,c,d) or min(segment_distance(a,c,d),segment_distance(b,c,d),segment_distance(c,a,b),segment_distance(d,a,b)) < self.required-1e-7:
                    return None
            if active and progress == 0:
                if u >= -1e-7 and v < 0:
                    p = tuple(a[i]+u/(u-v)*(b[i]-a[i]) for i in (0,1))
                    if segment_distance(p,*opening) > 1e-6 or not segment_within(a,p,polygon):
                        return None
                    next_progress = 1
                elif not segment_within(a,b,polygon):
                    return None
            else:
                # Do not enter reviewed water downstream through an opening or
                # remain inside it after declaring the escape complete.
                if (inside(a,polygon) and u > 1e-7) or (inside(b,polygon) and v > 1e-7):
                    return None
                if u*v < 0:
                    p = tuple(a[i]+u/(u-v)*(b[i]-a[i]) for i in (0,1))
                    if segment_distance(p,*opening) < 1e-6:
                        return None
        return next_progress

    def heuristic(self, point, finish, progress):
        return math.dist(point,finish)
