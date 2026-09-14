# Common Camera Adapter Contract

**Contract ID:** `maritime.camera_adapter`

**Contract version:** `1.0.0`

**Status:** Normative for Simulation and Hardware Adapter implementations

This document freezes the camera-neutral observation boundary presented to
shared autonomy. Camera drivers, simulator topic names, device identities, and
registration implementations remain private to their environment Adapter.
Neither environment may expose those private names as an autonomy dependency.

## Normative deployment configuration

The public names and message semantics in this contract are fixed. Deployment
configuration selects the environment, its camera roster, mounting transforms,
and per-camera timing limits. Version `1.0.0` accepts exactly these fields:

```yaml
contract_id: maritime.camera_adapter
contract_version: 1.0.0
environment: simulation
use_sim_time: true
enabled_cameras:
  - camera_0
cameras:
  camera_0:
    mount_parent_frame: base_link
    mount_xyz_m: [0.35, 0.0, 0.40]
    mount_rpy_rad: [0.0, 0.0, 0.0]
    registration_mode: color
    registration_evidence_ref: simulation-rgbd-registration
    timing:
      rgb_depth_match_tolerance_ns: 0
      max_acquisition_age_ns: 100000000
      max_arrival_silence_ns: 2000000000
      evidence_ref: simulation-camera-timing-2026-09-13
```

The canonical enabled roster is `[camera_0]` for simulation and
`[camera_0, camera_1]` for hardware. Roster order is stable deployment order;
it is not a priority order. `cameras` must contain exactly the roster keys.
Camera IDs must match `^camera_[0-9]+$`, be unique, and remain assigned to the
same physical mounting position across launches. Consumers must enumerate
`enabled_cameras`; they must not infer a camera count, probe sequential names,
or branch on a camera make or model.

For hardware, `environment: hardware` and `use_sim_time: false` are fixed, but
this common contract supplies no timing values. The Hardware Adapter deployment
must explicitly provide all three integer timing fields and a non-empty
`evidence_ref` independently for `camera_0` and `camera_1`. There is no default,
inheritance, environment-variable fallback, or substitution from the simulation
values. Missing, null, non-integer, or out-of-range hardware timing fields make
camera source readiness false and prohibit camera publication from being
treated as conforming. Hardware remains unverified for vessel readiness until
the referenced representative simultaneous dual-camera capture approves those
values.

Every `cameras.camera_N` record has exactly this schema:

| Field | Type and rule |
|---|---|
| `mount_parent_frame` | String exactly `base_link`. |
| `mount_xyz_m` | Three finite numbers in metres, ordered x, y, z. |
| `mount_rpy_rad` | Three finite numbers in radians, ordered roll, pitch, yaw. |
| `registration_mode` | String exactly `color`. |
| `registration_evidence_ref` | Non-empty string identifying the environment's geometric registration acceptance record. |
| `timing.rgb_depth_match_tolerance_ns` | Integer greater than or equal to zero; per-camera measured limit. |
| `timing.max_acquisition_age_ns` | Positive integer greater than the match tolerance; per-camera measured limit. |
| `timing.max_arrival_silence_ns` | Positive integer; per-camera measured steady-clock watchdog. |
| `timing.evidence_ref` | Non-empty string identifying the timing measurement record. |

The camera deployment configuration is authoritative for the simulated mount.
If a versioned scenario manifest repeats camera-mount data for evaluator
geometry, the renderer must copy these configured values and validation must
require equality. Shared autonomy and hardware must not consume the
simulation-only scenario manifest.

Configuration validation is fail closed:

- `contract_id`, `contract_version`, `environment`, `use_sim_time`,
  `enabled_cameras`, and `cameras` are required; fields unknown to version
  `1.0.0` are rejected.
- `environment` is exactly `simulation` or `hardware`, and `use_sim_time` must
  match the environment rule above.
- Every mount array contains exactly three finite numbers. The parent frame is
  `base_link`; no world, simulator-truth, or vendor frame is permitted.
- `registration_mode` is exactly `color`, and
  `registration_evidence_ref` is a non-empty identifier for the geometric
  registration acceptance record. Hardware supplies its own record.
