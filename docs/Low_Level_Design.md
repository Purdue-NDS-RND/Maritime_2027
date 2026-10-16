# Maritime 2027 Low-Level Design

## Purpose, Scope, and Design Status

**Current migration status (2026-10-04):** the simulated public camera boundary
is `/sensors/camera_0/...` with `camera_0_link` and
`camera_0_optical_frame`; MAVROS and `udp://:14552@` are Simulation Adapter
responsibilities. The Hardware Adapter and actual perception/state/mapping
application are not implemented. The simulation RGB-D and MAVROS regression
suite has passing evidence in the [RGB-D transport verification report](../Simulation/docs/RGBD_TRANSPORT_VERIFICATION.md).

The goal of this design effort is to establish the base autonomy functionality
on which later missions can be built. The intended result is a vessel that can
perceive its surroundings, obtain a vessel-state estimate, map the surrounding
area, and move within that area. Specific mission behaviors will build on this
foundation.

The first implementation covers sensing, the state interface, mapping, and
live visualization of the costmap while the operator manually pilots the boat.
It will not autonomously select destinations, generate routes, or issue motion
commands. Mission selection, path planning, and autonomous control are deferred
until this sensing and mapping foundation is established.

Design discussions currently focus on perception, state estimation, and mapping.
Navigation notes below preserve future direction only; they are not part of the
first implementation scope.

The perception, state, and mapping configuration, diagnostics, and verification
details below are draft recommendations for review. Those application behaviors
are not implemented or runtime-validated. Implemented Adapter interfaces are
defined by the versioned contracts linked below.
The perception behavior recorded from design discussions remains the baseline.

The state and mapping decisions below incorporate the approved six-part review:
coordinates and timing, depth extraction, buoy association, costmap structure,
visualization and lifecycle, and acceptance tests. Their numerical starting
values are configurable and require validation; approval does not imply that
implementation or runtime verification has occurred.

Existing-system changes and integration gaps are tracked separately in
[Things to Fix Before Implementation](Things_To_Fix_Before_Implementation.md),
including when each item must be resolved.

### Relationship to the High-Level Design

The [High-Level Design](High_Level_Design.md) defines mission-level scope,
component responsibilities, and deployment boundaries. This document refines
those boundaries into implementation instructions. Where both documents discuss
the same implementation detail, the settled decision recorded here is the newer
authority. Neither document turns a target-state design into a claim that the
corresponding repository migration or runtime validation is already complete.

### Requirements and Design Constraints

### Assumptions and Dependencies

## Component and Package Organization

### Package Responsibilities and Dependencies

Implementation status: the explicitly launched 2D detector now lives in
`autonomy/ros_ws/src/maritime_perception`. The shared detector returns only
axis-aligned marker boxes and category labels; marker corners are discarded.
No ArUco/PnP pose or known-size range estimation is implemented. The optional
debug image labels recognized categories only. The default autonomy service
still runs its bootstrap placeholder. A shared ROS detector/localizer launch,
XY output messages, and replay/result-recording tools are described in the
[benchmark guide](../Simulation/docs/BUOY_BENCHMARKS.md). The localizer currently
assembles the latest received state/calibration/depth with no timestamp
synchronization, and uses MAVROS `map` coordinates. The two positioning methods,
association, and accuracy scoring remain unimplemented. Box centers approximate
buoy centers. The draft sections below describe the wider target design,
including stronger timing requirements deferred from this initial scaffold.

Draft: place the detector in `autonomy/ros_ws/src/maritime_perception`, with
launch integration in `maritime_bringup`. Use OpenCV for ArUco detection,
`cv_bridge` for image conversion, and the standard `sensor_msgs` and
`vision_msgs` interfaces. Python with `rclpy` is the proposed initial
implementation; confirm throughput before deciding whether C++ is needed.
Gazebo bridge dependencies remain in the Simulation Adapter. Scenario-based
evaluators belong to Simulation test tooling rather than Adapter runtime.

### ROS 2 Nodes and Execution Model

Draft: launch `aruco_detector` once per camera namespace. Keep image reception
responsive while a worker processes one image, retaining at most one pending
image that is replaced by newer arrivals. DDS queue settings alone do not
define this application-level behavior. A future `yolo_detector` will follow
the same public interface; launch configuration selects the detector per camera.

## Shared Interfaces and Data Conventions

### ROS 2 Topics, Services, and Actions

Draft interfaces, relative to each detector's camera namespace:

| Topic | Direction | Message type | Purpose |
|---|---|---|---|
| `image` | Input | `sensor_msgs/msg/Image` | Camera color image, remapped at launch. |
| `detections` | Output | `vision_msgs/msg/Detection2DArray` | Recognized buoy detections for each processed image. |
| `debug/image` | Optional output | `sensor_msgs/msg/Image` | Source image annotated with boxes and labels. |

