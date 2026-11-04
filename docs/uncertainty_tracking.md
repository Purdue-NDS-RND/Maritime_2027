# Uncertainty and persistent buoy tracking

Last updated: 2026-11-04. Status: reviewed design and evaluation plan, not implemented.
This extends the ENU geometry and library-reuse references after review of a
user-supplied Gemini research brief. Formulas were checked independently; package
capabilities were checked against primary documentation.

## New targets and unresolved operational scope

The forwarded brief adds real-time track reports, a dynamically calculated Gaussian
position-uncertainty ellipse, persistent identities across passes, and prediction of
object motion/uncertainty during observation gaps. Record these as development targets,
not achieved capabilities.

The earlier operating plan remains survey -> land drone -> GCS review -> approved boat
route. A real-time report while surveying is compatible with that plan. Continuous
airborne updates while the boat moves, automatic resurvey and automatic route changes
are not established by the brief; decide those with the flight/GCS/boat owners.

The camera remains a fixed Arducam IMX519 and the detector baseline remains YOLO26n.
Generic gimbal encoders and alternative YOLO versions in Gemini's text do not override
those decisions. Ordinary GNSS is the user's 2026-11-04 baseline, replacing RTK. It supplies
an antenna/reference position, not automatically the lens origin. A calibrated camera/antenna/body transform and a valid attitude/heading estimate
are still required.

## Assessment of the proposed stages

| Proposal | Assessment |
| --- | --- |
| Pixel ray intersected with known horizontal water plane | Correct under the calibrated-pixel, pose, timing and plane assumptions |
| Always select bottom-centre of a bounding box | Not justified for overhead views; evaluate water-centre/reference methods |
| Geometry-dependent anisotropic measurement covariance | Good direction, but position, water-height, timing and calibration terms are missing |
| CWNA constant-velocity transition and process covariance | Mathematically correct for the stated state ordering and noise model |
| EKF/UKF required for the projected-position tracker | Unnecessary for the linear model given; ordinary KF is the baseline |
| Mahalanobis gating and global assignment | Sensible baseline with explicit missed/new/ambiguous hypotheses |
| 99% squared gate 9.21 and 95% ellipse multiplier about 2.448 | Correct for two dimensions and calibrated Gaussian errors |
| Expand uncertainty over long revisits | Necessary; it does not guarantee identity or justify unbounded drift for moored buoys |
| Existing ROS 2 raycasting cannot be reused | Incomplete conclusion; IPM already implements the relevant arbitrary-plane projection |
| Lightweight C++ is required | Unsupported without profiling; library-backed Python core is a reasonable first experiment |

## 1. Projection reference and error propagation

For camera position c, ENU ray r and water elevation w, define

$$
\tau=\frac{w-c_z}{r_z},\qquad
\mathbf z=\mathbf c_{xy}+\tau\mathbf r_{xy}.
$$

Require the camera above the modeled surface, a forward intersection, finite values,
and usable view angle/range. Raw distorted pixels require inverse distortion; rectified
pixels require their effective intrinsics. See [geolocation](geolocation.md).

A box's image-bottom is an image direction, not necessarily a buoy's water-contact point.
Under an ideal downward view of a symmetric buoy, it selects an edge. At nadir, a
20-pixel shift with H=5 m and f=1000 pixels produces 0.10 m horizontal displacement.
Reflections can extend a box further. Compare centre, selected waterline/keypoint,
mask/shape fit and height-corrected reference on measured data.

Use a joint uncertainty vector containing pixel choice, camera position/orientation,
intrinsics, extrinsics, water elevation and capture-time error:

$$
R_{\mathrm{meas},k}\simeq J_k\Sigma_kJ_k^\top.
$$

A sum of separate terms is valid only when the corresponding input errors are independent.
Use the full pose covariance and relevant cross terms when available. Do not count camera
height twice as both a position error and an independent height input.

Useful analytic Jacobians, treating c, r and w as independent coordinates, are

$$
J_c=
\begin{bmatrix}1&0&-r_x/r_z\\0&1&-r_y/r_z\end{bmatrix},
\quad
J_w=\begin{bmatrix}r_x/r_z\\r_y/r_z\end{bmatrix},
$$

$$
J_r=
\begin{bmatrix}
\tau&0&-\tau r_x/r_z\\
0&\tau&-\tau r_y/r_z
\end{bmatrix}.
$$

Compose these with the camera model and a documented small-angle rotation convention.
Numerical differentiation of a validated projection adapter is another way to obtain
Jacobians without rebuilding all IPM internals.

### Interpreting the range scaling

In a vertical section, with H the height above water and theta the angle from nadir,

$$
\rho=H\tan\theta,\qquad L=H/\cos\theta,\qquad
\frac{\partial\rho}{\partial\theta}=H\sec^2\theta=\frac{L^2}{H}.
$$