- `rgb_depth_match_tolerance_ns` is an integer greater than or equal to zero.
  Both freshness values are positive integers, and
  `max_acquisition_age_ns` must be greater than the match tolerance.
- `evidence_ref` is a non-empty identifier for the measurement record that
  justified all numerical timing limits.

An Adapter with invalid configuration may keep a supervisory process alive so
it can publish diagnostics, but it must not report source readiness. It must
publish an `ERROR` configuration diagnostic and must not silently start a
partial roster.

### Simulation timing evidence and scope

The simulation values above are based on measurements of the current generic
RGB-D source. A source-level sample produced 115 of 115 exact color/depth stamp
pairs with 33 ms simulated-time gaps. A separate ROS sample observed acquisition
ages around 34 ms, with 37 ms as the largest color age. Therefore simulation
requires exact matching and uses 100 ms as its initial acquisition-age ceiling.

The same ROS probe was intentionally a serial Python subscriber under software
rendering. Its delivery gaps were load- and tool-dependent and reached about
1.7 s, even though source stamps remained regular. The 2 s steady-clock arrival
watchdog is consequently a conservative simulation migration setting, not a
camera rate claim and not a hardware limit. A source-level software-rendered
probe had wall-gap maxima of about 276 ms. Retained hardware-rendered simulator
evidence separately recorded 120 exact pairs and approximately 30.30 Hz in
simulated time. None of these results measures physical cameras or authorizes
hardware timing values.

## Public ROS surface

For every configured `camera_N`, the Adapter exposes exactly these stable
interfaces:

