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
and per-camera timing limits. The complete simulation record is:

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

For `environment: simulation`, `enabled_cameras` must equal exactly
`[camera_0]`. For `environment: hardware`, it must equal exactly
`[camera_0, camera_1]` in that order. A missing, extra, reordered, or duplicate
entry is invalid. `cameras` must contain exactly the corresponding key set;
mapping-key order has no meaning. Camera IDs must match
`^camera_[0-9]+$`, remain assigned to the same physical mounting position
across launches, and be enumerated by consumers from `enabled_cameras`.
Consumers must not infer a camera count, probe sequential names, or branch on a
camera make or model.

For hardware, `environment: hardware` and `use_sim_time: false` are fixed, but
this common contract supplies no timing values. Hardware configuration adds a
required absolute `evidence_store_path`, mounted read-only, and must explicitly
provide all three integer timing fields independently for `camera_0` and
`camera_1`. Both `timing.evidence_ref` values and both
`registration_evidence_ref` values must be the same content reference for the
one simultaneous dual-camera evidence artifact defined below. There is no
default, inheritance, environment-variable fallback, or substitution from the
simulation values. Missing, null, non-integer, or out-of-range fields make
camera source readiness false and prohibit camera publication from being
treated as conforming. Hardware remains unverified for vessel readiness until
the artifact approves those exact values.

Every `cameras.camera_N` record has exactly this schema:

| Field | Type and rule |
|---|---|
| `mount_parent_frame` | String exactly `base_link`. |
| `mount_xyz_m` | Three finite numbers in metres, ordered x, y, z. |
| `mount_rpy_rad` | Three finite numbers in radians, ordered roll, pitch, yaw. |
| `registration_mode` | String exactly `color`. |
| `registration_evidence_ref` | Simulation uses its named local record; hardware uses the content reference required below. |
| `timing.rgb_depth_match_tolerance_ns` | Integer greater than or equal to zero; per-camera measured limit. |
| `timing.max_acquisition_age_ns` | Positive integer greater than the match tolerance; per-camera measured limit. |
| `timing.max_arrival_silence_ns` | Positive integer; per-camera measured steady-clock watchdog. |
| `timing.evidence_ref` | Simulation uses its named local record; hardware uses the content reference required below. |

The camera deployment configuration is authoritative for the simulated mount.
If a versioned scenario manifest repeats camera-mount data for evaluator
geometry, the renderer must copy these configured values and validation must
require equality. Shared autonomy and hardware must not consume the
simulation-only scenario manifest.

Configuration validation is fail closed:

- `contract_id`, `contract_version`, `environment`, `use_sim_time`,
  `enabled_cameras`, and `cameras` are required. `evidence_store_path` is
  required only for hardware and forbidden for simulation. Other fields unknown
  to version `1.0.0` are rejected.
- `environment` is exactly `simulation` or `hardware`, and `use_sim_time` must
  match the environment rule above.
- The selected roster must equal the environment's literal ordered list above;
  reason `roster_mismatch` covers missing, extra, reordered, duplicate, or
  map-key disagreement.
- Every mount array contains exactly three finite numbers. The parent frame is
  `base_link`; no world, simulator-truth, or vendor frame is permitted.
- `registration_mode` is exactly `color`, and
  `registration_evidence_ref` is a non-empty identifier for the geometric
  registration acceptance record. Hardware supplies its own record.
- `rgb_depth_match_tolerance_ns` is an integer greater than or equal to zero.
  Both freshness values are positive integers, and
  `max_acquisition_age_ns` must be greater than the match tolerance.
- Simulation evidence identifiers must equal the frozen values in the complete
  record. Hardware evidence references and artifacts must pass every check in
  the next section.

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

### Hardware evidence artifact and validator

A hardware evidence reference is exactly `sha256:<digest>`, where `<digest>` is
64 lowercase hexadecimal characters. It resolves only to the local regular
UTF-8 JSON file `<evidence_store_path>/<digest>.json`. Symlinks, path traversal,
remote references, and alternate filenames are rejected. Before parsing, the
validator hashes the exact file bytes with SHA-256 and requires equality with
the reference. The evidence store is mounted read-only; the runtime Adapter may
neither generate nor approve its own evidence.