Thus the first-order pitch-like angular contribution is

$$
\sigma_{\rho,\mathrm{angle}}\simeq \frac{L^2}{H}\sigma_\theta.
$$

Gemini's proportionality is reasonable for this component, but the angular standard
deviation and its units matter. It is not a universal model for every covariance term.
Water-height error contributes approximately abs(tan(theta))*sigma_H; yaw contributes
approximately rho*sigma_yaw in the transverse direction. At exact nadir the horizontal
ray direction is undefined, so do not construct the covariance by normalizing a zero
horizontal vector. A full Jacobian handles that case.

Near the horizon, linear/Gaussian propagation can be inaccurate or unbounded. Reject
ill-conditioned observations or validate an appropriate nonlinear uncertainty model
rather than relying on a very long ellipse.
Offline Monte Carlo or sigma-point propagation through the projection library can
measure skew and mean shift; this does not require choosing a UKF for the track itself.

## 2. Random error and shared bias are different

Repeated measurements can share persistent GNSS offset, clock offset, camera alignment error,
water-level bias or persistent pixel-reference bias. Adding each one's marginal variance
to R and then treating frames as independent can still underestimate final uncertainty.

For the simple model z_i = p + b + epsilon_i, where b is common to all observations,

$$
\operatorname{Var}(\bar z)=\sigma_b^2+\frac{\sigma_\epsilon^2}{N}.
$$

For 100 observations, sigma_b=0.10 m and sigma_epsilon=0.05 m, the true standard
deviation of this average is about 0.1001 m. A naive independent model using each
observation's total variance predicts about 0.0112 m. A tightly clustered track can
therefore have a substantially wrong absolute location.

Separate random covariance from known/common bias components in the output. Depending
on evidence, use a measured conservative floor, correlated block processing, or explicit
bias states/joint estimation. A bias floor is a practical approximation, not a substitute
for modeling dependencies when they materially affect decisions. Diverse views or
independent reference data can make some bias parameters observable.

One camera pose/water-plane error also correlates different buoy locations in the same
frame. Preserve observation/frame provenance rather than claiming their absolute
uncertainties are independent.

### Ordinary-GNSS anchoring and correlated drift

A proposed model is z_ik = p_i + b_k + epsilon_ik: target position, time-correlated
common navigation offset and independent residual error. Heading, height and mount
errors produce geometry-dependent correlations too; translation alone is incomplete.
Preserve source-frame/epoch IDs and component provenance across objects and updates.

For illustrative per-axis sigma_b=2 m, sigma_epsilon=0.1 m and 100 observations, the
mean's sigma is sqrt(4 + 0.01/100), approximately 2.000025 m. It is not
sqrt((4 + 0.01)/100), approximately 0.20025 m. These are synthetic calculations.
Measure drift and temporal residuals rather than assuming one bias for an entire day.

Keep conditional local track uncertainty separate from absolute anchoring uncertainty.
Only for an independent local/anchor split is P_absolute approximately P_local+P_anchor,
after frame transformation. Include cross terms when dependent; do not add a GNSS floor
to a posterior that already includes it and count it twice.

Compare correlation-aware batches plus a measured shared-error floor against a joint
anchor/bias model on replay. A floor is an approximation, not calibration or a guarantee.
Per-track floors alone do not encode cross-object correlations. Retain shared model ID,
epoch and sufficient components for downstream joint geometry. TF stores none of these.

If neither calibrated covariance nor a defensible conservative model exists, report
uncertainty unknown/unvalidated. Do not derive it from YOLO score or HDOP alone.
Scatter omits possible absolute bias. Name whether a reported ellipse includes modeled
GNSS/map anchoring error.

Repeated unknown buoy sightings alone cannot resolve absolute translation. Independent
measured references may help; a bias state or smoother alone cannot remove this ambiguity.
Boat-relative uncertainty also needs the boat's GPS error and any measured correlation;
nearby standalone receivers must not be assumed to cancel each other's errors.

## 3. Tracking baseline: linear KF with a tested motion model

For state x=[E,N,v_E,v_N] and projected measurement z=[E,N], the supplied constant-velocity
transition F is linear and the observation matrix is

$$
H=\begin{bmatrix}1&0&0&0\\0&1&0&0\end{bmatrix}.
$$

An ordinary KF supports time-varying R_k and Q_k. Nonlinear image projection before
this filter does not itself require an EKF/UKF after projection. The projected measurement
distribution is only approximately Gaussian; verify that approximation in the operating
envelope. Consider EKF/UKF if instead updating from raw pixels/bearings, introducing
nonlinear dynamics, or jointly estimating nonlinear pose/calibration states.

For continuous white acceleration with spectral density q,

