# Scenario Entity and Category Contract

This contract is the authority for buoy identity, category assignment, rendered
Gazebo names, and evaluation-only truth routing. It applies to scenario source
files, the resolved scenario manifest, generated Gazebo worlds, Simulation
Adapter truth bridges, and simulation evaluators.

## Identity and category

`buoys[].name` is the immutable entity identity. It identifies one physical
buoy within a scenario and is independent of its ArUco marker, category, pose,
and position in the `buoys` array. A seed or pose change must not change the
name. Changing a name creates a different entity; it is not a rename that
consumers may silently correlate with the old entity.

Names must match `^[a-z][a-z0-9_]*$` and must be unique within the scenario.
They must be meaningful instance names such as `red_gate_port`, not values
derived only from a marker ID. Marker IDs are category labels and may repeat.
The mapping is fixed:

| `marker_id` | `category` |
|---:|---|
| 0 | `white` |
| 1 | `red` |
| 2 | `green` |
| 3 | `blue` |

The renderer derives `category` from `marker_id`; scenario authors do not
provide a second, independently editable category value. The renderer also
selects the category asset `model://aruco_buoy_id<marker_id>`. Reusing that
asset for several entities does not merge their identities.

## Resolved manifest version 1

The renderer writes one UTF-8 JSON object with these required top-level fields.
No required field may be `null` except `seed`.

| Field | Type and rule |
|---|---|
| `schema_version` | Integer `1`. A consumer must reject any other value rather than guessing a schema. |
| `scenario` | Non-empty string matching `^[a-z][a-z0-9_]*$`; the source scenario name. |
| `seed` | Integer or `null`; the exact renderer seed. |
| `world` | String `blueboat_rgbd`. |
| `boat_pose` | Object containing finite numeric `x`, `y`, `z`, and `yaw_rad`. |
| `camera_mount` | Object containing finite numeric `x`, `y`, and `z` in `base_link`. |
| `buoys` | Array of zero or more entity records in source order. Identity comes from `name`, never array position. |

Every `buoys[]` entity record contains all of the following fields:

| Field | Type and rule |
|---|---|
| `name` | Immutable entity identity matching `^[a-z][a-z0-9_]*$`; unique in `buoys`. |
| `marker_id` | Integer in the inclusive range 0 through 3; repetition is valid. |
| `category` | Lowercase string derived from the fixed mapping above and consistent with `marker_id`. |
| `gazebo_model_name` | String exactly equal to `name`; used as the generated SDF `<include><name>`. |
| `model_uri` | String exactly `model://aruco_buoy_id<marker_id>`; category-level and therefore allowed to repeat. |
| `model_pose` | Object containing finite numeric `x`, `y`, `z`, `yaw_deg`, and `yaw_rad`; the two yaw values describe the same resolved initial angle. |
| `marker_plane_center` | Object containing finite numeric `x`, `y`, `z`, `normal_x`, and `normal_y`; the initial marker face center and unit horizontal normal in world coordinates. |
| `truth_topic` | String exactly `/blueboat/ground_truth/<name>/odometry`. |
| `evaluation_key` | String exactly equal to `name`. |

For each entity, Gazebo publishes odometry on
`/model/<gazebo_model_name>/odometry`. The Simulation Adapter bridges that
source to the record's `truth_topic` as `nav_msgs/msg/Odometry`, in the
`GZ_TO_ROS` direction. The manifest carries the derived names so bridge and
evaluator consumers can validate the same roster instead of independently
interpreting marker IDs.

All four shared buoy assets include the simulation-only `maritime::BuoyFaceBoat`
Gazebo system. While simulation time advances, it keeps each buoy upright and
turns its local +X marker face toward the XY position of the world model
`blueboat`, preserving its center. This also applies to assets inserted after
startup. With no boat, or coincident XY positions, the current yaw is retained.
The manifest describes the resolved spawn pose, not the changing runtime yaw.
Evaluators must transform the local marker center `(0.311, 0, 0.75)` using live
buoy odometry for runtime marker depth and position. The fixed category mapping
and immutable entity identities remain unchanged.

Manifest validation must reject malformed or missing required fields,
unsupported `schema_version`, non-finite numeric values, marker IDs outside
0 through 3, a category that disagrees with its marker ID, duplicate names,
duplicate `gazebo_model_name` values, duplicate `truth_topic` values, and
duplicate `evaluation_key` values. It must accept duplicate `marker_id`,
`category`, and `model_uri` values. For the supported test area, each resolved
buoy must have `x >= 4.0`, `abs(x) <= 40.0`, and `abs(y) <= 20.0`; every pair
of resolved buoy centers must be at least 1.0 metre apart. `yaw_rad` must equal
`yaw_deg * pi / 180` within floating-point tolerance, and the marker-plane
normal must be unit length and consistent with the resolved yaw.