Trust is owned by the **Maritime_2027 Release Maintainers**, not by either
Adapter, a deployment operator, or an evidence submitter. Their canonical
source is the version-controlled closed JSON manifest
`deployment/camera_evidence_trust.json` on the protected default branch. A
manifest change is valid only through a dedicated trust-change review approved
by two Release Maintainers other than the added, rotated, or revoked key's
holder; it must not be combined with Adapter runtime or deployment-configuration
changes. This repository review is the sole authority for adding trust.

The Hardware Adapter release build copies the reviewed manifest to the fixed
image path `/etc/maritime/camera_evidence_trust.json`, owned by root and mode
`0444`, and embeds the manifest's exact SHA-256 digest and integer
`manifest_version` in the validator. Startup hashes the installed manifest and
requires both embedded values. The path and digest are not configuration
fields, cannot be supplied by a volume, environment variable, command-line
argument, evidence artifact, or network lookup, and cannot be extended at
runtime. An image with a missing, writable, over-mounted, or differently hashed
manifest is non-conforming and reports `trust_store_invalid` before evidence is
examined.

The trust manifest has exactly `schema_id` (string
`maritime.camera_evidence_trust`), `schema_version` (integer `1`),
`manifest_version` (positive monotonically increasing integer), and `keys`
(non-empty array). Each key record has exactly `approved_by`, `approval_key_id`,
`public_key_ed25519`, `status`, `valid_from_utc`, and `revoked_at_utc`.
Identities and key IDs are unique non-empty strings; the public key is exactly
64 lowercase hexadecimal characters; `status` is `active` or `revoked`;
`valid_from_utc` is RFC 3339 UTC; and `revoked_at_utc` is null for an active key
or RFC 3339 UTC for a revoked key. Only the person or project role named by an
active `approved_by` entry may approve camera evidence, using that entry's
private key outside the runtime system.

Key addition creates a new active record. Rotation adds a new key ID and marks
the old record revoked; revocation marks the record revoked without removing
it. Each operation increments `manifest_version`, follows the separate review
rule, and requires a new Hardware Adapter release image. Evidence signed by a
revoked key, outside the key's validity interval, or against any other manifest
version/hash is rejected. A deployment must install the new approved image to
consume a trust update; it cannot patch trust into a running or existing image.

The JSON object is closed: unknown or missing fields are invalid. Its top-level
fields are exactly:

- `schema_id`: string exactly `maritime.camera_hardware_evidence`;
- `schema_version`: integer exactly `1`;
- `contract_id`: string exactly `maritime.camera_adapter`;
- `contract_version`: string exactly `1.0.0`;
- `validation`, `target`, `measurement`, and `approved_timing`: the closed
  objects defined below.

`validation` has exactly `status`, `validator_id`, `validator_version`,
`trust_manifest_version`, `trust_manifest_sha256`, `approved_by`,
`approved_at_utc`, `approved_payload_sha256`, `approval_key_id`, and
`approval_signature_ed25519`. `status` is exactly `approved`,
`validator_id` is exactly `maritime_camera_hardware_evidence_validator`, and
`validator_version` is exactly `1.0.0`. `approved_by` is a non-empty external
approval identity and `approved_at_utc` is an RFC 3339 UTC timestamp.
`trust_manifest_version` and `trust_manifest_sha256` must exactly equal the
embedded positive integer version and `sha256:<digest>` of the installed trust
manifest.
`approved_payload_sha256` is a `sha256:<digest>` of the RFC 8785 canonical JSON
object containing exactly `contract_id`, `contract_version`, `target`,
`measurement`, and `approved_timing` from the artifact. `approval_key_id` must
resolve to the same active trust-manifest record as `approved_by`, and
`approved_at_utc` must fall on or after its `valid_from_utc` while the key has
not been revoked. `approval_signature_ed25519` is the lowercase hex Ed25519
signature by that key over the RFC 8785 canonical JSON bytes of the other nine
`validation` fields. The validator recomputes the payload hash and verifies the
signed identity, status, time, validator version, trust-manifest binding, and
payload hash together. Approval is produced offline after evidence review,
never inferred from measurements or filled by the Adapter; a user-supplied key
or self-signed artifact is rejected.

