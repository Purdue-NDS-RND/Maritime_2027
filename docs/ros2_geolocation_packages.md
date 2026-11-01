# ROS 2 packages for camera-to-water geolocation

Researched: 2026-11-01. Scope: fixed monocular Arducam IMX519, YOLO26n detections,
IMU/flight-estimator attitude and RTK position, with ENU processing and WGS84 export.
This is a source-backed recommendation and evaluation plan, not an installed stack.

For live uncertainty and cross-pass identity targets added by the forwarded research
brief, read [uncertainty and tracking](uncertainty_tracking.md). Its voxel/mesh-package
discussion does not invalidate the IPM candidate: IPM is specifically a plane projector.

## Recommendation

Evaluate ROS Sports `ipm_library` first for pixel-to-water-plane projection. Pair it
with tf2 for timestamped camera poses and a tested geodetic conversion library.
Keep a thin Maritime adapter for calibrated image coordinates, timing/fix checks,
water-height assumptions, uncertainty, instance fusion and map export.

If IPM's dependencies or image contract are awkward on the selected Jetson stack, use
`image_geometry` + tf2 + a small, tested ray-plane intersection function. The latter is
a deliberately narrow fallback, not a reason to rebuild the old monolithic logger.
Existing CUASC code already imported image_geometry; the main missed reuse opportunity
was integrating camera models, TF/history and geodesy into a consistent contract.

The relevant problem is inverse perspective mapping: intersect image rays with an assumed
surface. Occupancy-grid/mesh ray tracing solves a different problem and needs a 3D map.
Neither approach obtains unknown depth from monocular pixels alone.

## Package comparison