No custom service or action is proposed for initial detection. For simulation,
propose namespace `/perception/camera_0` and remap its `image` input to the
target `/sensors/camera_0/color/image_raw` topic. The Simulation Adapter now
normalizes its public camera boundary to that topic; legacy Gazebo names remain
private implementation details.
Namespace names are configuration, not assumptions inside the
detector. Only one selected detector publishes the primary output per camera.

### Message Definitions and Data Models

### Coordinate Frames, Transforms, and Units

### Timestamps and Clock Synchronization

Draft: copy source headers without replacing timestamps with processing time.
Set `use_sim_time=true` for the simulated detector and false for hardware.
Preserve the incoming camera frame; do not hard-code the current simulator's
historical `zed2i_*` names. The Simulation Adapter already normalizes frames to
`camera_0_optical_frame`; physical-camera integration remains deferred.
Do not infer that MAVROS and camera timestamps are synchronized merely because
the detector uses simulation time; state/depth synchronization remains open.

### Quality of Service and Data Freshness

Draft: use best-effort reliability, volatile durability, and keep-last history
with depth 1 for image input, detections, and debug images. This follows the
ROS sensor-data preference for fresh observations; the current RGB bridge
already uses the sensor-data profile. Detection consumers and test subscribers
must use compatible QoS. Publishing one array per processed image does not
guarantee every subscriber receives every array.

The latest-image worker policy complements these transport settings. Maximum
acceptable observation age and processing rate require measurements before
numerical acceptance limits are selected.

### Configuration and Parameters

Draft configuration is supplied through per-camera ROS parameter YAML and launch
remaps. Initially apply changes by restarting the instance.

| Setting | Draft value or policy |
|---|---|
| `aruco_dictionary` | `DICT_4X4_50`, matching the existing simulator markers. |
| `marker_ids` | Integer array `[0, 1, 2, 3]`. |
| `marker_categories` | Parallel string array `[white, red, green, blue]`. |
| `publish_debug_image` | `false` by default; enabled for visual checks. |
| Camera namespace and image remap | Supplied by launch for each source. |
| `use_sim_time` | Selected by deployment environment. |

Validate that category arrays have equal lengths, IDs are unique configuration
keys within the selected dictionary, and labels belong to the supported set.
Repeated IDs on different observed buoys remain valid. Invalid configuration
should prevent startup with an explanatory error. Physical marker size is not
required for this 2D-only interface; scene marker size still affects visibility.
Exact OpenCV version and detector tuning remain open pending image testing.

## Camera and Sensor Integration

### Camera-Neutral Observation Interface

Both environment-specific Adapters will expose generic camera interfaces.
Camera identifiers describe configured mounting positions and remain stable
across launches; camera model and serial number belong in configuration.

| Interface | First-camera name |
|---|---|
| Color image | `/sensors/camera_0/color/image_raw` |
| Depth registered to color | `/sensors/camera_0/depth/image_rect_raw` |
| Color calibration | `/sensors/camera_0/color/camera_info` |
| Camera mounting frame | `camera_0_link` |
| Color and registered-depth optical frame | `camera_0_optical_frame` |

Simulation initially supplies `camera_0`; hardware supplies `camera_0` and
`camera_1` using the same convention. Autonomy processes configured sources
through this common interface. The [camera contract](contracts/camera_adapter_contract.md)
fixes registered depth as `32FC1` metres, calibration compatibility, exact
simulation timestamp matching, a 100 ms simulation acquisition-age limit, and a
2 s steady-clock arrival watchdog. Hardware timing values require independent
signed dual-camera evidence; they do not inherit simulation limits.

### Physical Camera Sources and Calibration

The physical cameras are ZED X Mini cameras. Their publishing wrappers will
live in the Hardware Adapter and expose the generic interface above. ZED 2i
is not the selected hardware. Driver integration, calibration loading, and
device-to-mount configuration remain implementation design work.

### Simulated RGB-D Source

The current simulator supplies one generic Gazebo RGB-D camera with ideal
depth. Its historical `zed2i_*` frame names are private source identifiers; the
Simulation Adapter publishes the generic convention. This source does not
model the physical two-camera arrangement
or establish ZED X Mini performance.

### Source Synchronization and Availability

Camera observations and MAVROS state must have compatible timestamps during
normal uninterrupted operation, allowing mapping to use vessel state at image
acquisition time. Preserve source acquisition timestamps through wrappers.
The camera contract defines and validates the simulation camera stream timing
and stale-data thresholds. Camera-to-vessel-state clock compatibility and
application-level synchronization remain to be verified before mapping. Missing
or stale inputs must not be treated as fresh
observations, even though simulation pause/resume is outside initial scope.

## Perception