## Complete repeated-category example

Both records below are red category instances with marker ID 1 and the same
category asset. Their entity names, Gazebo names, truth topics, and evaluator
keys remain distinct.

```json
{
  "schema_version": 1,
  "scenario": "repeated_red",
  "seed": null,
  "world": "blueboat_rgbd",
  "boat_pose": {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "yaw_rad": 0.0
  },
  "camera_mount": {
    "x": 0.35,
    "y": 0.0,
    "z": 0.4
  },
  "buoys": [
    {
      "name": "red_gate_port",
      "marker_id": 1,
      "category": "red",
      "gazebo_model_name": "red_gate_port",
      "model_uri": "model://aruco_buoy_id1",
      "model_pose": {
        "x": 7.0,
        "y": 1.5,
        "z": 0.0,
        "yaw_deg": 192.0,
        "yaw_rad": 3.351032164
      },
      "marker_plane_center": {
        "x": 6.695796096,
        "y": 1.435339464,
        "z": 0.75,
        "normal_x": -0.978147601,
        "normal_y": -0.207911691
      },
      "truth_topic": "/blueboat/ground_truth/red_gate_port/odometry",
      "evaluation_key": "red_gate_port"
    },
    {
      "name": "red_gate_starboard",
      "marker_id": 1,
      "category": "red",
      "gazebo_model_name": "red_gate_starboard",
      "model_uri": "model://aruco_buoy_id1",
      "model_pose": {
        "x": 7.0,
        "y": -1.5,
        "z": 0.0,
        "yaw_deg": 168.0,
        "yaw_rad": 2.932153143
      },
      "marker_plane_center": {
        "x": 6.695796096,
        "y": -1.435339464,
        "z": 0.75,
        "normal_x": -0.978147601,
        "normal_y": 0.207911691
      },
      "truth_topic": "/blueboat/ground_truth/red_gate_starboard/odometry",
      "evaluation_key": "red_gate_starboard"
    }
  ]
}
```

## Runtime handoff and authority boundary

`SCENARIO_MANIFEST` is the only runtime entity-roster interface. It contains an
absolute path inside the consumer container; the standard container path is
`/scenario/active.manifest.json`. Orchestration must render and atomically
publish the file before starting any bridge or evaluator that consumes it, and
must mount it read-only. Passing a comma-separated list, a marker-ID list, raw
JSON in an environment variable, or a separately maintained roster is not
permitted.

The Simulation Adapter reads `SCENARIO_MANIFEST`, validates version 1, and
creates exactly one odometry bridge per `buoys[]` record using
`gazebo_model_name` and `truth_topic`. A simulation evaluator reads the same
manifest, subscribes by `truth_topic`, and stores truth and results by
`evaluation_key`. Image detections must remain an ordered collection (or use a
per-observation key); a dictionary keyed only by `marker_id` is invalid because
several simultaneous detections may have the same category.

All manifest data, generated Gazebo names, entity identities, evaluation keys,
and perfect poses are simulation/evaluation interfaces. Perfect truth remains
under `/blueboat/ground_truth/...`. Autonomy and hardware deployments must not
read the manifest, subscribe to truth topics, or receive scenario entity names,
Gazebo names, evaluation keys, or truth positions. Autonomy receives ordinary
sensor observations and category strings (`white`, `red`, `green`, or `blue`),
never simulator identity. Association of repeated-category observations into
autonomy-owned tracks uses autonomy's own track identities.

## Legacy assumptions to remove

- Task 05 must remove renderer validation that marker IDs are unique and that
  every `name` equals `buoy_<marker_id>`. It must preserve unique `name`
  validation, emit the version 1 fields above, and add a repeated-category
  scenario.
- Task 06 must remove the four fixed `buoy_0` through `buoy_3` Gazebo/ROS truth
  bridge pairs. It must build truth bridges from `SCENARIO_MANIFEST`, subscribe
  evaluators by `truth_topic`, store evaluator results by `evaluation_key`, and
  stop collapsing detections into a dictionary keyed only by `marker_id`.
- Task 09 must remove `ACTIVE_BUOY_IDS`, including its comma-separated
  construction in `Simulation/scripts/run.sh`, its empty fallback, and its
  Compose environment handoff. It must mount the rendered manifest and pass
  only the `SCENARIO_MANIFEST` path to the components that require the entity
  roster.