| Candidate | Provides | Fit and decision |
| --- | --- | --- |
| [ros-sports/ipm](https://github.com/ros-sports/ipm), especially ipm_library | Vectorized pixels -> arbitrary plane; CameraInfo, measurement time and TF frames | Closest reusable projection component; evaluate first |
| ipm_service / ipm_image_node in the same repository | ROS service interface or image/mask -> projected point cloud | Optional interfaces; projecting a small detection-point batch needs neither a full cloud nor a new service |
| [image_geometry](https://index.ros.org/p/image_geometry/) | ROS CameraInfo camera model, rectification and pixel-ray geometry | Standard alternative building block; direction alone is not a geographic hit |
| [tf2 / tf2_ros / tf2_geometry_msgs](https://github.com/ros2/geometry2) | Frame tree, buffered transforms and geometry transformations | Use for camera-to-ENU transforms at image time |
| [image_proc and camera_calibration](https://github.com/ros-perception/image_pipeline) | Image rectification and camera-calibration tooling | Reuse where compatible with Arducam driver/capture; mount calibration remains separate |
| [message_filters](https://github.com/ros2/message_filters) | Message caches and exact/approximate timestamp pairing | Useful for related streams; pairing is not exposure synchronization or pose interpolation |
| [GeographicLib](https://geographiclib.sourceforge.io/html/CartConvert.1.html) | WGS84 geodetic/ECEF/local Cartesian conversion | Use for ENU/geodetic boundary; not a ROS-only dependency |
| [robot_localization](https://github.com/cra-ros-pkg/robot_localization), including navsat_transform_node | State-estimation tools and GPS-to-world odometry | Conditional: useful if we own sensor fusion; not a camera raycaster |
| [mgonzs13/yolo_ros](https://github.com/mgonzs13/yolo_ros) | ROS 2 detection/tracking integration, currently listing YOLO26 | Optional detector wrapper; compare Jetson deployment with a thin Ultralytics/TensorRT adapter |
| [OctoMap castRay](https://octomap.github.io/octomap/doc/classoctomap_1_1OcTree.html) | Ray queries through an occupied/free 3D voxel map | Not needed for the initial flat-water assumption |
| [GISNav](https://www.gisnav.org/introduction) | Camera-to-geographic-map matching to localize the drone | Adjacent problem; not our known-pose water-object projection |
| [FilterPy](https://filterpy.readthedocs.io/en/latest/kalman/KalmanFilter.html) | Reusable linear Kalman filter, per-update R and process-noise helpers | Candidate for projected-ENU tracking; not a ROS node or a substitute for calibrated uncertainty |
| [Stone Soup](https://stonesoup.readthedocs.io/en/latest/auto_tutorials/06_DataAssociation-MultiTargetTutorial.html) | Tracking models, association hypotheses and evaluation examples | Candidate offline comparison framework; not automatically an onboard dependency |
| [SciPy linear_sum_assignment](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html) | Minimum-cost assignment solver | Candidate for gated matching with explicit missed/clutter alternatives |

Package descriptions above describe upstream functionality. Fit/selection is our engineering
judgment. No package currently establishes Maritime's physical accuracy or competition readiness.

## IPM: verified API and integration contract

The inspected API exposes `IPM(tf_buffer, camera_info, distortion=False)`,
`map_point` and vectorized `map_points`. It takes a plane, image pixels and measurement
timestamp, transforms the plane into the optical frame, intersects the rays, then transforms
results to the requested output frame. Explicitly pass both frame names: defaults use the
camera frame, which would not be the ENU map we want.

For water at local ENU z = h, shape_msgs/Plane uses coefficients `[0,0,1,-h]`.
Its convention is `a*x+b*y+c*z+d=0`; this differs in sign from the right-hand-side d
notation used in [our mathematical derivation](geolocation.md).

Illustrative adapter call, not implemented application code:

```python
import numpy as np
from ipm_library.ipm import IPM
from shape_msgs.msg import Plane

mapper = IPM(tf_buffer, effective_camera_info, distortion=False)
water = Plane(coef=[0.0, 0.0, 1.0, -water_height_enu_m])
header, points_enu = mapper.map_points(
    water,
    np.asarray(selected_pixels_uv, dtype=np.float64),
    original_image_stamp,
    plane_frame_id="survey_enu",
    output_frame_id="survey_enu",
)
```

Use a batch of selected buoy pixels, not all image pixels. Preserve the association from
each input point to its detection. Handle empty batches before calling the library.

### Calibration behavior that needs an adapter

Source inspection of `ipm_library/utils.py` found that its pixel function reads CameraInfo.K,
uses OpenCV undistortPoints, and applies binning. It does not automatically use CameraInfo.P
as a rectified intrinsic matrix or dispatch by every distortion-model name.

- For raw pixels in our standard calibrated pinhole/plumb_bob model, supply original K/D
  and enable distortion processing.
- For rectified pixels, supply an effective CameraInfo whose K matches those pixels,
  commonly the rectified P's left 3x3 block for this monocular setup; disable distortion.
- Make ROI, binning, crop/resize and optical-frame definitions consistent. Prefer a
  normalized effective image contract, not mixing raw metadata with rectified pixels.
- Do not undistort twice or pass monitor-resolution detections with full-resolution K.
  Fisheye/nonstandard models need an explicitly supported path.
- The implementation converts pixel coordinates to float32 inside OpenCV. Quantify any
  resulting contribution rather than assuming every internal operation is float64.

By comparison, image_geometry.projectPixelTo3dRay expects rectified pixels and documents
a ray with z=1 in the inspected ROS 2 header. Do not assume it is unit length when using
range or angle thresholds. Use the pinned version's API; Python method naming may differ
across package releases.

### Time and validity behavior

IPM requests TF at the supplied measurement time. The inspected tf2 cache interpolates
translation and uses quaternion SLERP. This can replace custom interpolation arithmetic,
but the caller must supply valid, clock-aligned transforms and enforce acceptable sample
gaps, freshness, fix quality and origin continuity. TF interpolation alone does not impose
Maritime's telemetry-gap policy, and it does not estimate capture latency.

The inspected IPM kernel masks intersections behind the camera with NaNs. Parallel or
poorly conditioned geometry still needs application-level rejection: do not equate
'a function returned an array' with a usable location. Require finite outputs, validated
intrinsics/quaternions, usable view angle/range and recorded quality. The library returns
points, not a complete position covariance, bias bound, buoy-height model or map tracker.

## TF and pose ownership

Proposed minimal TF chain: survey_enu -> drone_base_link -> arducam_optical_frame.

- Publish drone_base_link pose dynamically from one authoritative, timestamped vehicle
  state estimate, adapted into the fixed ENU origin.
- Publish the measured camera mount as a static transform. Correct the antenna/body
  reference exactly once. Never also apply mount rotations manually after TF did so.
- Use original image times after clock-domain conversion. Keep TF history long enough
  for measured detector latency; handle missing transforms without a 'latest' fallback.
- If an FCU already fuses RTK and IMU, begin by consuming its validated estimate. Adding
  robot_localization is not inherently an improvement, and fusing correlated outputs
  as independent measurements can create misleading confidence.

IMU alone does not mean a complete earth-referenced attitude is available. Confirm
whether the message contains a valid fused orientation and how true/geographic yaw is
obtained; a single-antenna RTK position is not itself a heading measurement.
Retain full altitude/water-datum reasoning in [geolocation.md](geolocation.md).

navsat_transform_node explicitly expects robot odometry, an IMU/heading estimate and
NavSatFix, and produces world-frame odometry. Its inspected documentation expects yaw
zero toward east. It does not perform object projection, recover missing yaw, or resolve
our water-height datum automatically. Do not enable zero-altitude behavior for a drone
geolocation pipeline that needs camera height.

## YOLO26n and reuse boundaries

The user's chosen baseline is YOLO26n. Official Ultralytics documentation lists the
nano detection weights and export support; pin the actual package, trained weights,
class map, input geometry and export output layout in the eventual runtime.

As retrieved, yolo_ros main is a C++/ONNX Runtime pipeline and lists YOLO26 compatibility.
Its README provides aarch64 CPU use, but says its prebuilt GPU runtime bundles are x64;
aarch64 GPU needs an appropriate source build. This is not evidence that an Orin Nano
GPU will work with its standard desktop install. Compare real startup, GPU-provider use,
precision/latency and dependencies before choosing it. A small ROS publisher around the
already-working Ultralytics/TensorRT path may be less work on this hardware.

Do not reuse old Python-wrapper instructions or assume a TensorRT .engine is an ONNX
input. Check source-image timestamps, image-coordinate restoration, output message type
and stable per-image identity in either adapter. Keep detector implementation independent
of the chosen projection library.

## What Maritime still owns

| Reuse from libraries | Maritime integration and validation |
| --- | --- |
| Pixel model and plane intersections | Correct selected point on a buoy, reflection/height bias |
| TF storage, interpolation and transforms | Exposure time/clock mapping, frame/datum/reset contract and telemetry quality |
| Geodetic conversion | Fixed surveyed origin, water elevation, RTK base and antenna reference |
| ROS detection interfaces | Training data, correct YOLO26n artifact, calibration-aware pixels and actual Jetson performance |
| Generic message timing utilities | Measured maximum gaps and rejection/degradation policy |
| Optional state estimation | Appropriate source selection and avoidance of correlated double fusion |
| Standard messages | Object-instance association, uncertainty, freshness, operator review and JSON export |

## Source verification and compatibility

Inspected on 2026-11-01:

- IPM rolling commit `8003178ba83aa102e7fb9740c8d1403a1d6cdebf`: API, utilities,
  package manifest, upstream tests and Humble/Jazzy/Rolling workflow files.
- IPM humble commit `29439254c6c1eaabfaf1e8a42345594ffd55f3b5`: API source matched
  the inspected rolling API blob. This does not establish equality of all dependencies.
- Upstream IPM docs target Humble onward and document a source build. A Jazzy CI
  workflow exists; neither fact proves this exact Jetson build or current CI success.
  No ROS binary-package availability is assumed.
- IPM manifest at that revision reports version 0.0.0 and Apache-2.0 licensing.
  Pin a compatible commit after evaluation rather than inferring maturity from a version.
- image_geometry Humble header blob `fdbecd7d582506c17dbca4a6149d670b1797a796`;
  tf2 Jazzy cache blob `7b3e66e86515327cc9049938e14fbb43089ebd68`.
- robot_localization Jazzy commit `3efa714fb9c1ff40966327b7bed7053b2570be4d`;
  yolo_ros main commit `7ee20a9f5ec8d8223715f0240cabb9287746238e`.
- ROS website pages were partly blocked during retrieval; API/source behavior above was
  checked directly against upstream GitHub files rather than guessed from ROS 1 examples.

The extracted IPM NumPy line/plane kernel passed six local analytic checks: intersections,
downward-camera ENU mapping, 90-degree heading, nonzero water elevation, behind-camera
invalidity and parallel-ray nonfinite behavior. This was not a ROS/IPM integration test:
rclpy and OpenCV are absent here. No upstream full test suite, lens-distortion path,
TF runtime, package build, Jetson inference, camera or physical accuracy trial ran.

## First implementation experiment

1. Confirm drone ROS/JetPack choice and authoritative pose/heading source.
2. Evaluate the appropriate pinned IPM revision in a disposable ROS workspace/container;
   start with normal tf2, not an additional optimized TF-buffer dependency.
3. Publish synthetic dynamic drone poses and measured/example static mount. Project known
   centre/edge pixels at multiple attitudes and water heights.
4. Check raw-vs-rectified equivalence, binning/resize/ROI behavior, stale/missing TF,
   mismatched clock domains, near-horizon rays and all NaN/Inf handling.
5. Compare IPM with an independent analytic reference and manually annotated recorded
   targets. Define numeric tolerances from the error budget before accepting results.
6. Add detector output through a thin adapter, then ENU instance fusion and JSON export.

If IPM meets these checks, use it behind our adapter. Otherwise use image_geometry/tf2
with the same acceptance suite and record the specific mismatch. No package dependency
or runtime code is introduced by this documentation update.

## Primary references

- [IPM overview](https://github.com/ros-sports/ipm)
- [IPM tutorial and API use](https://ipm-docs.readthedocs.io/en/latest/tutorial.html)
- [IPM source installation](https://ipm-docs.readthedocs.io/en/latest/installation.html)
- [Pinned IPM API](https://github.com/ros-sports/ipm/blob/8003178ba83aa102e7fb9740c8d1403a1d6cdebf/ipm_library/ipm_library/ipm.py)
- [Pinned IPM geometry utilities](https://github.com/ros-sports/ipm/blob/8003178ba83aa102e7fb9740c8d1403a1d6cdebf/ipm_library/ipm_library/utils.py)
- [Pinned Jazzy workflow](https://github.com/ros-sports/ipm/blob/8003178ba83aa102e7fb9740c8d1403a1d6cdebf/.github/workflows/build_and_test_jazzy.yaml)
- [image_geometry ROS 2 header](https://github.com/ros-perception/vision_opencv/blob/humble/image_geometry/include/image_geometry/pinhole_camera_model.h)
- [tf2 interpolation source](https://github.com/ros2/geometry2/blob/jazzy/tf2/src/cache.cpp)
- [message_filters ROS 2 source](https://github.com/ros2/message_filters/blob/jazzy/src/message_filters/__init__.py)
- [navsat_transform_node documentation at inspected revision](https://github.com/cra-ros-pkg/robot_localization/blob/3efa714fb9c1ff40966327b7bed7053b2570be4d/doc/navsat_transform_node.rst)
- [YOLO26 official documentation](https://docs.ultralytics.com/models/yolo26/)
- [yolo_ros inspected README](https://github.com/mgonzs13/yolo_ros/blob/7ee20a9f5ec8d8223715f0240cabb9287746238e/README.md)
- [GeographicLib conversion](https://geographiclib.sourceforge.io/html/CartConvert.1.html)


