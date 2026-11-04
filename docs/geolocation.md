# ENU geolocation and measurement error

Last updated: 2026-11-04. This is the proposed mathematical and validation contract.
Physical transforms, numerical quality gates and accuracy requirements remain to be measured.

## Implementation reuse

The mathematics below is the reference contract, not a requirement to hand-code every
operation. [Package research](ros2_geolocation_packages.md) recommends evaluating
ipm_library for pixel-to-plane projection, tf2 for timestamped rigid transforms and
interpolation, and tested WGS84 geodesy at export. Keep application validity, uncertainty
and object-association checks in a thin adapter. Note that shape_msgs/Plane uses
ax+by+cz+d=0, so our horizontal water plane z=h is encoded as [0,0,1,-h].

## Frames and notation

| Symbol/frame | Meaning |
| --- | --- |
| E / survey_enu | Fixed local East, North, Up, meters |
| B / base_link | Drone body: forward, left, up (FLU), unless explicitly adapted |
| C / camera_optical_frame | Image right, image down, lens forward |
| A | GNSS antenna phase centre |
| R_EB | Rotation taking a B-expressed vector into E |
| R_BC, t_BC | Optical-to-body rotation; optical centre position expressed in B |
| p_EB | Position of the chosen body reference expressed in E |
| t_BA | GNSS antenna position expressed in B |

Use SI units internally, normalized quaternions with explicitly named order `[x,y,z,w]`,
and named transform direction. ENU yaw zero is east and positive turns toward north;
navigation heading usually uses north zero and clockwise. Never substitute one silently.

Raw FCU FRD (forward/right/down) and NED (north/east/down) data require both body and
world-frame conversions. MAVROS already adapts frames; verify the exact topic contract
before converting again. Avoid ambiguously named variables such as `body_ned`.

Choose a fixed geographic origin `(latitude0, longitude0, ellipsoid_height0)`
and an immutable `origin_id` for the map. A boat launch point, FCU home and EKF origin
are not automatically the same position or vertical zero. Detect FCU reset/relocalization.
Either transform measurements into the same fixed survey frame or begin a new explicit
origin/epoch. Do not anchor existing maps to the boat's changing location.

## Pixel to ENU ray

Use one of two explicit image contracts:

1. Raw distorted pixels: apply inverse distortion using the original K and D, obtaining
   normalized undistorted coordinates, then ray `r_C = normalize([x_n, y_n, 1])`.
2. Rectified pixels: use the actual rectified K' for that image and
   `r_C = normalize(inv(K') [u, v, 1])`. Do not undistort again.

Resize/crop/letterbox/tile transforms must be inverted before using calibrated pixels,
or the effective intrinsics must be transformed consistently. Monitor images do not inherit
full-resolution intrinsics. Record focus, sensor mode, resolution, ROI and image domain.

At exposure time t:

```text
r_E(t) = R_EB(t) R_BC r_C

p_EC(t) = p_EB(t) + R_EB(t) t_BC

If position is antenna position p_EA rather than body position:
p_EC(t) = p_EA(t) + R_EB(t) (t_BC - t_BA)
```

Confirm whether the flight estimator already compensates the GNSS lever arm; do not
apply it twice. Static camera mounting still moves and rotates with the aircraft.
Store one authoritative camera extrinsic calibration and derive any URDF/config from it.

For an ideal downward camera whose image top points along body forward,
one example optical-to-FLU rotation is:

```text
R_BC = [[ 0, -1,  0],
        [-1,  0,  0],
        [ 0,  0, -1]]
```

This is a proper rotation (determinant +1), and its centre ray points body down.
It is an example for a specified mounting, not an assumed calibration for the actual rig.

## Water-plane intersection

For plane `n_E dot X_E = d` and unit ray `r_E`:

```text
lambda = (d - n_E dot p_EC) / (n_E dot r_E)
X_E = p_EC + lambda r_E
```

The first local water model is a horizontal plane: `n_E=[0,0,1]`, `d=z_water`.
Thus `lambda = (z_water - p_EC.z) / r_E.z`.

Reject nonfinite inputs, invalid quaternions, unresolved origins/calibration, rays facing
away, near-parallel geometry and physically unreasonable intersection distances.
Use practical angle/uncertainty limits derived from acceptance, not just a 1e-6 divide guard.
Separate rejected, degraded and usable observations, with explicit reasons.