### Inputs and Outputs

The initial detector will consume camera images and produce 2D detections
containing a buoy category and its location in the image. It will not consume
depth or estimate a buoy's 3D position.

Both the ArUco detector and the future YOLO detector will publish
`vision_msgs/msg/Detection2DArray`, containing one `Detection2D` per detection
in a processed image. Each detection will include:

- A buoy category in `results[].hypothesis.class_id`, using `white`, `red`,
  `green`, or `blue`.
- An axis-aligned `BoundingBox2D`, represented by its center and width and
  height in source-image pixels, with box rotation set to zero.
- The source image timestamp and camera frame in its header. The array header
  will also match the source image header.

For every successfully processed image, the detector will publish a detection
array, including an empty array when no recognized buoy categories are found.
An empty array represents a completed observation with no recognized detections;
missing images or processing failures must not be represented as empty results.

When processing falls behind the camera, each detector instance will prioritize
the newest available image and discard older pending images rather than build
a processing backlog. An image already being processed may finish; the next
image selected will be the latest available. Dropped images will not produce
detection arrays. Published results will retain the timestamp of the image
actually processed.

The ArUco bounding box will enclose the detected marker; the future YOLO box
will enclose the detected buoy. Downstream processing must account for this
difference in the image region represented by each detector.

The `Detection2D.id` field will remain empty until object tracking is designed;
it must not contain the category-level ArUco ID. No 3D pose is estimated, and
consumers must not interpret default pose fields as measured positions.
Confidence-score semantics remain open. Draft topic names and QoS are recorded
under Shared Interfaces and Data Conventions.

Both detector nodes will support an optional debug image showing the source
image with bounding boxes and buoy-category labels overlaid. Debug image
publication will be configurable and will preserve the source image header
for correlation with detections. It is intended for visual inspection;
downstream autonomy will consume the detection messages.

### Buoy Detection and Classification

The initial perception pipeline will use ArUco markers for detections. An
ArUco detection node will provide the initial detection capability used to
develop the autonomy foundation.

ArUco marker IDs will map to buoy categories rather than unique physical buoy
identities. Multiple buoys may belong to the same category; a marker ID alone
must not be used to identify an individual mapped buoy. The initial buoy
categories are white, red, green, and blue, with the following marker-ID mapping:

| ArUco marker ID | Buoy category |
|---|---|
| 0 | White |
| 1 | Red |
| 2 | Green |
| 3 | Blue |

ArUco IDs outside the configured category mapping (initially IDs 0–3) will
be excluded from published buoy detections. When debug image publication is
enabled, those markers will still be outlined and labeled `unmapped ID`,
including the numeric marker ID, to make configuration errors visible.

A separate YOLO detection node is planned for later real-world detections.
That node will use a similar perception pipeline so the detection approach can
evolve while supporting the same downstream autonomy responsibilities.

Draft interfaces and dictionary configuration are recorded above; detector
tuning and confidence semantics remain unresolved.

### Relative Position Estimation and Confidence

Depth-based position estimation is deferred to the mapping design. The initial
perception scope is limited to category identification and image-space location.

### Multiple Camera Observation Handling

Run one detector instance per camera source. Each instance will process its
own image stream and publish detections and optional debug images under a
separate camera namespace, preserving that camera's source image headers.

Simulation will initially use one instance for its single RGB-D camera's color
stream. The planned physical two-camera setup will use two instances of the
selected detector implementation. Perception will keep their observations
separate; combining observations across cameras and associating detections
with mapped buoys belong to mapping.

## State Estimation and Flight-Controller Integration

State estimation will provide a stable, project-owned topic interface for
mapping, navigation, and other vessel-state consumers. Initially, a node in
`maritime_state` will subscribe to MAVROS state topics and republish their
information under that interface. It will not implement a new estimator or
perform additional sensor fusion in this first version.

Later, a replacement or additional state-estimation node may supply estimates
from other sources, including a future GPS-denied approach, without changing
the topic names used by consumers. GPS-denied operation itself is future work;
this design establishes the interface boundary to support that evolution.

### MAVROS Connection and Vessel-State Inputs

Agreed topic mapping, retaining standard ROS message types rather than creating
custom message definitions:

| MAVROS input | Autonomy output | Message type | Information |
|---|---|---|---|
| `/mavros/imu/data` | `/state/imu` | `sensor_msgs/msg/Imu` | IMU and orientation information supplied by MAVROS. |
| `/mavros/local_position/odom` | `/state/odometry` | `nav_msgs/msg/Odometry` | Local position, orientation, velocity, and associated covariance fields. |
| `/mavros/global_position/global` | `/state/global_position` | `sensor_msgs/msg/NavSatFix` | Flight-controller global position estimate expressed as latitude, longitude, and altitude. |

