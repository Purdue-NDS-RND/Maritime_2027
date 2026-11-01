# Perception JSON contract and GCS integration

Last updated: 2026-11-01. Status: proposed semantics for discussion with GCS/boat owners.
This is documentation, not an implemented JSON Schema, ROS message or network endpoint.

## Three different products

1. Observation: one detection from one frame, its selected geometric reference, time,
   ENU position/quality or rejection reason. Retain locally for replay/debugging.
2. Survey map: consolidated physical instances, their estimated positions, uncertainty,
   last observation times and provenance. This is the drone -> GCS deliverable.
3. Route/mission: operator-approved boat waypoints and task actions, produced downstream.
   Existing boat mission semantics remain unchanged.

Use a named schema namespace and version rather than overloading existing object-map
version 1 or 2. Prefer a complete immutable survey snapshot first. Observation streaming,
transport framing and live map deltas may be added only when needed.

## Required map semantics

| Field group | Requirement |
| --- | --- |
| Schema | Name + version; unsupported versions rejected explicitly |
| Survey/map identity | survey_id, map_id, monotonic revision, source vehicle |
| Time | UTC capture start/end and generation time; each object first/last observed |
| Frames | origin_id, ENU axes/units, WGS84 origin lat/lon/ellipsoidal height |
| Water surface | Plane model/elevation and uncertainty/method |
| Processing provenance | Code/model/calibration IDs and configuration identity |
| Objects | Stable instance ID, class/type estimate, ENU horizontal reference and geometry |
| Geodetic export | Derived lat/lon, optional explicitly named ellipsoid height; conversion ID |
| Uncertainty/quality | Covariance or explicit unknown, RTK/timing/geometric quality, usable/degraded status |
| Evidence | Observation count and references to preview/crop/frame/time for review |
| Survey completeness | Complete/partial/failed status, coverage evidence and unresolved regions |
| Semantics | Predicted appearance separate from operator color/role and edits |

Objects of the same class have unique IDs. Track IDs are stable within a survey, not
guaranteed identities across new flights. Preserve merge/split lineage where IDs change.
Color `unknown` is valid. Null means unavailable, not zero uncertainty or zero range.
Detector confidence describes class detection confidence; it is not location accuracy.

## Illustrative draft map

All values below are synthetic fixture data, not measurements of the competition.
The origin is deliberately (0,0,0) for a geodetic test. The WGS84 position corresponds
to the sample ENU point through an ECEF tangent-frame conversion. Quality is unvalidated,
so the map is not navigation-approved. Software IDs are illustrative identifiers.

```json
{
  "schema": "maritime.survey_map",
  "schema_version": 1,
  "survey_id": "survey_fixture_001",
  "map_id": "map_fixture_001",
  "revision": 1,
  "source": {"vehicle_id": "drone_01", "kind": "synthetic"},
  "capture": {
    "started_at": "2026-11-01T15:00:00Z",
    "ended_at": "2026-11-01T15:01:00Z"
  },
  "generated_at": "2026-11-01T15:01:02Z",
  "frame": {
    "id": "survey_enu",
    "origin_id": "equator_test_origin",
    "axes": ["east", "north", "up"],
    "units": "m",
    "origin_wgs84": {
      "latitude_deg": 0.0,
      "longitude_deg": 0.0,
      "ellipsoid_height_m": 0.0
    }
  },
  "water_surface": {
    "model": "horizontal_plane",
    "up_m": 0.0,
    "vertical_uncertainty_m": null,
    "method": "synthetic_fixture"
  },
  "processing": {
    "code_version": "fixture",
    "model_id": "fixture_detector",
    "calibration_id": "fixture_camera",
    "geodesy_id": "wgs84_ecef_enu"
  },
  "objects": [
    {
      "id": "object_0001",
      "class": "buoy",
      "appearance": {"predicted_color": "unknown"},
      "position_enu_m": {"east": 10.0, "north": 20.0, "up": 0.0},
      "position_wgs84": {
        "latitude_deg": 0.0001808738954093828,
        "longitude_deg": 0.00008983152841187855,
        "ellipsoid_height_m": 0.00003940705209970474
      },
      "position_reference": "horizontal_centre_at_water_plane",
      "geometry": {"kind": "unknown", "radius_m": null},
      "uncertainty": {
        "covariance_en_m2": null,
        "systematic_horizontal_bound_m": null
      },
      "quality": {
        "status": "unvalidated",
        "rtk_state": "unknown",
        "timing_validated": false,
        "mean_detection_confidence": 0.88
      },
      "first_observed_at": "2026-11-01T15:00:10Z",
      "last_observed_at": "2026-11-01T15:00:40Z",
      "observation_count": 12,
      "evidence": [{"frame_id": "frame_0042", "preview_id": "preview_0042"}]
    }
  ],
  "coverage": {
    "status": "partial",
    "unresolved_regions": ["coverage_not_evaluated"]
  }
}
```