$$
Q(\Delta t)=q
\begin{bmatrix}
(\Delta t^3/3)I_2&(\Delta t^2/2)I_2\\
(\Delta t^2/2)I_2&\Delta t I_2
\end{bmatrix}.
$$

This matches Gemini's expression and [E,N,v_E,v_N] ordering. The units of q are m^2/s^3.
Do not replace it with a discrete per-step random-acceleration covariance using the
same numeric noise parameter; the models and units differ.

[FilterPy](https://filterpy.readthedocs.io/en/latest/kalman/KalmanFilter.html) provides
a reusable linear KF and per-update measurement covariance. Its
Q_continuous_white_noise helper supports explicit state ordering; for this ordering the
candidate parameters are dim=2, block_size=2, order_by_dim=False. Evaluate and pin the
chosen library on the actual stack before adoption. Stone Soup is another candidate for
offline model/association comparisons; neither library becomes a runtime dependency here.

### Motion must match the actual buoy

A moored marker and a freely floating recovery case need not share one motion model.
Confirm attachment, excursion and measured movement; do not infer free drift from the
word buoy.

Compare a static/random-walk baseline against constant velocity. For moored markers,
a mean-reverting or damped model around an uncertain anchor may be more appropriate.
A sustained velocity extrapolated for minutes can put a tethered buoy outside its
physical excursion. A large covariance does not correct an implausible mean automatically.

Initialize velocity with suitable uncertainty, not a falsely precise zero. Use measured
motion to tune process noise, and include missed-detection, tentative, confirmed,
coasting, ambiguous and stale/deleted states.

## 4. Gating, assignment and cross-pass identity

At a common measurement timestamp, the independent-error baseline uses innovation
nu_ij=z_j-H*x_i and S_ij=H*P_i*H^T+R_j.

$$
d_{ij}^2=\nu_{ij}^\top S_{ij}^{-1}\nu_{ij}.
$$

A 99% two-dimensional gate uses chi-square quantile 9.21034. This is a model-based
coverage threshold for a correct association, not a 99% probability that an identity
is correct. Shared track/measurement errors can also invalidate the independence
formula for S unless modeled.

Global assignment is sensible after gating, but:

- Include unmatched-track and new/clutter-detection alternatives. Do not force every
  detection onto an existing buoy. SciPy's linear_sum_assignment solves the supplied
  assignment objective; the caller must construct these alternatives.
- With different S matrices, a Gaussian negative-log-likelihood cost includes both
  0.5*d^2 and 0.5*log(det(S)), plus appropriate detection/clutter terms. Distance alone
  can favor a highly uncertain track.
- Merge duplicate tile detections before a one-detection-per-object update batch.
- After minutes without observations, expanded gates can overlap several similar buoys.
  Use course order/relative arrangement, visual evidence where available, repeated
  observations and a defined ambiguity policy. Do not assert that covariance inflation
  preserves identity.
- Retain operator color/role labels separately and avoid transferring them silently to a
  potentially different physical instance after uncertain reassociation.

Start with gated assignment and explicit ambiguity. Escalate to multiple hypotheses or
JPDA only if tests show a material association problem; forcing a multimodal situation
into one small Gaussian ellipse would hide identity uncertainty.

## 5. Real-time reporting and 95% ellipses

A filter state is an estimate at a particular time. Distinguish the last observation,
state epoch and publish time. A current prediction from an old measurement must be
marked predicted/coasting, with age and propagated covariance. Handle delayed YOLO
measurements at their capture time, then repropagate; define a bounded replay/fixed-lag
or rejection policy for out-of-sequence updates.

For a symmetric positive semidefinite EN position covariance with eigenvalues
lambda_max >= lambda_min,

$$
a_{95}=\sqrt{\chi^2_{2,0.95}\lambda_{\max}},\qquad
b_{95}=\sqrt{\chi^2_{2,0.95}\lambda_{\min}},
\qquad \sqrt{\chi^2_{2,0.95}}=2.44774683.
$$

Gemini's multiplier and orientation expression are correct for the nondegenerate 2D case.
Use the major eigenvector to set orientation consistently; define radians counterclockwise
from East, modulo pi. Isotropic ellipses have no meaningful unique orientation. Sort
eigenvalues, verify covariance validity, and distinguish semi-axis lengths from diameters.
Negative eigenvalues beyond numerical roundoff indicate a problem to investigate.

This is a model-based 95% position-probability region, not a hard error bound or a claim
that the model covers all failure modes. Validate coverage on held-out surveyed targets.
Position covariance describes the filtered/predicted location; it is not the measurement
covariance R or the innovation covariance S. Association ambiguity, unknown bias and
false detections require separate quality fields.

Keep covariance/ellipse axes in ENU meters. Convert the geographic centre, or sampled
ellipse boundary points, through the established WGS84 transform. A local ENU origin
is not automatically a launch fix or GNSS reference location; horizontal and height datums must agree.
Do not mix meter-squared covariance with latitude/longitude degrees.

## 6. Additional ideas to evaluate

1. **Separate map-wide error from individual motion.** If several apparently stable buoys
   shift together between passes, test a common pose/origin/heading-bias explanation.
   Robust geometric registration with appropriately uncertain GNSS priors may help diagnose the cause. Repeated
   course layouts can make registration ambiguous; do not use the rough diagram as
   surveyed truth or conceal absolute GNSS bias.
2. **Choose revisits for information.** Request views of stale tracks or long ellipses,
   ideally with improved geometry or different viewing direction. Repeated identical
   views may mostly repeat the same bias. Survey requests remain flight-team ownership.
3. **Predict uncertainty at boat encounter time.** A narrow ellipse now may not suffice
   when the boat reaches that buoy later. Export state/age/model information so planning
   can use a time-appropriate location region plus hull, tracking and movement margins.
4. **Calibrate uncertainty from residuals.** Compare analytic geometry with empirical
   errors by image position, angle, brightness, blur and GNSS/estimator state. Learn or fit missing
   residual variance/bias terms from training/calibration sessions, and evaluate on
   held-out flights. Report both coverage and ellipse size, not just how tight it looks.
5. **Joint offline calibration and smoothing.** A factor graph can estimate some mount,
   timing or water-height biases together with buoy trajectories if reference data and
   view diversity make them observable. This is a later experiment, not a reason to
   start with a large new optimization stack.
6. **Separate absolute and boat-relative error.** If drone and boat have measured common position error and
   compatible datums, some of it may cancel in their relative geometry. Sharing an RTK
   base was a historical example; RTK is no longer planned. Nearby ordinary-GNSS
   receivers must not be presumed to have that correlation.
   For d=p_buoy-p_boat, the covariance is P_buoy+P_boat-C-C^T, where
   C=Cov(p_buoy,p_boat). Measure the shared component and time dependence; do not assume
   cancellation or reduce the absolute GPS ellipse without evidence. This can make
   navigation-clearance estimates more faithful than adding independent GPS margins.

These are engineering proposals, not established performance improvements.

## Validation and adoption sequence

- Confirm the target's motion constraints and live-report operational scope.
- Retain IPM/tf2/geodesy reuse; compare pixel reference choices before filter tuning.
- Validate full random covariance plus separately treated shared bias with recorded truth.
- Evaluate linear KF motion baselines and association using irregular times, long gaps,
  nearby same-class buoys, glare/false detections and common pose errors.
- Measure NIS=nu^T*S^-1*nu and held-out position error e^T*P_pos^-1*e. Each has a
  two-dimensional chi-square reference under its respective calibrated assumptions;
  the full four-state NEES would use four degrees of freedom. Association-selected
  residuals and correlated frames require care when interpreting these diagnostics.
- Measure coverage, ellipse area, bias, p95/max position error, ID switches, merge/split
  rates, latency, freshness and rejection rate. Tune noise on calibration sessions,
  then evaluate separate sessions rather than choosing q to make one plot look smooth.
  Account for reference-survey uncertainty when interpreting residuals and coverage.
- Only then choose numerical operating limits and add real-time report transport.
  Live data does not silently modify an already approved boat mission.

Independent local checks during this review covered the camera/ray/water Jacobians by
finite differences, angular sensitivity, CWNA covariance properties, the ellipse scale
and a synthetic 100,000-sample Gaussian coverage experiment (94.901% inside the nominal
95% ellipse). These verify analytic/code calculations, not real buoy accuracy, a working
ROS tracker or calibrated hardware uncertainty.

## Primary references

- [IPM projection library and service tutorial](https://ipm-docs.readthedocs.io/en/latest/tutorial.html)
- [Soccer IPM: related detections and object-size assumptions](https://ipm-docs.readthedocs.io/en/latest/soccer.html)
- [FilterPy linear KalmanFilter and per-update R](https://filterpy.readthedocs.io/en/latest/kalman/KalmanFilter.html)
- [FilterPy continuous/discrete noise helpers and state ordering](https://filterpy.readthedocs.io/en/latest/common/common.html)
- [Stone Soup constant-velocity transition models](https://stonesoup.readthedocs.io/en/latest/stonesoup.models.transition.html)
- [Stone Soup multi-target association tutorial](https://stonesoup.readthedocs.io/en/latest/auto_tutorials/06_DataAssociation-MultiTargetTutorial.html)
- [Stone Soup JPDA and mixture hypotheses](https://stonesoup.readthedocs.io/en/stable/auto_tutorials/08_JPDATutorial.html)
- [SciPy assignment solver](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html)
- [NIST chi-square quantiles](https://itl.nist.gov/div898/handbook/eda/section3/eda3674.htm)