These MAVROS inputs are already referenced by the repository's MAVROS smoke
test. Local odometry is the primary local-state output because it includes pose
and velocity. No separate pose-only topic is required initially.
The global input above is the flight controller's fused global estimate;
a separate raw GPS measurement interface can be added if a concrete need arises.

### State Conversion and Reference Frames

Initially preserve source values, timestamps, frame identifiers, covariance,
and status fields when republishing. Do not relabel frames without transforming
their data or replace measurement timestamps with relay publication times.

A stable topic name alone is not a complete replacement contract. Future
providers must preserve the agreed message types, units, frame meanings,
origin conventions, and validity behavior. The map uses a fixed local frame
established when mapping starts, based on the flight controller's local
coordinates. Preserve full vessel orientation when transforming camera
observations before projecting their positions into the 2D map.
Exact frame names and geographic datum/transform remain open. The Adapter owns
camera mounting transforms; shared state integration owns estimated motion TF.
Only one selected provider should own each public state output at a time.

Match detections to their corresponding depth images and interpolate vessel
pose at the source image timestamp. If matching depth, pose, or transforms are
unavailable, skip that metric observation and report a diagnostic. Timestamp
tolerances, buffering limits, and interpolation-gap limits remain to be tuned.

### State Validity and Availability

Do not fabricate global coordinates when no valid global reference exists.
A future GPS-denied estimator may provide local state while global position
is unavailable. The public topic name can remain stable without guaranteeing
that valid global data always exists.

Preserve upstream validity indicators and uncertainty. Freshness thresholds
and the diagnostic interface remain open. Missing required state prevents map
updates from the affected observations. An estimator reset or origin change
pauses mapping and requires an explicit new mapping session; keep the previous
map visible until it is reset. Reset-detection details remain to be designed.
Republishing a stale sample with a new timestamp must not make it appear fresh.
Changing the onboard state provider does not by itself configure the flight
controller for GPS-denied control; that integration remains separate future work.

## Mapping

### Inputs and Outputs

The current design direction is to introduce depth when developing mapping,
combining 2D detections with corresponding depth, camera calibration, transforms,
and vessel state to locate observed buoys. The processing boundary between
depth-based observation positioning and map updates will be resolved during
mapping design.

Mapping will consume the project-owned state interface instead of subscribing
directly to MAVROS state topics. Maintain buoy geometry in a local metric
reference frame and attach a geographic reference when one is available.
The local frame is fixed at mapping-session start using flight-controller local
coordinates. Exact frame names and the geographic transformation remain open.

The primary requested mapping output is a costmap of the surrounding area.
Mapping should refine buoy locations as additional observations become
available. The user's current working assumption is that useful camera depth
extends to roughly 8 meters, while detections may occur farther away. This is
a provisional operating assumption to validate, not a hard sensor specification
or a guarantee that every closer depth sample is valid.

### Buoy Map Representation

Located buoys will remain represented in the costmap throughout the run,
including after they leave camera view. Losing visibility alone will not clear
their occupied area from the map.

Maintain buoy tracks with an internally assigned ID, category, estimated
position when available, uncertainty, observation count, and bounded observation
history, then derive the costmap from those tracks. Keep detections with
unresolved range as tentative bearing
observations rather than assigning them an arbitrary obstacle position.

### Depth Extraction and Obstacle Position

For initial ArUco observations, sample a small region around the marker center.
Reject invalid depth pixels and use the median of the accepted samples. Reject
the measurement if too few valid pixels remain or their variation is excessive.
Use a configurable maximum accepted depth of 8 meters initially. Patch size,
minimum valid-sample count, and variation thresholds require image testing.

The reconstructed position is a marker-surface observation, not an exact buoy
center. Use a conservative configurable obstacle footprint that accounts for
the marker-to-center offset, with dimensions determined from buoy geometry.
Rejecting depth preserves the detection's bearing for future localization work
but does not initialize a metric obstacle at an invented range.

### Costmap Output and Grid Configuration

Publish `/mapping/costmap` as `nav_msgs/msg/OccupancyGrid`. Start with a fixed
100 by 100-meter grid at 0.1-meter resolution, centered on the vessel's position
when mapping starts. Extent and resolution are configurable starting values.
Flag observations outside the grid instead of silently recentering it.

Mark confirmed buoy footprints occupied and retain unknown values elsewhere;
reliable free-water detection is not part of this first implementation. Show
position uncertainty separately in visualization. Boat-clearance inflation is
deferred to navigation design. Exact occupied-value encoding and publication
rate/QoS remain implementation-contract details to specify.

Rebuild occupied regions from retained buoy records so position refinement
removes obsolete footprints while preserving overlapping obstacles. The grid
is a representation of those records, not their only persistent storage.

### Approaches Under Consideration