The small nonzero geodetic height illustrates that local tangent-plane up=0 is not an
exact constant-ellipsoid-height surface away from the origin. It is not measured buoy
freeboard. Production origin heights must come from a documented reference.

## Observations retained locally

A useful observation ledger includes:

- observation/frame ID, source camera, image domain/dimensions, model/calibration IDs;
- original exposure timestamp + clock domain, host receive and detector completion time;
- detection class/confidence and box/selected pixel in the calibrated image domain;
- selected pixel method and any assumed object reference height;
- pose sample IDs/times, interpolation status/gap, ENU origin, attitude and position quality;
- water plane version, ENU hit and geometric conditioning/uncertainty;
- rejected/degraded reason, association decision and target instance if assigned.

Do not delete outliers simply to make output scatter look good. Immutable observations
allow reprocessing with new calibration without rerunning inference or losing context.
A rejected hit has no usable position; never encode it as (0,0,0).

## Existing GCS format: actual compatibility work

`shared/object_map.py::validate_map` currently accepts integer schema_version 1 or 2,
requiring scene_id, run_id, geographic_reference and a nonempty buoys list. Buoy records
include id, centre latitude/longitude, geometry type and positive radius; version 2 also
requires height and obstacle/station/start-pose structures.

`gcs/app/workspace.py` imports that format and invalidates approval on map/draft edits.
The current fixture above uses objects, uncertainty and unknown dimensions and is not
compatible with that import path. The GCS also uses categories in its UI, so validator
acceptance alone would not establish useful unknown-color behavior.

Two candidate routes:

- Introduce an explicit survey-map importer preserving ENU/raw data and survey provenance,
  converting to the current display/planning representation.
- Export a compatibility object map plus its full survey metadata, with a deliberately
  documented survey identity mapping. Do not falsely label measured data as simulator truth.

Choose with the GCS owner. Do not fabricate scene/run identity, physical radius/height,
start pose or obstacle geometry merely to satisfy the old simulator-focused validator.
For collision checking, unknown size requires an explicit conservative operator estimate
or further measurement before navigation approval. Store its source separately.

The GCS must retain original detected position/appearance and a separate reviewed overlay
for operator color, course role and position corrections. Review state records author/time,
source map revision and edits. Repeated surveys must not overwrite reviewed work silently.
An object-map revision affecting a route requires clearance recheck and fresh approval.
The currently implemented GCS approval hashing is useful but does not yet implement all
survey provenance, review overlays or completeness semantics described here.

## Validation and transport

Reject nonfinite numbers, invalid latitude/longitude, duplicate IDs, malformed times,
inconsistent origins, invalid covariance shape/symmetry/positive semidefiniteness, and
inconsistent derived coordinates. Define tolerances and schema evolution explicitly.
A 2x2 EN covariance matrix has axis order [east,north], with units m^2.

The first delivery can be a complete JSON file. Subsequent radio/network transport needs
message/map ID, byte completeness/integrity, revision handling, retry/deduplication,
acknowledgement and explicit failure status. Receiving bytes is not map acceptance or
route approval. Do not assume an MAVLink telemetry radio automatically transports this
payload or the boat HTTP API. Measure actual link throughput and interruptions.

Preview images may transfer separately by evidence ID and checksum; the map must state
when an image is unavailable. No transport library, port or endpoint is selected here.