`target` has exactly `compute_platform_id`, `adapter_image_digest`,
`driver_version`, `capture_topology_id`, `capture_configuration_sha256`, and
`cameras`. The first four are non-empty deployment identifiers and
`adapter_image_digest` is a `sha256:<digest>` reference.
`capture_configuration_sha256` is a `sha256:<digest>` of the RFC 8785 canonical
JSON bytes of `target.cameras`. `target.cameras` has exactly `camera_0` and
`camera_1`. Each camera object has exactly:

- `source_identity_sha256`: a `sha256:<digest>` of the private stable device
  identity; a raw serial or model name is not exposed;
- `physical_port`: a non-empty stable deployment port identifier;
- `width_px` and `height_px`: positive integers;
- `frame_rate_hz`: a positive finite number;
- `color_encoding`: exactly `rgb8` or `bgr8`;
- `depth_encoding`: exactly `32FC1`.

The validator obtains the running compute, Adapter image, driver, topology,
device-identity hashes, ports, and capture modes independently and requires
exact equality with `target`; it does not trust configuration to attest to
itself.

`measurement` has exactly `simultaneous`, `camera_roster`, `started_at_utc`,
`duration_ns`, and `per_camera`. `simultaneous` is exactly `true`,
`camera_roster` is exactly `[camera_0, camera_1]`, `started_at_utc` is RFC 3339
UTC, `duration_ns` is a positive integer, and `per_camera` has exactly those two
camera keys. Each per-camera object has exactly:

- positive integer `color_sample_count`, `depth_sample_count`,
  `camera_info_sample_count`, and `matched_triple_count`, each at least 1000;
- non-negative integer `unmatched_color_count`, `unmatched_depth_count`, and
  `dropped_or_overflow_count`;
- integer `camera_info_stamp_mismatch_count`, `nonmonotonic_stamp_count`,
  `future_acquisition_count`, and `negative_arrival_silence_count`, all exactly
  zero;
- `rgb_depth_abs_skew_ns`, `acquisition_age_ns`, and `arrival_silence_ns`, each
  a closed object containing non-negative integer `p50`, `p95`, `p99`, and
  `max`, ordered `p50 <= p95 <= p99 <= max`;
- `clock_mapping`, a closed object with non-empty `description` and
  non-negative integer `max_mapping_error_ns`;
- `registration`, a closed object with `status` exactly `approved`, integer
  `sample_count` at least 1000, and finite non-negative
  `max_alignment_error_px`;
- `interruptions`, a closed object whose `color_stale`, `depth_stale`, and
  `camera_info_stale` fields are all exactly `true`.

`approved_timing` has exactly `camera_0` and `camera_1`; each has exactly the
three integer timing fields from deployment configuration. Approved match
tolerance must be at least the measured skew `max`, approved acquisition age
must be at least the measured acquisition-age `max`, and approved arrival
silence must be at least the measured arrival-silence `max`. The running
configuration must equal these approved values exactly, not merely remain
inside their bounds.

Hardware validation is ordered and fail closed:

1. Validate the literal roster and closed deployment schema.
2. Require all four per-camera evidence-reference fields to be identical and
   syntactically valid.
3. Resolve the regular file and verify its content hash before JSON parsing.
4. Verify the installed trust manifest against the image-embedded hash and
   version. Then validate the closed evidence schema and versions, recompute the
   approved payload hash, require `approved_by` and `approval_key_id` to resolve
   to the same active in-validity trust entry, verify the signed validation
   fields, and require external approved status.
5. Match every target field and the canonical capture-configuration hash to the
   running deployment.
6. Validate simultaneous measurement, counts, zero-violation fields,
   distributions, registration approval, and all three interruption results.
7. Require the configured timing values to equal `approved_timing` and require
   those values to bound the reported maxima.

Any failure is a configuration `ERROR`, prevents publishers from being treated
as conforming, and makes every hardware camera's source readiness false. The
reason mapping is exact:

| Failure | Diagnostic `reason` |
|---|---|
| Image-pinned trust manifest is missing, writable, over-mounted, malformed, wrong-version, or wrong-hash | `trust_store_invalid` |
| Required store path, reference, or evidence field is absent | `evidence_missing` |
| File does not resolve under the path policy, is not regular/read-only, or cannot be read | `evidence_unresolved` |
| Exact file-byte digest differs from the content reference | `evidence_hash_mismatch` |
| Reference syntax, JSON, closed schema, field type, artifact/contract version, canonical hash format, measurement count, metric, or invariant is invalid | `evidence_schema_invalid` |
| Approved-payload digest, approval identity/key membership, key validity/revocation state, trust-manifest binding, or Ed25519 signature does not verify | `evidence_signature_invalid` |
| Verified artifact status is not `approved` | `evidence_unapproved` |
| Running target identity or capture configuration differs | `evidence_target_mismatch` |
| Configured values differ from `approved_timing` or fail to bound a measured maximum | `evidence_timing_mismatch` |