| Approach | Treatment of distant detections | Main trade-off |
|---|---|---|
| Depth-first baseline | Retain category and bearing; initialize a metric buoy position only when acceptable depth becomes available. | Simple initial system, but distant detections cannot yet define a metric route or gate. |
| Depth plus bearing tracking | Combine accepted depth with repeated bearings from different vessel positions to refine or initialize buoy locations. | Uses distant observations, but requires reliable association, vessel state, and useful viewing geometry. |
| Geometric range estimates | Supplement observations with known-size marker/buoy geometry or a water-plane assumption. | Can suggest range without usable depth, but depends on object dimensions or camera/water geometry and may not transfer cleanly from ArUco to YOLO. |

The selected initial approach is the depth-first baseline. Depth plus bearing
tracking is a planned follow-up capability and a strong project priority,
rather than an optional idea to discard after the baseline works. Specific
estimation algorithms remain open. Geometric range estimation remains an
unselected alternative.

To support that progression, retain bounded observation histories with
category, source timestamp, camera identity, calibrated bearing, associated
vessel pose and uncertainty, and accepted depth when available. Define retention
limits during implementation design. Repeated markers identify categories only,
so cross-frame association must not assume a unique marker ID per buoy.

The follow-up milestone should demonstrate localization from multiple viewpoints
when depth is unavailable, rejection of ambiguous associations or insufficient
viewing geometry, and refinement when depth becomes available. Numerical
acceptance thresholds remain open.

### Observation Association and Map Updates

Initial assumption: buoys remain approximately stationary in the local map
frame during a run. Small apparent or physical movement from waves and moorings
is tolerated as observation variability; the initial mapper will not estimate
buoy velocity or predict buoy motion.

Match new metric observations to nearby records of the same category using
position uncertainty. If more than one association is plausible, leave the
observation unresolved rather than merging different buoys. A record starts
tentative and requires three consistent valid-depth observations to become
confirmed; this count is an adjustable initial value. Tentative records may
expire, with their timeout to be specified.

Refine confirmed positions with uncertainty-weighted updates and retain a
minimum uncertainty floor so repeated frames do not produce false confidence.
The weighting model must account for shared state-estimation errors rather
than treating every frame as independent evidence. Association gates,
consistency thresholds, and the uncertainty floor remain to be tuned.

Repeated observations will refine an estimated fixed buoy location. The planned
bearing-based localization follow-up will initially use the same stationary-buoy
assumption. Association gates, allowable variability, and outlier thresholds
remain to be defined.

### Mapping Assumptions and Limitations

The first version is restricted to open water where marked buoys are the only
obstacles the sensing and mapping system is expected to represent. The operator
pilots the boat; automatic obstacle avoidance is deferred. Shorelines, other
vessels, unmarked objects, and moving obstacles are outside this initial mapping
scope. This is an operating-environment assumption, not evidence that the system
can detect those hazards.

Missing buoy detections do not establish that an area has been observed clear.
Cells outside confirmed obstacle footprints remain unknown initially.
The policy for entering
unobserved areas belongs to later navigation design.

The stationary-buoy assumption is a deliberate initial simplification, not a
claim that real buoys never move. Sustained drift, moving obstacles, or a buoy
being relocated require revisiting association and track-update behavior.
Motion inconsistent with the assumption must not be silently averaged into a
confident fixed position; detection and handling of that inconsistency remain
open design work.

### Uncertainty and Map Lifecycle

Retain confirmed buoy estimates for the entire run, updating them as valid new
observations arrive. Empty detection arrays, occlusion, and leaving camera view
will not by themselves remove a mapped buoy. Refining a position should update
its costmap footprint without leaving a trail of obsolete occupied cells.

Retaining buoy estimates does not require retaining every source image or an
unbounded observation history. Track storage and observation-history limits are
separate design choices. Confirmed records persist until a session reset;
automatic deletion is not part of the initial version. Confirmation reduces
false detections but cannot guarantee their absence.

Provide explicit start, pause, and reset mapping operations. Start each session
with an empty map and do not automatically reload previous maps. Pausing stops
map updates while retaining the display; resetting clears session map state.
Support optional export of a map snapshot and buoy records for inspection.
The operation interfaces and export format remain to be specified.

### Live Mapping Visualization

The operator must be able to watch the costmap build and update while manually
piloting. It should show the vessel's pose and retained buoy obstacle regions
in a common local reference frame. Use RViz2 with a saved configuration showing
the costmap, boat pose, camera image, buoy-category labels, and uncertainty
outlines. This milestone does not require
the future GCS application or a running navigation planner/controller.

## Planning and Navigation

This entire section records future direction. Planning and autonomous motion
control are excluded from the first sensing and mapping implementation.

### Inputs and Outputs

### Navigation Framework and Algorithms