Waves, buoy heave and water-level variation perturb this plane. A horizontal approximation
is acceptable only if measured residual error is within the budget; do not assume every
frame needs a complex dynamic surface model.

## Ordinary GNSS: current requirement and height/heading contract

The user removed RTK on 2026-11-04. Ordinary GNSS is the deployment baseline;
historical RTK discussion below is not a requirement. Receiver, antenna, covariance
semantics and FCU interfaces have not been verified.

Camera + raw accelerometer/gyro data cannot yield absolute object GPS coordinates.
Require GNSS anchoring, earth-referenced attitude/heading and height above the modeled
water surface. A single antenna position is not a hover heading measurement;
course-over-ground need not equal body yaw. Prefer validated FCU fusion with an explicit
heading source and covariance, not open-loop integration or duplicate correlated fusion.

A numerical ENU origin may be selected without surveying, but record whether it is
surveyed, configured or an uncertain GNSS estimate. Subtracting a launch fix does not
remove global offset. Track shared position/heading/height error across objects/passes.
Rotate source covariance into the survey frame; distinguish receiver covariance,
estimator posterior, unknown covariance and empirical calibration. HDOP is dimensionless,
not a variance in metres squared.

For height, evaluate the authoritative FCU vertical estimate with measured
lens/deck/water offsets and barometric drift. GNSS ellipsoid altitude, AMSL and FCU
relative altitude are not interchangeable with height above water. A boat launch adds
freeboard and motion. Carry uncertainty; do not set water z=0 because home z=0.
An optional rangefinder must first pass over-water return-validity tests with tilt and
lever-arm compensation.

At near nadir, height error has little horizontal effect; off nadir it scales as
tan(theta). Low altitude cannot remove horizontal GNSS offset. A synthetic
sigma_GNSS=2 m per axis alone implies about a 4.90 m 95% Gaussian circle; this is not
a receiver specification or guaranteed bound. Measure this receiver. See the ordinary-GNSS
correlation model in [uncertainty and tracking](uncertainty_tracking.md).

## Historical RTK considerations (not required)

RTK can improve antenna positioning when corrections/fix quality are good. It does not
directly calibrate attitude, camera alignment, exposure time or object reference height.
Vertical uncertainty differs from horizontal uncertainty; a fixed solution can retain base
survey bias. Record fix state, correction age, uncertainty estimates and outages.

GNSS ellipsoidal altitude, orthometric/AMSL altitude, FCU relative altitude and height above
water are distinct. An FCU initialized on a boat deck has its local z-zero above the water.
Measure water elevation and lens/antenna/body offsets in the same reference. A downward
range sensor is an option to evaluate on water, not an assumed reliable source.
Do not treat the Google Earth view's camera altitude as water elevation.

## The visible buoy is not a water-plane point

An upright fender can protrude substantially above water. At an oblique viewing angle,
projecting a top/body-centre pixel onto water biases its horizontal location away from
the camera's vertical projection. Reflection, shape and occlusion shift a box centre too.
Near nadir reduces this effect; flying lower does not eliminate it.

Define desired output as a consistent horizontal object centre/footprint, with a chosen
reference height. Compare: box centre baseline, visible waterline/keypoint, mask/shape fit,
or an elevated-point height model. No universal bottom-centre-of-box rule is justified for
an overhead view. Store the reference method and uncertainty per observation.

## Timing and interpolation

The time required for a raycast is the exposure time, not detector completion.
Preserve frame ID and original capture timestamp through inference. Map sensor/FCU/host
clocks with measured offset and drift. If sensor timing is unavailable, measure host-stamp
delay and jitter and label the approximation. Exposure midpoint is useful for a frame;
rolling shutter can require a row-dependent correction if measured motion error warrants it.

Interpolate position between valid bracketing samples and attitude by quaternion SLERP.
Require bounded gaps; explicitly reject or flag extrapolation/stale data. Do not return the
latest pose on an interpolation failure. Buffer a bounded amount to obtain the after-sample.
Record both pose sample times, interpolation gap and timing uncertainty.

## Error sensitivity

The following are analytic illustrations, not measurements or guaranteed bounds.
H is camera height above the water, theta is ray angle from nadir, rho is horizontal
camera-to-target range, and small angular errors use radians.

