# Simulator scenarios

`one.json`, `gate.json`, `multi.json`, `repeated_red.json`, and `slalom.json` are the editable
source of truth for the RGB-D test worlds. Each buoy has a unique, stable entity
name, a category marker ID, a nominal pose, and optional symmetric jitter
limits. Marker IDs may repeat: `repeated_red.json` contains two separate red
entities that both use marker ID 1. Launch the nominal layout with
`SCENARIO=gate make run`, or a reproducible randomized layout with
`SCENARIO=gate BUOY_SEED=42 make run`.
Add `WATER=calm`, `WATER=normal`, or `WATER=harsh` to choose water independently
of the buoy layout, for example `WATER=harsh SCENARIO=gate make run`. Explicit
scenario commands without `WATER` retain their original calm-water default.

## Default competition course

`make run` defaults to `competition.json`; `SCENARIO=competition` selects it
explicitly. The boat starts at world (0, 0), facing west (Gazebo yaw pi,
SITL heading 270 degrees). The upper blue marker is 3 m east of the boat.
The geographic reference remains 51.566151, -4.034345.

The local course PDF in `docs/competition_docs/` supplies labeled distances:
1 ft = 0.3048 m. Relative to that blue marker, Dodge runs west through gates
at -45/-195 ft with four turns spaced 30 ft apart. Evade descends a 40 ft wide,
60 ft long channel. Identify, Deploy, Launch, Recover and Return run east on
the lower row. Receive is a dock annotation associated with Deploy; it adds no
offshore obstacle. The cyan marker's purpose is unspecified.

The source records reference feet, metric poses, stable identities, task labels,
and approximation notes. The 4 m Dodge gate width, 5 ft Identify spacing,
10 ft target diameter, detector/case sizes and simplified docks are estimates.
These are fixed scene props, including a striped Zebra buoy; they do not use
the regression ArUco buoy tracking plugin. Cameras and boat dynamics are unchanged.
Competition bounds are checked separately; legacy scene bounds remain unchanged.

Snapshots and active-scene checks include all 23 buoys and six physical props.
Competition exports use object-map version 2: buoy records, circle/polygon
obstacle footprints derived from actual collision primitives, station annotations,
nonblocking 6 ft deployment-radius overlay and recorded start pose. The physics
recorder is enabled. Use the existing alignment probe/report and active export
commands in the [GCS guide](../../gcs/README.md); the probe restores the original
spawn heading. Keep the boat app stopped while probing.

Routes are manually authored using the GCS **Custom route (clearance only)**
mode, with no required passage list. Identify contact, sensor deployment,
detector behavior, launch, retrieval, docking actions and scoring are deferred.
Map visibility does not establish challenge compliance or full-course acceptance.
The old **Slalom** menu selection and `SCENARIO=slalom` retain the accepted
Milestone 1 regression layout and passage validator.

## Slalom / Dodge practice

Run `WATER=calm SCENARIO=slalom make run`, or select **Slalom** after choosing
water in the setup menu. These scenes use the retained camera-equipped Gazebo assets.

The fixed layout is inspired by the supplied Dodge reference, rotated so the
boat starts at `(0, 0)` and travels along +X. Gate A is at X=7 m; Gate B is at
X=37 m. Each gate has green at Y=+2 m and red at Y=-2 m (4 m between centres).
Four centreline turns at X=13, 19, 25 and 31 m alternate red/green/red/green.
An illustrative path passes red on the boat's right and green on its left.
The 30 m course, gate widths and spacing are provisional, not official event
dimensions. Gate names live in entity IDs; no course timing/scoring or autonomous
path controller is added. The same shared marked buoy assets are used throughout.

The JSON intentionally has no jitter: `BUOY_SEED` leaves this reference layout
unchanged. Edit its poses to adjust the spacing. Near buoys may hide distant
markers until the boat moves; seeing all eight markers at once is not expected.
The existing camera also clips at 20 m, so the far end becomes visible as the
boat advances. Camera range and boat dynamics are unchanged.

These are scene assets, not autonomous route execution. Buoy centers remain
fixed; later feasibility tests must account for buoy drift too.

## Scenario implementation

The renderer validates entity names, marker IDs, test-area bounds, and
separation, then writes the untracked world and versioned entity-roster manifest
under `logs/generated-worlds/`. The fixed marker/category mapping is 0=white,
1=red, 2=green, and 3=blue.

Every shared buoy model turns around its vertical axis to face `blueboat` as
the boat moves. Its center stays fixed. This behavior also applies when the
same models are inserted into calm, waves, harbor, or custom worlds at runtime;
those worlds do not acquire additional buoys automatically. Use the marked
`model://aruco_buoy_id0` through `model://aruco_buoy_id3` assets for all buoy
spawns, choosing the ID by color rather than by entity instance.

Scenario yaw and marker-plane fields in the generated manifest describe the
initial pose. Runtime evaluation uses live buoy odometry to locate the rotating
marker. Markers stay upright; visibility still depends on camera view, distance,
and occlusion.

Run `make buoy-tracking-smoke` after building to exercise the real Gazebo
plugin through a full circle for all colors, late boat and buoy insertion, and
coincident target positions. It uses an isolated Gazebo partition and no ROS or
FCU.