The intended direction is to use Nav2 or a comparable planning framework with
the perceived costmap. Final framework and plugin selection remain open.
ArduPilot will own low-level vessel movement control; onboard autonomy will
choose where to go and monitor execution.

Draft integration recommendation: use costmap-based path planning and a route
execution component that sends intermediate position targets through MAVROS to
ArduPilot. Nav2's standard controller produces velocity commands, so this
position-target approach requires deliberate integration rather than assuming
the complete default Nav2 control pipeline can be connected unchanged.

### Route Generation and Obstacle Handling

### Movement Commands and MAVROS Interface

The preferred direction is to command target locations and let ArduPilot
control steering and thrust toward them. Guided-mode local or global position
targets are candidates; the exact MAVROS interface, target frames, update
policy, speed constraints, and arrival behavior remain to be designed.

ArduPilot provides feedback control and boat position-maintenance behavior,
but disturbance rejection is bounded by tuning, state-estimate quality, vessel
dynamics, and available thrust. It does not automatically consume the ROS
costmap. Autonomy must account for clearance, route deviation, and replanning;
waypoint execution must be tested for turns and overshoot near buoys.

### Progress Monitoring and Replanning

## Mission Management

### Mission Definitions and Objectives

### Mission States and Transitions

### Component Coordination

### Start, Stop, and Completion Conditions

## Operator Authority and Failure Handling

### Command Ownership and Arbitration

### Arming, Disarming, and Manual Control

### Connection Loss and Degraded Operation

### Fault Detection and Recovery

## Ground Control Station

### Frontend and Backend Organization

### Telemetry and Command Interfaces

### Vessel, Map, and Mission Visualization

### Operator Interactions and Command Feedback

### Hosting and Communication Transport

## Simulation and Adapter

### Adapter Responsibilities and Vehicle Interface

The selected Adapter is a bidirectional environment-facing data layer. It owns
camera drivers or Gazebo bridges, camera calibration and mounting transforms,
MAVROS startup/configuration, flight-controller transport, and connection/data
availability diagnostics. Shared autonomy owns perception, state integration,
mapping, navigation, and mission decisions.

Both Adapters expose `/mavros/...` directly for telemetry, commands, services,
and acknowledgments. No additional command wrapper is required by this design.
The Simulation Adapter connects MAVROS to SITL; the Hardware Adapter connects
it to the physical flight controller. Command authority and arbitration belong
to the later control/authority design, not to Adapter transport responsibilities.

The Simulation Adapter implements this ownership boundary in
`Adapter/simulation/ros_ws/`. Its pinned MAVROS packages and canonical runtime
configuration implement the [MAVROS contract](contracts/mavros_adapter_contract.md).
Shared autonomy currently contains only an explicit simulation bootstrap;
implementing the Hardware Adapter remains deferred.

### Gazebo-to-ROS Bridges

The Simulation Adapter translates Gazebo camera data and calibration into the
common camera interface and exposes simulation time. Bridge mappings and sensor
QoS are configured in `blueboat_sim_bringup/config/`; camera normalization and
source-availability diagnostics implement the camera contract. Vehicle traffic
uses MAVROS connected to SITL rather than the camera bridge.

### Simulation Frames and Sensor Configuration

Each Adapter publishes the fixed transform from `base_link` to each configured
`camera_N_link` and from that mounting frame to `camera_N_optical_frame`.
Mounting transforms reflect the simulated installation or physical calibration.
Shared state integration owns estimated vessel-motion transforms, such as
`odom -> base_link`; exact navigation frame names remain open.

### Scenario Configuration

### Evaluation-Only Ground Truth Interfaces

Preserve the current separation of perfect vessel/buoy poses under
`/blueboat/ground_truth/...`, including the separate evaluation topics
`/blueboat/ground_truth/tf` and `/blueboat/ground_truth/tf_static`.
Evaluation tools may compare perceived state and maps against these references.
Autonomy must obtain vessel state through MAVROS and buoy locations through
observations; perfect motion must not populate the shared navigation TF tree.
Camera mounting transforms remain available on ordinary `/tf_static`.
This separation is a topic contract, not an enforced access restriction.

### Simulation Limitations

The initial supported workflow is one uninterrupted simulation run per mapping
session. Pause/resume, resetting Gazebo while autonomy remains running, and
recovery across partial stack restarts are unsupported. The operator starts
and stops the complete stack. Timestamp compatibility and stale-data rejection
are still required during normal operation.

This excludes simulator pause/reset recovery, not the separately agreed mapping
start/pause/reset operations or handling of a flight-controller estimator-origin
change during a running session.

## Deployment and Runtime Lifecycle

### Container Boundaries and Dependencies

