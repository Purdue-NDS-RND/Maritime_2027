"""Small-course geographic projection and conservative planar geometry."""
import math

# AP_Common/Location: 1e-7 degree latitude in metres.
METRES_PER_DEGREE = 111319.49079327357


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('finite numeric value required')
    return float(value)


def to_gps(x, y, reference):
    x, y = finite(x), finite(y)
    lat = finite(reference['latitude']) + y / METRES_PER_DEGREE
    lon = finite(reference['longitude']) + x / (METRES_PER_DEGREE * math.cos(math.radians((lat + reference['latitude']) / 2)))
    return {'latitude': lat, 'longitude': lon}


def to_local(point, reference):
    lat, lon = finite(point['latitude']), finite(point['longitude'])
    if abs(lat) > 85 or abs(lon) > 180:
        raise ValueError('unsupported geographic position')
    return ((lon - reference['longitude']) * METRES_PER_DEGREE * math.cos(math.radians((lat + reference['latitude']) / 2)),
            (lat - reference['latitude']) * METRES_PER_DEGREE)


def segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_sq = dx * dx + dy * dy
    fraction = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq)) if length_sq else 0
    return math.hypot(point[0] - start[0] - fraction * dx, point[1] - start[1] - fraction * dy)


def polygon_clearance(polygon, centre, radius):
    """Convex enclosing polygon to circle; overlap is negative."""
    cross = []
    distance = math.inf
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        cross.append((b[0] - a[0]) * (centre[1] - a[1]) - (b[1] - a[1]) * (centre[0] - a[0]))
        distance = min(distance, segment_distance(centre, a, b))
    inside = all(c >= 0 for c in cross) or all(c <= 0 for c in cross)
    return (-distance if inside else distance) - radius


def transform_polygon(polygon, x, y, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c * px - s * py, y + s * px + c * py) for px, py in polygon]