| Interface | Message type | Required meaning |
|---|---|---|
| `/sensors/camera_N/color/image_raw` | `sensor_msgs/msg/Image` | Color acquisition in one accepted encoding. |
| `/sensors/camera_N/depth/image_rect_raw` | `sensor_msgs/msg/Image` | Depth registered pixel-for-pixel to the color image. |
| `/sensors/camera_N/color/camera_info` | `sensor_msgs/msg/CameraInfo` | Calibration and raster geometry for both public images. |
| `/tf_static` | `tf2_msgs/msg/TFMessage` | The configured `base_link -> camera_N_link -> camera_N_optical_frame` static chain. |
| `/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | Per-camera contract and readiness status. |

The three sensor topics use best-effort reliability, volatile durability,
keep-last history, and queue depth 1. This favors current observations and does
not promise lossless delivery. `CameraInfo` is published with every color frame;
a late subscriber waits for the next acquisition rather than receiving an
unpaired latched calibration. Tests and consumers must request compatible QoS.

No private source topic, device name, frame, or model identifier is part of the
public contract. Additional public camera topics require a compatible contract
revision before autonomy may depend on them.

## Color representation

The only accepted public color encodings are `rgb8` and `bgr8`. The encoding in
each `sensor_msgs/msg/Image` is authoritative; consumers must handle both or
perform an explicit local conversion. An Adapter receiving another upstream
encoding must convert it to one accepted encoding before publication without
resizing, cropping, changing the acquisition stamp, or relabeling its frame.

`width` and `height` must be positive, `step` must describe the actual row
layout, and the data length must agree with `step * height`. No public consumer
may embed a resolution constant. It obtains raster dimensions from the paired
`CameraInfo` and verifies the image fields agree.

## Canonical registered depth

`32FC1` in metres is the selected canonical depth representation. Each finite,
positive float is the optical-axis `Z` distance from
`camera_N_optical_frame` to the surface represented at the same pixel in the
color image. Public depth is IEEE-754 single-precision data, and
`is_bigendian` must accurately describe its byte order.

The only canonical invalid-pixel representation is quiet `NaN`. An Adapter must
convert zero, negative values, positive or negative infinity, upstream `NaN`,
and driver-specific invalid or no-return sentinels to quiet `NaN`. Consumers
must accept only finite values greater than zero as valid depth and must never
treat an invalid pixel as zero range.

An upstream `16UC1` millimetre image is converted pixel-by-pixel as follows:
zero becomes quiet `NaN`; every other value becomes
`float32(raw_value) * 0.001` metres. Any other upstream unit requires an
explicit Adapter conversion scale recorded in private deployment configuration;
unit inference is forbidden. Registration, unit conversion, and invalid-value
normalization occur before publication. The Adapter must not clip a valid range,
fill invalid pixels, or synthesize depth merely to satisfy readiness.

## Registration, calibration, and dimensions

Depth is registered to color: pixel `(u, v)` in the depth image describes the
same viewing ray and color sample as pixel `(u, v)` in the paired color image.
Equal dimensions alone do not prove registration. The Adapter must use an
upstream aligned product or perform calibrated registration, and its acceptance
record must include a geometric registration check. Unregistered depth must not
be published on the public depth topic.

For every accepted color/depth pair:

- Color, depth, and `CameraInfo` have identical positive `width` and `height`.
- All three headers use `camera_N_optical_frame`.
- `CameraInfo.header.stamp` exactly equals the color acquisition stamp.
- `CameraInfo` describes the color raster and therefore the registered depth
  raster. Its `K`, `R`, and `P` arrays contain finite calibrated values;
  `K[0]`, `K[4]`, `P[0]`, and `P[5]` are positive, while `K[8]` and
  `P[10]` equal 1. An uncalibrated all-zero matrix is invalid.
- `distortion_model` is exactly `plumb_bob`, `rational_polynomial`, or
  `equidistant`. `D` contains respectively 5, 8, or 4 finite coefficients.
  The images share this declared pixel geometry; the topic spelling does not
  imply that distortion coefficients are zero.
- Any binning and region-of-interest fields describe the published raster, and
  the supplied intrinsics are already adjusted for them. Consumers must not
  scale intrinsics from a remembered source resolution.

A calibration update is permitted only at an acquisition boundary. The new
`CameraInfo` accompanies the first color frame using it, and registered depth
for that pair must use the same geometry. A changed dimension, distortion model,
or intrinsic matrix without the matching `CameraInfo` is a contract error.

## Frames and transforms

`camera_N_link` is the configured mounting frame. It uses ROS body axes: `x`
forward, `y` left, and `z` up. `camera_N_optical_frame` uses ROS optical axes:
`z` forward, `x` right, and `y` down. The Adapter owns and publishes the static
chain from `base_link` through both frames. Each child has one parent, the chain
is available before source readiness becomes true, and transforms agree with
the configured mount.

All three public message headers name `camera_N_optical_frame`. Renaming a
header without transforming the data is forbidden. Simulator truth may not
provide or replace any public camera transform. Internal source frames may
remain private behind the Adapter.

## Acquisition timestamps and matching

Every sensor header stamp is the source acquisition time, not receipt,
conversion, registration-completion, or publication time. An Adapter may map a
device clock into the deployment's ROS time domain only with a measured clock
mapping that preserves the acquisition instant. It must not stamp `now` merely
to make a sample appear fresh. Timestamps are nonzero and strictly increase
within each of the color, depth, and `CameraInfo` streams.

Pairing is deterministic and performed independently for each camera:

1. Keep unmatched color, depth, and `CameraInfo` messages ordered by stamp.
   A non-monotonic or duplicate stamp is rejected and does not refresh status.
2. Color is the anchor. For the oldest color stamp `c`, wait until the latest
   depth stamp is at least `c + rgb_depth_match_tolerance_ns`, or until that
   color becomes stale.
3. Among unused depth messages in the inclusive interval
   `[c - tolerance, c + tolerance]`, select the one minimizing
   `abs(depth_stamp - c)`. A tie selects the earlier depth stamp. One depth
   message may be used once.
4. Require a `CameraInfo` message whose stamp equals `c`. There is no separate
   calibration matching tolerance. If the `CameraInfo` stream advances past
   `c` without that exact stamp, the triple is incompatible.
5. Emit the triple for downstream RGB-D use only after all structural,
   registration, frame, calibration, and freshness checks pass. If no valid
   depth candidate or exact calibration exists before expiry, reject the color
   anchor, report the cause, and never pair it later.
6. Discard unused messages older than the lower bound of the oldest remaining
   color anchor. An implementation must retain every non-expired candidate;
   inability to do so is a queue-overflow error that makes source readiness
   false. It must not silently drop data or change the configured tolerance.

With the simulation tolerance of zero, public color and depth stamps must be
identical. Hardware may use a nonzero measured tolerance, but that value is
local to each configured camera and does not permit timestamps to be rewritten.

## Freshness algorithm

The Adapter records a steady-clock arrival time for each structurally valid
message before conversion work. At every readiness evaluation, for each of the
three required streams, compute:

```text
acquisition_age_ns = deployment_ros_now_ns - latest_valid_header_stamp_ns
arrival_silence_ns = steady_now_ns - latest_valid_arrival_steady_ns
stream_fresh =
    0 <= acquisition_age_ns <= max_acquisition_age_ns
    and 0 <= arrival_silence_ns <= max_arrival_silence_ns
