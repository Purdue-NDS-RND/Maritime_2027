"""Planning policy over the physical RGB map. No ROS or simulator dependencies."""
import math
import numpy as np


class InputProgress:
    """Repeated snapshots do not refresh acquisition progress. Resets latch."""
    def __init__(self):
        self.session = None
        self.stamp = 0
        self.progress = -math.inf
        self.receipt = -math.inf
        self.fault = None

    def update(self, session, stamp, now):
        self.receipt = now
        if self.session is not None and session != self.session:
            self.fault = 'mapping_session_changed'
        if stamp < self.stamp:
            self.fault = 'mapping_time_rewound'
        self.session = session
        if stamp > self.stamp:
            self.stamp, self.progress = stamp, now

    def ready(self, now, timeout=2.):
        return not self.fault and now-self.progress < timeout and now-self.receipt < timeout


class SnapshotPair:
    """Retain a matched snapshot while the next map/grid arrive separately."""
    def __init__(self):
        self.maps, self.grids = {}, {}
        self.stamp = -1

    def push(self, kind, stamp, message):
        cache = self.maps if kind == 'map' else self.grids
        cache[stamp] = message
        for old in sorted(cache)[:-10]:
            del cache[old]
        common = self.maps.keys() & self.grids.keys()
        if common and max(common) >= self.stamp:
            self.stamp = max(common)
            return self.maps[self.stamp], self.grids[self.stamp]
        return None


def validate_bounds(bounds):
    if (len(bounds) != 4 or not all(map(math.isfinite, bounds))
            or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]):
        raise ValueError('Bounds must be finite xmin,ymin,xmax,ymax')
    return tuple(bounds)


def active_bearings(records, tracks, unresolved_ids, snapshot_stamp):
    """Use canonical mapper lifecycle, retaining observations ahead of a snapshot.

    An anonymous ambiguous observation has no authoritative track lifecycle and
    stays a hazard. A positioned track is represented by its metric footprint.
    """
    metric = {t.world_id for t in tracks}
    unresolved = set(unresolved_ids)
    return {key: (stamp, bearing) for key, (stamp, bearing) in records.items()
            if bearing.world_id not in metric and
            (not bearing.world_id or bearing.world_id in unresolved or stamp > snapshot_stamp)}


def resample_physical(physical, origin, source_resolution, bounds, resolution=.1):
    """Crop to the operating region and refine without inventing free cells.

    Nearest containing source-cell sampling preserves every coarse physical
    obstacle. A lethal border bounds planning and keeps fine grids inexpensive.
    """
    bounds = validate_bounds(bounds)
    if (not all(map(math.isfinite, (*origin, source_resolution, resolution)))
            or min(source_resolution, resolution) <= 0 or resolution > source_resolution):
        raise ValueError('Invalid raster resolution')
    physical = np.asarray(physical)
    if physical.ndim != 2 or not np.isin(physical, [-1, 0, 100]).all():
        raise ValueError('Invalid physical occupancy grid')
    output_origin = (math.floor(bounds[0]/resolution)*resolution-2*resolution,
                     math.floor(bounds[1]/resolution)*resolution-2*resolution)
    width = math.ceil((bounds[2]-output_origin[0])/resolution)+2
    height = math.ceil((bounds[3]-output_origin[1])/resolution)+2
    if width*height > 4_000_000:
        raise ValueError('Planning region is too large')
    yy, xx = np.indices((height, width))
    cols = np.floor((output_origin[0]+(xx+.5)*resolution-origin[0])/source_resolution).astype(int)
    rows = np.floor((output_origin[1]+(yy+.5)*resolution-origin[1])/source_resolution).astype(int)
    valid = (cols >= 0) & (cols < physical.shape[1]) & (rows >= 0) & (rows < physical.shape[0])
    output = np.full((height, width), 100, dtype=np.int8)
    output[valid] = physical[rows[valid], cols[valid]]
    return output, output_origin