Thus a syntactically bogus but non-empty reference, a self-authored artifact
with invented timing values, or an approved artifact copied from another
deployment cannot pass. No conforming hardware evidence artifact currently
exists.

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
   `[c - timing.rgb_depth_match_tolerance_ns,
   c + timing.rgb_depth_match_tolerance_ns]`, select the one minimizing
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

Candidate samples are checked before promotion to `latest_valid_*`. If
`acquisition_age_ns < 0`, the sample is rejected, no latest-valid header or
arrival state is refreshed, and the stream and source-readiness diagnostics are
`ERROR` with reason `future_acquisition_stamp`. This denotes a future stamp or
an incompatible or backward-moving deployment clock; it is not ordinary
latency. If `arrival_silence_ns < 0`, the sample and that readiness evaluation
are rejected without refreshing latest-valid state, and the stream and source
readiness are `ERROR` with reason `steady_clock_regression`. This denotes a
non-monotonic steady clock or an arrival recorded in an incompatible clock
domain. A duplicate or decreasing source stamp is likewise rejected without a
refresh and reports `ERROR` reason `nonmonotonic_header_stamp`.

Only non-negative deltas proceed to upper-bound freshness evaluation.
`acquisition_age_ns > max_acquisition_age_ns` is `STALE` reason
`acquisition_timeout`; `arrival_silence_ns > max_arrival_silence_ns` is `STALE`
reason `arrival_timeout`. At each evaluation, state precedence is exact:
configuration, evidence, clock-domain, negative-delta, and content violations
produce `ERROR` first; absent/unobserved data or a positive upper-bound timeout
produces `STALE` only if no `ERROR` applies; `OK` is possible only if neither
applies. The aggregate severity order is `ERROR` greater than `STALE` greater
than `OK`. A lower-severity result cannot overwrite an `ERROR` in the same
evaluation. Recovery requires a valid configuration and clock followed by a
newly received conforming triple; rejected data never performs the refresh.

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
| Any required stream exceeds either freshness upper limit with non-negative deltas | That stream and source readiness are `STALE` with `acquisition_timeout` or `arrival_timeout`; dependent RGB-D output is suppressed until a fresh valid triple arrives. |
| Missing or invalid hardware timing/evidence, unsupported encoding/unit/distortion, invalid calibration/dimensions, frame mismatch, unregistered depth, non-monotonic or future stamp, negative arrival silence, incompatible time domain, or RGB/depth skew above tolerance | Affected check and source readiness are `ERROR`; the invalid sample or triple is rejected without refreshing latest-valid state. |
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
   hardware timing field in turn and test missing, extra, reordered, and
   duplicate roster entries; every case must be `ERROR`, source-readiness false,
   and roster cases must report `roster_mismatch`. Reject any deployment field,
   mount, environment variable, or command-line option that tries to supply or
   extend the trust-manifest path, hash, version, key, or identity. For hardware,
   separately replace the image-pinned manifest with missing, writable,
   over-mounted, malformed, wrong-version, and wrong-hash variants and require
   `trust_store_invalid`. Also test a syntactically bogus reference, unresolved
   digest, byte/hash mismatch, malformed or unknown-field evidence schema,
   payload-hash or approval-signature mismatch, `approved_by`/key disagreement,
   unknown, not-yet-valid, or revoked approval keys, non-approved status, trust
   manifest version/hash mismatch, target mismatch, and approved/configured
   timing mismatch. Require the corresponding evidence reason and fail-closed
   source readiness for each case.
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
   require `ERROR`, rejection, and no freshness reset. Separately force
   `acquisition_age_ns < 0` and `arrival_silence_ns < 0`; require respectively
   `future_acquisition_stamp` and `steady_clock_regression`, verify no
   latest-valid refresh, and verify `ERROR` wins even when another stream is
   `STALE`.
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