```

The deployment ROS clock must exist, be in the configured time domain, and be
advancing. A missing, incompatible, backward-moving, or unavailable clock makes
source readiness false; a frozen simulation clock cannot preserve a previous
fresh result merely because acquisition age stops increasing.

Camera source readiness for `camera_N` is true only when color, depth, and
`CameraInfo` are individually fresh and the most recent resolvable triple passes
the matching and content rules. Repeated invalid data does not update
`latest_valid_*`. Republishing an old sample with a new stamp is a contract
violation. A consumer applies the same age rule at use time; Adapter readiness
does not guarantee that an overloaded consumer receives every best-effort
sample.

## Diagnostics and failure behavior

The Adapter publishes standard `DiagnosticStatus` entries under these exact
names:

- `camera_adapter/configuration`
- `camera_adapter/camera_N/color`
- `camera_adapter/camera_N/depth`
- `camera_adapter/camera_N/registration`
- `camera_adapter/camera_N/calibration`
- `camera_adapter/camera_N/synchronization`
- `camera_adapter/camera_N/frames`
- `camera_adapter/camera_N/source_readiness`

Every per-camera entry includes `contract_version`, `camera_id`,
`source_ready`, the three configured timing limits, the three latest header
stamps and arrival silences when available, the latest RGB/depth skew, and a
machine-readable `reason` key. Values absent because no sample has arrived are
reported as `unobserved`, not zero.

Status behavior is exact:

| Condition | Level and behavior |
|---|---|
| Valid configuration but no first image or calibration yet | `STALE`; process may be live, source readiness is false, and startup continues without fabricating data. |
| Any required stream exceeds either freshness limit | That stream and source readiness are `STALE`; dependent RGB-D output is suppressed until a fresh valid triple arrives. |
| Missing hardware timing/evidence, unsupported encoding/unit/distortion, invalid calibration/dimensions, frame mismatch, unregistered depth, non-monotonic stamp, incompatible time domain, or RGB/depth skew above tolerance | Affected check and source readiness are `ERROR`; the invalid triple is rejected. |
| Valid current triple and all contract checks pass | Component entries and source readiness are `OK`. |
| Queue overflow or unmatched data that expires | Synchronization is `ERROR`; record rejected count and observed skew when available. |

Recovery requires a newly received conforming triple and current fresh streams;
changing a timestamp or clearing a diagnostic without new evidence is not
recovery. A partial roster never reports overall camera source readiness.

## Readiness boundaries

The following states are separate; no state implies a later one:

1. **Process liveness:** the Adapter process and ROS node respond. A live process
   may have invalid configuration, no camera data, or only diagnostics.
2. **Camera source readiness:** every configured camera is `OK` under this
   contract, including current images, calibration, matching, timing, and TF.
   A color-only consumer may use the exception below without claiming this
   RGB-D state.
3. **FCU readiness:** the independent MAVROS Adapter contract reports a fresh,
   connected, valid flight-controller boundary. Camera source readiness says
   nothing about the FCU, and FCU readiness says nothing about cameras.
4. **Mission readiness:** mission policy confirms the camera and FCU states plus
   required transforms, state-time compatibility, perception quality, command
   authority, operator link, health policy, and failsafes. This contract never
   declares mission readiness.

In simulation, camera messages use simulation time while the approved MAVROS
boundary retains its own timestamp behavior. Both components being individually
ready does not prove that camera observations can be combined with vessel state;
that cross-source timing check belongs to state integration and mission
readiness.

## Initial 2D perception exception

Initial 2D perception may operate before registered depth is ready only when it
enumerates a configured camera, consumes
`/sensors/camera_N/color/image_raw`, and has fresh matching `CameraInfo`. It may
convert `rgb8` and `bgr8` pixels internally, but every detection array and debug
image derived from a color frame must copy that input header unchanged. It must
derive dimensions and intrinsics from `CameraInfo`, must identify itself as
color-only, and must not report camera RGB-D readiness, metric depth, FCU
readiness, or mission readiness.

## Observable conformance checks

Contract automation must perform all of these assertions for every configured
camera:

1. Parse configuration before starting publishers; verify contract/version,
   exact environment roster, mount fields, explicit timing fields, evidence
   reference, and simulation/hardware time policy. Negative tests remove each
   hardware timing field in turn and require fail-closed source readiness.
2. Capture `ros2 topic list -t` and `ros2 topic info -v`; verify all public
   names, exact message types, and sensor QoS. Reject legacy or private camera
   names as public autonomy dependencies.
3. Sample color, depth, and `CameraInfo`; validate accepted encodings, canonical
   depth units and invalid pixels, data layout, matching dimensions, allowed
   distortion model and coefficient count, finite intrinsics, headers, and the
   deterministic matching algorithm.
4. Inspect `/tf_static`; require exactly one configured
   `base_link -> camera_N_link -> camera_N_optical_frame` chain per roster entry
   and reject truth or private source frames as public camera parents.
5. Measure stamps, receipt times, acquisition ages, arrival silences, exact or
   bounded RGB/depth skew, unmatched counts, and calibration pairing. Run longer
   than both configured freshness limits, then interrupt color, depth, and
   calibration separately and verify the specified `STALE` transitions.
6. Inject wrong encoding, units, dimensions, calibration, frame, registration,
   non-monotonic stamps, future/incompatible timestamps, and excessive skew;
   require `ERROR`, rejection, and no freshness reset.
7. Confirm the initial color-only perception path uses only generic topics,
   derives raster data from `CameraInfo`, and preserves the input header exactly.
8. Capture `/diagnostics`; compare entry names, levels, reasons, observed timing,
   and overall source-readiness state with this contract. Verify a healthy
   container or live node alone cannot satisfy source readiness.

The hardware timing check must run both configured cameras simultaneously on
the target compute and capture path, at intended deployment modes, under
representative processing load. Its evidence record must include unmodified
stamps, steady arrivals, skew and gap distributions, unmatched/drop counts,
clock mapping, and deliberate stream interruptions. Until that record approves
all three timing values for both cameras, Hardware Adapter and vessel readiness
remain unverified.

## Compatibility and change control

Contract versions use semantic versioning:

- **Patch:** clarification or stricter validation that changes no public name,
  type, encoding, unit, frame, timing value/algorithm, roster, QoS, or readiness
  meaning.
- **Minor:** backward-compatible addition; every version `1.0.0` interface and
  behavior remains available.
- **Major:** topic/frame rename, type or encoding removal, unit or invalid-value
  change, registration/calibration semantic change, roster change, timing field
  or algorithm change, QoS incompatibility, or changed failure/readiness meaning.

Simulation and Hardware Adapters may not advance versions independently. A
normalized conformance snapshot stores the public graph, QoS, configuration,
frames, diagnostics, and timing results under the contract version. Intentional
incompatible changes update this document and major version first, then both
Adapters, tests, and all consumers in one migration.

## Current implementation gap

The current Simulation Adapter still exposes legacy private camera paths and
frames rather than this public boundary. Its source data provides the measured
encoding, depth, calibration, and timing evidence used for the simulation
configuration, but source evidence is not contract conformance. A later
simulation migration must change bridges, frames, health/readiness diagnostics,
perception remaps, evaluators, and boundary tests together. The Hardware Adapter
and its deployment timing evidence do not yet exist; no claim of physical-camera
or vessel readiness is made.
