# CUASC vision pipeline review and reuse plan

Last updated: 2026-11-01. Paths below are relative to the supplied `CUASC_2026-main/`
snapshot. Line numbers refer to that snapshot and may shift after edits.
Review type: static source inspection plus one extracted-function geometry check.
No model, ROS graph, camera, Jetson or flight was executed.

## Execution path and reusable ideas

`src/vision_pipeline/launch/vision_demo.launch.py` starts:
`image_grabber` -> `yolo_node` -> `mission_logger`, plus robot_state_publisher.
The active logger does not consume TF extrinsics; it separately reads mount parameters.

| Source under src/vision_pipeline/ | What it supplies | Reuse decision |
| --- | --- | --- |
| vision_pipeline/image_grabber.py | Argus/GStreamer capture, rectification, ROS images/CameraInfo and monitor stream | Reuse acquisition structure; correct timing/domain contract |
| vision_pipeline/compressed_grabber.py | Bounded appsink, low-bandwidth image variants | Reuse queue/preview ideas; fix resized-image calibration |
| vision_pipeline/yolo_node.py | TensorRT/Ultralytics inference over overlapping tiles, NMS, Detection2DArray with input stamp | Reuse detector adapter and coordinate-offset ideas; benchmark alternatives |
| vision_pipeline/mission_logger.py | Image/pose history, quaternion SLERP, raycasting, dual nearest/interpolated logs and replay images | Retain recording/replay concept; extract and replace geometry/timing logic |
| vision_pipeline/data_logger_node.py | Standalone background dataset capture | Useful collection pattern; latest-pose snapshots are not synchronized truth |
| vision_pipeline/target_clustering.py | DBSCAN, cluster summaries and grouped images | Baseline comparison only; fuse original ENU observations with instance IDs |
| vision_pipeline/offline_photogrammetry.py | Offline image/log matching and raycast analysis | Reuse replay workflow concept; remove hardcoded time/paths and duplicate geometry |
| vision_pipeline/export_bin_to_csv.py | DataFlash GPS/ATT/POS export | Preserve raw logs; export independent sample times and quality |
| vision_pipeline/visualize_clusters.py | Detection plotting, per-image scatter/confidence | Diagnostic only; add reference-target errors and per-instance association |
| vision_pipeline/target_cv.py | HSV red target centroid and enable service for package-drop centering | Separate task-centering utility, not aerial multi-buoy mapping |
| config/arducam_info.yaml, config/kalibr.yaml | 3840x2160 calibration and converted intrinsics | Historical starting point; recalibrate actual lens/focus/mode |
| archive/target_localizer.py | Explicit optical/body/world transform structure and observation buffers | Conceptual reference, not a drop-in implementation |
| archive/simple_raycaster.py, target_geolocator.py, older loggers | Earlier planar/heading-based or alternate projection versions | Historical only; avoid multiple authoritative geometry implementations |
| setup.py, package.xml, launch/, vision.sh and local scripts | Packaging/launch conventions | Replace environment-specific scripts with declared target runtime |

The archives' descriptions, names and comments do not establish correctness. Existing
`main.py` is not the active mission pipeline entry point. Adjacent CUASC flight/control
packages exist, but this review does not propose importing the whole old architecture.

## Confirmed source issues and their implications