The target simulation stack has Simulation, Simulation Adapter, and shared
autonomy services. Physical deployment selects the Hardware Adapter in place
of the Simulation Adapter. MAVROS belongs to the selected Adapter; shared
autonomy consumes its ROS interfaces. The current simulation deployment uses
this boundary with a non-commanding autonomy bootstrap. GCS deployment remains
later work.

### Simulation Bringup

### Physical Vessel Bringup and Hardware Access

### Startup, Readiness, and Shutdown

Each fresh simulation launch starts a new mapping session with an empty map
and empty observation buffers. This application-session policy does not require
wiping persisted SITL parameters or deleting simulation logs. Stop the complete
stack to end a run; no pause/resume or partial-restart recovery is required for
the first version.

The current simulation launcher starts Gazebo/SITL, then waits for fresh
Simulation Adapter camera and FCU source-readiness diagnostics before starting
the bootstrap. Service exit or sustained unhealthy status stops the complete
stack. Bootstrap health is only process liveness; mission readiness stays false.
Launch configuration, scenario identity, and service logs are retained under
`Simulation/logs/runs/$RUN_ID/`. See the
[maintenance guide](../Simulation/docs/DEVELOPMENT.md) for startup timeouts,
shutdown cleanup, and parameter persistence. This infrastructure does not
implement mapping-session lifecycle or partial-restart recovery.

### Software Versions and Platform Compatibility

### Compute, Memory, and Communication Budgets

## Logging and Diagnostics

### Runtime Logs and Diagnostic Status

Draft perception diagnostics should distinguish waiting for an image, processing
successfully with zero detections, and image-conversion or detection failures.
Log configuration errors clearly and throttle repeated runtime error messages.
Measure received, processed, replaced, and failed image counts plus processing
duration. Debug-image failure should not suppress otherwise valid detections.
Camera-loss timeout, diagnostic publication interface, and stale-result handling
remain open. Diagnostics do not choose vessel recovery actions.

### Data Recording and Retention

## Verification and Acceptance

### Component Tests

Draft perception tests:

| Case | Expected evidence |
|---|---|
| Each supported marker | Correct category for IDs 0–3 and a box enclosing the marker. |
| Several markers, including repeated IDs | Separate detections for separate image regions, even for the same category. |
| Blank image or only unmapped IDs | Empty detection array with the original header. |
| Unmapped ID with debugging enabled | Numeric ID and `unmapped ID` label visible, with no buoy detection for it. |
| Rotated and perspective-transformed markers | Valid axis-aligned boxes in original image coordinates for detected markers. |
| Invalid image or processing failure | Error indication, without publishing a misleading empty result. |
| Invalid parameter mapping | Clear startup failure. |

Use image fixtures with independently known marker locations to check box
geometry. Include border cases, blur, occlusion, and small markers to characterize
the operating limits; detection of every degraded marker is not assumed.

### Interface and Integration Tests

State-interface acceptance checks must verify that each agreed MAVROS input is
republished with unchanged values, timestamps, frame IDs, covariance, and status.
Verify that missing or stale inputs are not republished as fresh measurements.

Draft: publish controlled image streams into a running ROS node and verify
message types, category strings, headers, empty tracking IDs, and pixel boxes.
Test debug output both enabled and disabled. Run two instances with different
input streams and confirm there is no cross-camera output mixing.

For overload testing, introduce a controlled processing delay and publish images
with identifiable timestamps faster than processing can finish. Verify that
the worker replaces pending frames, output stays tied to processed inputs,
and no unbounded queue develops. Stop the image publisher and confirm no new
empty observations are fabricated. Test QoS compatibility with the actual bridge.

### Simulation Regression and Mission Evaluation

Draft: validate real camera-to-detector output with the simulator's ArUco scenes,
checking category labels and marker boxes in annotated images. The detector
must run without depth, vessel state, scenario manifests, or ground-truth topics.
Evaluation clients may use scenario references separately.

The current scenario generator requires unique marker IDs and names tied to
those IDs (`Simulation/scripts/render_scenario.py`). It needs a later change
before simulation can test several buoys of the same category. Existing model
colors also need alignment with the agreed category mapping: marker 0 is
currently described as orange rather than white, and marker 3 as yellow rather
than blue. These are integration tasks,
not changes made by this design document.

Run `make validate` from `Simulation/` before building. After integration,
run the relevant perception checks and existing control smoke test; changes to
models, scenarios, bridges, or frames also require `make verify-rgbd`. Record
semantic results and annotated samples. A perception pass demonstrates detection
only; mapping and autonomous movement require later acceptance tests.

### Hardware and Real-Water Validation

Draft: validate the same interface with physical camera images and ArUco markers
before claiming hardware compatibility. Later YOLO validation needs labeled
real buoy imagery covering the four categories and representative water
conditions. Successful simulated marker detection does not establish YOLO or
real-water detection performance.