def planning_grid(physical, origin, resolution, bounds, tracks, sigma=2., clearance=.15,
                  assumed_water=False, constraints=(), bearings=(), clear_start=None,
                  restrict_to_start=False, uncertainty_mode='graded'):
    """Rebuild a conservative grid; boat footprint is applied later by Nav2.

    Unknown -> traversable is an explicit bounded operating assumption. It does
    not modify the mapper's physical grid or claim observed free water.
    Physical obstacles plus clearance are hard. By default, covariance adds a
    graded planning preference, not a promise of collision-free confidence.
    """
    bounds = validate_bounds(bounds)
    if (not all(map(math.isfinite, (resolution, sigma, clearance))) or resolution <= 0
            or sigma < 0 or clearance < 0 or uncertainty_mode not in ('graded', 'hard')):
        raise ValueError('Invalid costmap geometry')
    source = np.asarray(physical, dtype=np.int16)
    if source.ndim != 2 or not np.isin(source, [-1, 0, 100]).all():
        raise ValueError('Invalid physical occupancy grid')
    yy, xx = np.indices(source.shape)
    xx = origin[0]+(xx+.5)*resolution
    yy = origin[1]+(yy+.5)*resolution
    inside = ((xx-resolution/2 >= bounds[0]) & (xx+resolution/2 <= bounds[2])
              & (yy-resolution/2 >= bounds[1]) & (yy+resolution/2 <= bounds[3]))
    result = source.copy()
    if assumed_water:
        result[(source == -1) & inside] = 0
    result[~inside] = 100
    # Unresolved range is uncertainty, represented as an angular soft gradient
    # in graded mode. Strict mode blocks the whole sector. Neither policy clears
    # unknown water or physical occupancy. The declared clear start is exempt.
    startup = np.zeros(source.shape, dtype=bool)
    if clear_start is not None:
        sx, sy, heading = clear_start
        forward = (xx-sx)*math.cos(heading)+(yy-sy)*math.sin(heading)
        left = -(xx-sx)*math.sin(heading)+(yy-sy)*math.cos(heading)
        startup = ((forward >= -3+resolution) & (forward <= 5-resolution)
                   & (np.abs(left) <= 4-resolution))
    for bearing in bearings:
        if not all(map(math.isfinite, (bearing.origin_x, bearing.origin_y,
                                      bearing.world_bearing_rad, bearing.bearing_variance))) or bearing.bearing_variance < 0:
            raise ValueError('Invalid unresolved bearing')
        dx, dy = xx-bearing.origin_x, yy-bearing.origin_y
        distance = np.hypot(dx, dy)
        angle = np.arctan2(dy, dx)-bearing.world_bearing_rad
        angle = np.arctan2(np.sin(angle), np.cos(angle))
        angular_width = max(math.radians(3), 3*math.sqrt(bearing.bearing_variance))
        padding = np.arcsin(np.minimum(1., (.35+clearance+resolution)/np.maximum(distance, .01)))
        sector = (np.abs(angle) <= angular_width+padding) & ~startup
        if uncertainty_mode == 'hard':
            result[sector] = 100
        else:
            soft = np.rint(85*np.clip(1-np.abs(angle)/(angular_width+padding), 0., 1.)).astype(np.int16)
            known = sector & (result >= 0)
            result[known] = np.maximum(result[known], soft[known])
    if restrict_to_start:
        result[~startup] = 100
    for track in tracks:
        if track.lifecycle not in ('tentative', 'confirmed', 'stale', 'inconsistent'):
            raise ValueError('Unknown track lifecycle')
        covariance = np.asarray(track.covariance).reshape(2, 2)
        if (not np.isfinite(covariance).all() or not np.allclose(covariance, covariance.T)
                or not all(map(math.isfinite, (track.x, track.y, track.footprint_radius_m)))
                or track.footprint_radius_m <= 0):
            raise ValueError('Invalid mapped obstacle')
        eigenvalues = np.linalg.eigvalsh(covariance)
        if eigenvalues[0] < -1e-8:
            raise ValueError('Invalid obstacle covariance')
        uncertainty = sigma*math.sqrt(max(0., eigenvalues[-1]))
        radius = track.footprint_radius_m+clearance
        # Cell-disc intersection preserves small hazards between cell centres.
        dx = np.maximum(np.abs(xx-track.x)-resolution/2, 0.)
        dy = np.maximum(np.abs(yy-track.y)-resolution/2, 0.)
        distance = np.hypot(dx, dy)
        if uncertainty_mode == 'hard':
            radius += uncertainty
        elif uncertainty > 0:
            soft = np.rint(85*np.clip(1-(distance-radius)/uncertainty, 0., 1.)).astype(np.int16)
            # Keep unknown unknown unless the bounded-water policy authorized it.
            known = result >= 0
            result[known] = np.maximum(result[known], soft[known])
        result[distance <= radius] = 100
    for origin_xy, forward, left, plane, low, high in constraints:
        dx, dy = xx-origin_xy[0], yy-origin_xy[1]
        s = dx*forward[0]+dy*forward[1]
        t = dx*left[0]+dy*left[1]
        result[(np.abs(s-plane) <= resolution) & ((t < low) | (t > high))] = 100
    return result.astype(np.int8)


def swept_clear(grid, origin, resolution, x, y, yaw, speed, rate, horizon=3.):
    """Conservative sampled hull sweep; includes every grid cell touching hull.

    The 3 s horizon must be validated against measured stopping distance. Add a
    cell diagonal to the rectangle to bound raster and pose sampling error.
    """
    if not all(map(math.isfinite, (x, y, yaw, speed, rate))) or speed < 0:
        return False
    padding = math.sqrt(2)*resolution
    half_length, half_width = 1.1+padding, .6+padding
    radius = math.hypot(half_length, half_width)
    dt = min(.1, resolution/(2*max(.01, speed+abs(rate)*radius)))
    for _ in range(math.ceil(horizon/dt)+1):
        col = int(math.floor((x-origin[0])/resolution))
        row = int(math.floor((y-origin[1])/resolution))
        reach = math.ceil(radius/resolution)
        if row-reach < 0 or col-reach < 0 or row+reach >= grid.shape[0] or col+reach >= grid.shape[1]:
            return False
        patch = grid[row-reach:row+reach+1, col-reach:col+reach+1]
        iy, ix = np.indices(patch.shape)
        dx = origin[0]+(ix+col-reach+.5)*resolution-x
        dy = origin[1]+(iy+row-reach+.5)*resolution-y
        longitudinal = dx*math.cos(yaw)+dy*math.sin(yaw)
        lateral = -dx*math.sin(yaw)+dy*math.cos(yaw)
        hull = (np.abs(longitudinal) <= half_length) & (np.abs(lateral) <= half_width)
        if np.any(hull & ((patch < 0) | (patch >= 100))):
            return False
        x += speed*math.cos(yaw)*dt
        y += speed*math.sin(yaw)*dt
        yaw += rate*dt
    return True
