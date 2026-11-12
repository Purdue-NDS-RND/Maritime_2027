"""PROJ WGS84 geodetic/ECEF/topocentric conversions; no simulator projection edits."""
import numpy as np
from pyproj import Transformer
from pyproj.enums import TransformDirection

from .validation import Unavailable, array


class GeodeticConverter:
    def __init__(self, origin):
        self.origin = origin
        lat, lon, height = array([origin["latitude_deg"], origin["longitude_deg"], origin["ellipsoid_height_m"]], (3,), "origin")
        if not -90 < lat < 90 or not -180 <= lon <= 180 or not origin.get("origin_id"):
            raise Unavailable("invalid_origin")
        self.transformer = Transformer.from_pipeline(
            f"+proj=pipeline +step +proj=cart +ellps=WGS84 +step +proj=topocentric "
            f"+ellps=WGS84 +lat_0={lat:.17g} +lon_0={lon:.17g} +h_0={height:.17g}")

    def to_enu(self, latitude, longitude, height):
        values = array([latitude, longitude, height], (3,), "geodetic_position")
        if abs(latitude) > 90 or abs(longitude) > 180:
            raise Unavailable("invalid_geodetic_position")
        return np.asarray(self.transformer.transform(values[1], values[0], values[2], errcheck=True))

    def to_wgs84(self, enu):
        enu = array(enu, (3,), "enu_position")
        lon, lat, height = self.transformer.transform(*enu, direction=TransformDirection.INVERSE, errcheck=True)
        return {"latitude_deg": float(lat), "longitude_deg": float(lon), "ellipsoid_height_m": float(height)}