| Source | Approximate horizontal sensitivity | Illustration |
| --- | --- | --- |
| Horizontal position | Direct translation | 0.05 m pose bias gives about 0.05 m location bias |
| Roll/pitch or mount tilt | Near nadir H times delta-angle; off-nadir approximately H sec(theta)^2 times delta-angle along viewing direction | 1 degree at H=5 m near nadir gives 0.087 m |
| Heading error | rho times delta-yaw | At rho=5 m, 1 degree gives about 0.087 m |
| Water/point-height error | abs(delta-height) tan(theta) | 0.20 m at 30 degrees gives 0.115 m |
| Translation timing | speed times abs(delta-time) | 2 m/s and 0.10 s gives 0.20 m |
| Attitude timing | Roughly H sec(theta)^2 times angular-rate times delta-time | Must use measured angular motion |
| Pixel choice | Near nadir H times delta-pixels / focal-length-pixels | Depends on actual rectification/focus |
| Lever-arm calibration | Translation error, rotated into ENU | Camera and antenna reference must match |
| Object drift/map age | Motion since observation | Measure, do not hide in averaging |
| Geographic conversion | Projection/datum/origin mismatch | Compare across course, not only at origin |

For state s containing pixels, pose, extrinsics, water elevation and time, use sensitivity
Jacobian J to estimate `Sigma_EN = J Sigma_s J^T`; Monte Carlo supports nonlinear/gated
cases. Include known correlations where practical. Common calibration/base/clock bias
does not disappear by averaging many frames. Track scatter is not absolute accuracy.
YOLO confidence is not a position covariance. Report unmodeled/systematic components
separately and calibrate confidence regions against held-out ground truth.

[Uncertainty and tracking](uncertainty_tracking.md) expands this into per-observation
Jacobians, shared bias/correlations, a linear-KF baseline, cross-pass association and
timestamped 95% ellipse reporting. It also reviews the forwarded research brief:
its angular range scaling is a useful first-order contribution, not a complete noise
model, and overhead bottom-centre projection is not accepted as a universal reference.

## Geodetic export and existing GCS compatibility

Use WGS84 geodetic -> ECEF -> local ENU for consistent position input; inverse ENU -> ECEF
-> geodetic at export. Use a tested implementation such as GeographicLib LocalCartesian
or equivalent. Ellipsoidal heights must be documented. Preserve full floating-point
precision internally; decimal places are not a measure of accuracy.

Existing `shared.geometry` intentionally follows an ArduPilot-compatible small-course
projection. It is not a full 3D WGS84 tangent frame. Do not silently replace it: compare
independent known points, bearings, scale and round trips, and retain simulator tests.
The two projections must be explicitly reconciled at the GCS map boundary.

## Validation ladder

1. Synthetic geometry: centre/east/north pixels, 90-degree heading rotations, roll/pitch,
   mount rotations, lever arms, rotated camera, wrong-way/horizon rays, invalid numbers.
2. Projection tests: raw-vs-rectified equivalence, resize/crop/letterbox inversion and
   independently verified WGS84 conversions over the course.
3. Bench/land grid: surveyed flat targets across the image at multiple heights/headings.
   Use manual pixel annotations first to isolate geometry from detector error.
4. Hover and motion: repeat targets with GNSS/estimator quality and timing logs; sweep speed/turns to
   identify clock, attitude and rolling-shutter sensitivity.
5. Water trials: surveyed buoy horizontal centres, reflections, heave, varying sun,
   off-nadir range and elapsed time. Measure reference uncertainty too.
6. Full held-out survey and boat integration: completeness, false/merged/split instances,
   freshness and clearance, with independent truth and no tuning on the final test.

Report mean East/North bias, median/p95/max horizontal error, accepted/rejected counts,
coverage, per-object recall, geometry/GNSS/lighting strata and uncertainty-region coverage.
Agree numeric pass thresholds using boat hull/turn/tracking and buoy-motion margins.

## Primary references

- [ROS REP-103 source: FLU, ENU, optical axes and yaw](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-0103.rst)
- [MAVROS overview: FCU/ROS frame conversion](https://index.ros.org/p/mavros/)
- [OpenCV calibration and inverse distortion](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)
- [GeographicLib local Cartesian conversion and ellipsoidal height](https://geographiclib.sourceforge.io/html/CartConvert.1.html)