| Priority | Evidence | Finding | Required treatment |
| --- | --- | --- | --- |
| P0 | mission_logger.py:540-589 | Optical ray is mapped to FRD-like axes then passed through an attitude interpreted as ROS FLU-to-ENU. World NED/ENU round trips do not supply the missing body conversion | Replace with explicitly named R_EB R_BC chain and synthetic frame tests |
| P0 | image_grabber.py:206-233; compressed_grabber._on_timer | Stamp is obtained after camera.read and remap | Measure exposure-to-stamp offset/jitter; retain sensor timestamp where possible |
| P0 | mission_logger.py:463-505 | Nearest-pose mismatch over 200 ms returns latest pose; unbracketed/large-gap interpolation also returns latest | Reject or explicitly degrade stale/extrapolated measurements |
| P0 | compressed_grabber._on_timer and _setup_rectification_maps | Default primary image is 960x540 while CameraInfo retains 3840x2160 K/P and dimensions | Publish a matching image-specific calibration or keep calibrated full-resolution domain |
| P0 | config/vision_params.yaml; yolo_node.py:28; models/ | Defaults request yolo26n_v2.1.engine but supplied model is yolo26n_v1.0.engine | Resolve artifact/config mismatch; recover portable weights and training provenance |
| P1 | image_grabber.py:150-179 and camera_info publishing | K/P are replaced for rectified pixels but original D remains, and rectified stream is named image_raw | Make raw/rectified contracts explicit; prevent double undistortion |
| P1 | mission_logger.py:563-587 and offline config | Water plane/local z and GPS home are assumed compatible; no RTK status, datum or origin continuity check | Fixed ENU datum, water elevation, reset policy, health and antenna reference |
| P1 | config/vision_params.yaml, offline_flight_config.yaml, urdf/hexacopter.urdf | Three different mount values/definitions; active logger ignores URDF | One measured extrinsic authority and derived representations |
| P1 | image_grabber.py:111,228 and URDF | Images are stamped camera_link but URDF child is camera_optical_frame; supplied pitch-only URDF is not the stated downward optical-to-FLU mount | Reconcile frame names and calibrated transform, test centre ray |
| P1 | mission_logger.py:444-460 | Images may match within 250 ms although detector preserves original input stamp | Use frame identity/exact match; reject wrong-image substitution |
| P1 | mission_logger.py:370-424 | Previously saved central observations suppress later nearby hits rather than refine an instance | Preserve observation ledger and perform explicit association/fusion |
| P1 | archive/target_localizer.py:185-217 | Observation state keyed by class_id | Multiple same-class buoys must receive different instance IDs |
| P1 | target_clustering.py:56-110 | DBSCAN eps=3 m/min_samples=3 and arithmetic lat/lon means, without time/quality/motion gates | Compare against ENU, uncertainty-aware association; tune from real separation/errors |
| P1 | mission_logger.py:127-131,259-307 | Up to 100 full 4K BGR images plus synchronous JPEG writes in callbacks | Bound memory and decouple logging; measure full-pipeline latency |
| P2 | setup.py/package.xml and shell launchers | Runtime dependencies incomplete; scripts assume Humble, home paths, a separate venv and sudo daemon reset | Reproducible target dependencies/container; host driver management stays outside apps |
| P2 | target_cv.py | Detection timestamp is current callback time; combined red mask can join distinct red regions; sentinel may collide with a valid normalized corner | Preserve frame times and use typed validity/instances if reused |

The old 1 m deduplication threshold is not a proven buoy-separation threshold. Its
implementation only appends saved coordinates for central/prime detections, so behavior
differs across the image. Multiple detections in one frame share one annotated output
filename; these are not independently identified target chips despite the logger comments.

## Reproduced frame issue

The actual `_raycast_to_gps` method was extracted via Python AST and executed with
lightweight data objects, NumPy and SciPy, without ROS. Inputs: fx=fy=1000, cx=cy=0,
principal pixel (0,0), body position (0,0,5), identity quaternion [0,0,0,1], zero mount,
horizontal plane z=0. Under the standard ROS contract, identity means level with forward
east. The code's centre ray remains ENU +Z, so its intersection scale is negative and
the function returns None. A downward optical-to-FLU transform produces ENU -Z and
a valid vertical intersection instead.

This is a deterministic counterexample under that input contract. It does not prove
which quaternion/frame/configuration the physical historical flights actually supplied.
Verify that separately from original telemetry and hardware before interpreting past logs.

## Offline analysis pitfalls

- `offline_photogrammetry.parse_image_time` hardcodes UTC-4 rather than an unambiguous
  stored timestamp. Its filename convention differs from current img_sec_nanosec output.
- Offline roll/pitch/yaw are interpolated independently. Yaw wrap can produce an
  incorrect orientation; quaternion SLERP and explicit time validity are preferable.
- The first telemetry altitude is subtracted as home altitude. It is not a measurement
  of water height or necessarily FCU home.
- `export_bin_to_csv` attaches latest ATT values to POS rows without preserving separate
  sample times; GPS time alignment starts from one GPS sample. Its fixed leap-second
  constant and clock mapping must be versioned/verified, not silently assumed forever.
- `visualize_clusters.py` groups scatter by Image_Name. Different objects in one image
  can be spatially separated, so that spread does not by itself measure location error.
- Old source comments such as 'singularity-free', 'bulletproof' and 'thread-safe' are
  descriptions, not validation evidence.

## Available evidence and missing assets

Supplied vision assets include three DataFlash logs and CSV exports:
00000029 (4,937 rows), 00000030 (1,525), 00000031 (3,346).
CSV fields include timestamps, lat/lon, altitude and Euler attitude. They lack the complete
new calibration/timing/RTK quality contract. Raw logs may support richer re-extraction.
Do not infer matched imagery, object truth or an accuracy estimate from telemetry alone.

The ZIP contains one engine artifact; no portable training weights, annotated water-object
corpus or verified geolocation ground-truth dataset was identified in this package.
No matching full image sessions are supplied for a numerical historical accuracy study.

At 3840x2160, 100 BGR uint8 frames occupy 2,488,320,000 bytes, approximately 2.32 GiB.
With 1280-pixel tiles and 20% overlap, the configured 4K frame produces eight inference
calls. These are static calculations, not observed RAM use or inference speed.

## Migration order

Keep the old package as a reference baseline. Port small acquisition/detector interfaces;
first build shared pure geometry and replay, then clock/calibration adapters, then
instance fusion and map export. Avoid copying the monolithic logger as the production
geolocator. Work items and acceptance criteria are in [TASKS.md](../drone/TASKS.md).