### Acceptance Criteria and Requirements Traceability

The first integrated milestone is a manually piloted mapping demonstration:
live camera detections and the project-owned state interface support a visible
costmap built from accepted depth observations. Drive past marked buoys, turn
away, and revisit them to verify persistence and location refinement without
duplicate obstacles or stale footprints. The sensing and mapping stack must not
issue motion commands. Motion remains under operator control.

The agreed mapping acceptance run must:

- Observe all four categories, including two distinct buoys of the same category.
- Turn away and verify that confirmed buoys remain in the costmap.
- Revisit buoys and verify position refinement without duplicate obstacles or
  obsolete occupied footprints.
- Supply invalid depth and interrupt state data, verifying that affected
  observations do not corrupt the map.
- Reset the estimator and verify that mapping pauses with the old map visible.
- Verify that the sensing and mapping stack sends no movement commands.

Compare buoy positions with simulation truth only in the separate evaluator.
Measure position error and update latency before selecting numerical pass
thresholds. Check visualization, session reset, and out-of-grid diagnostics
alongside the manually piloted run.

Draft: the initial perception milestone requires correct category mapping,
image-space boxes, preserved source headers, repeated-category handling, empty
results, unmapped-ID behavior, optional debug output, per-camera isolation, and
bounded pending-image storage. Each behavior is covered by the tests above.
Numerical limits for box error, detection recall, false positives, latency, and
throughput remain open until the operating envelope and target hardware are
measured. No runtime acceptance results are claimed in this document.

### Proposed Perception Development Sequence

1. Review the draft ROS configuration and resolve confidence-score semantics.
2. Build the ArUco detector and image-fixture tests behind the agreed interface.
3. Add per-camera launch configuration, diagnostics, and ROS integration tests.
4. Align simulator category assets and enable repeated-category scenarios.
5. Run live perception checks and required simulator regressions; measure
   latency and detection limits to establish numerical acceptance criteria.

Depth integration and YOLO implementation follow in later design work.

The broader first implementation adds the state relay, depth-based mapping,
and live costmap visualization after the perception foundation. YOLO,
bearing-based localization, path planning, and autonomous control are later
milestones; bearing-based localization remains a planned priority.

## Open Design Decisions

- Specify exact state/map frame names and geographic transformation under the
  agreed ownership split (Adapter camera transforms; state integration motion TF),
  reset detection, synchronization tolerances, and state diagnostics.
- Tune depth patch and validity thresholds, association gates, uncertainty
  weighting/floor, and tentative-record expiry using representative data.
- Define mapping operation interfaces, export format, grid encoding/publication
  settings, and numerical mapping acceptance thresholds.
- Review draft package implementation, topic names, QoS, parameter defaults,
  diagnostics, and test plan.
- Define ArUco confidence-score semantics without implying a calibrated
  probability or treating them as interchangeable with YOLO scores.
- Select camera-loss and stale-observation thresholds and their diagnostic
  behavior; vessel response belongs to subsequent autonomy design.
- Confirm OpenCV version, image encodings, detector tuning, and measurable
  performance targets using representative images and hardware.
- Implement physical camera remaps and mounting calibration using the agreed
  generic convention before hardware depth/state integration. Simulation
  camera remaps and frame normalization are already implemented.

## References

- [ROS vision_msgs interface overview](https://github.com/ros-perception/vision_msgs/blob/ros2/README.md)
- [Detection2D message definition](https://github.com/ros-perception/vision_msgs/blob/ros2/vision_msgs/msg/Detection2D.msg)
- [BoundingBox2D message definition](https://github.com/ros-perception/vision_msgs/blob/ros2/vision_msgs/msg/BoundingBox2D.msg)
- [ROS 2 Jazzy QoS documentation source](https://github.com/ros2/ros2_documentation/blob/jazzy/source/Concepts/Intermediate/About-Quality-of-Service-Settings.rst)
- [OpenCV ArUco detection documentation](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html)
- [MAVROS local-position interfaces](https://github.com/mavlink/mavros/blob/ros2/docs/plugins/std/local_position.md)
- [MAVROS global-position implementation](https://github.com/mavlink/mavros/blob/ros2/mavros/src/plugins/global_position.cpp)
- [ArduPilot Rover Guided mode](https://ardupilot.org/rover/docs/guided-mode.html)
- [ArduPilot boat configuration](https://ardupilot.org/rover/docs/boat-configuration.html)
- [Nav2 configuration and server responsibilities](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/)
- [ROS 2 OccupancyGrid message](https://github.com/ros2/common_interfaces/blob/jazzy/nav_msgs/msg/OccupancyGrid.msg)
- [RViz2 display interfaces](https://github.com/ros2/rviz/blob/jazzy/rviz_default_plugins/plugins_description.xml)
