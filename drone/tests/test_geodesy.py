import numpy as np
import pytest

from maritime_perception.geodesy import GeodeticConverter
from maritime_perception.validation import Unavailable


def origin(lat=0., lon=0., height=0.):
    return {"origin_id": "test", "latitude_deg": lat, "longitude_deg": lon, "ellipsoid_height_m": height, "provenance": "test"}


def test_equator_independent_sphere_section():
    geo = GeodeticConverter(origin())
    angle = np.deg2rad(.001)
    # At the equator the WGS84 ellipsoid's equatorial section has radius a.
    expected = [6378137*np.sin(angle), 0., 6378137*(np.cos(angle)-1)]
    np.testing.assert_allclose(geo.to_enu(0., .001, 0.), expected, atol=1e-8)
    assert geo.to_wgs84([0, 0, 25])["ellipsoid_height_m"] == pytest.approx(25.)


def test_published_proj_reference():
    # PROJ topocentric documentation uses GRS80; WGS84 discrepancy is below 2 mm here.
    geo = GeodeticConverter(origin(55., 5., 200.))
    np.testing.assert_allclose(geo.to_enu(53.80939444, 2.12955, 73.), [-189013.869, -128642.040, -4220.171], atol=.002, rtol=0)


@pytest.mark.parametrize("point", [[0, 0, 0], [10, 20, 0], [-100, 70, 3], [1000, -300, 5]])
def test_course_round_trip(point):
    geo = GeodeticConverter(origin(40., -86., 200.))
    llh = geo.to_wgs84(point)
    np.testing.assert_allclose(geo.to_enu(llh["latitude_deg"], llh["longitude_deg"], llh["ellipsoid_height_m"]), point, atol=1e-7)


def test_invalid_geodetic_inputs():
    with pytest.raises(Unavailable):
        GeodeticConverter(origin(91))
    with pytest.raises(Unavailable):
        GeodeticConverter(origin()).to_enu(0, float('nan'), 0)
