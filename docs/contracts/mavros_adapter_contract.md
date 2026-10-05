# Common MAVROS Adapter Contract

**Contract ID:** `maritime.mavros_adapter`

**Contract version:** `2.0.0`

**Status:** Normative for Simulation and Hardware Adapter implementations

This document freezes the MAVROS boundary presented to onboard autonomy and a
future GCS. It defines interface compatibility, not command authority or vessel
readiness policy. Both environment Adapters must produce this same boundary.

## Normative configuration source

The manifest in this section defines the normative values for contract version
`2.0.0`. The canonical simulation runtime configuration is
`Adapter/simulation/ros_ws/src/blueboat_sim_bringup/config/mavros.yaml`.
Launch consumes its loader and UAS settings; `configure_mavros` reads its plugin
groups and applies them through parameter services. Adapter diagnostics
independently checks the effective values against the contract. The runtime
configuration, diagnostic expectations, and contract tests must remain aligned
with this manifest and change together in the same review. Adapter environment
files may supply only the overrides defined below. Package-supplied
`apm_config.yaml` and `apm_pluginlists.yaml` are not authoritative project
configuration.

```yaml
contract_id: maritime.mavros_adapter
contract_version: 2.0.0

platform:
  ros_distribution: jazzy
  os_distribution: ubuntu_noble_24.04
  mavros_upstream_version: 2.15.1
  packages:
    ros-jazzy-mavros: 2.15.1-1noble.20260903.022619
    ros-jazzy-mavros-extras: 2.15.1-1noble.20260903.025450

mavlink:
  protocol: v2.0
  source_system_id: 255
  source_component_id: 191
  target_system_id: 1
  target_component_id: 1
  gcs_url: ""
  uas_url: /uas1

ros:
  public_namespace: /mavros
  node_fqn: /mavros
  use_sim_time: false

system:
  heartbeat_rate_hz: 1.0
  heartbeat_type: ONBOARD_CONTROLLER
  connection_timeout_s: 10.0
  diagnostics_disabled: false

time:
  time_reference_source: fcu
  timesync_mode: MAVLINK
  timesync_alpha_initial: 0.05
  timesync_beta_initial: 0.05
  timesync_alpha_final: 0.003
  timesync_beta_final: 0.003
  convergence_window: 500
  timesync_rate_hz: 10.0
  system_time_rate_hz: 1.0

frames:
  map_frame_id: map
  odom_frame_id: odom
  base_link_frame_id: base_link
  body_frd: base_link_frd
  local_position:
    frame_id: map
    tf_send: false
    tf_frame_id: map
    tf_child_frame_id: base_link
  global_position:
    frame_id: map
    child_frame_id: base_link
    tf_send: false
    tf_frame_id: map
    tf_global_frame_id: earth
    tf_child_frame_id: base_link
  imu:
    frame_id: base_link

plugins:
  plugin_allowlist:
    - adsb
    - cam_imu_sync
    - camera
    - cellular_status
    - command
    - companion_process_status
    - distance_sensor
    - esc_status
    - esc_telemetry
    - fake_gps
    - geofence
    - gimbal_control
    - global_position
    - gps_input
    - gps_rtk
    - gps_status
    - guided_target
    - home_position
    - imu
    - landing_target
    - local_position
    - log_transfer
    - mag_calibration_status
    - manual_control
    - mocap_pose_estimate
    - mount_control
    - nav_controller_output
    - obstacle_distance
    - obstacle_distance_3d
    - odometry
    - onboard_computer_status
    - open_drone_id
    - optical_flow
    - param
    - play_tune
    - rallypoint
    - rangefinder
    - rc_io
    - setpoint_accel
    - setpoint_attitude
    - setpoint_position
    - setpoint_raw
    - setpoint_trajectory
    - setpoint_velocity
    - sim_state
    - sys_status
    - sys_time
    - tdr_radio
    - terrain
    - trajectory
    - tunnel
    - vfr_hud
    - vision_pose
    - vision_speed
    - waypoint
    - wind_estimation
  plugin_denylist:
    - actuator_control
    - altitude
    - debug_value
    - ftp
    - hil
    - px4flow
    - vibration
    - wheel_odometry
```

Ownership is singular at runtime:

| Manifest group | Runtime owner |
|---|---|
| `platform` and `contract_version` | The selected Adapter image build lock and image metadata. |
| MAVLink transport and target IDs | Loader `/mavros_node` (`fcu_url`, `gcs_url`, `tgt_system`, `tgt_component`); router `/mavros_router` owns the resolved connection endpoints. |
| MAVLink source IDs/protocol, `ros`, and `plugins` | UAS node `/mavros`, loaded from the canonical configuration. |
| `system` | The enabled system-status plugin node `/mavros/sys`. |
| `time` | The enabled system-time plugin node `/mavros/time`. |
| `frames.local_position` | The enabled plugin node `/mavros/local_position`. |
| `frames.global_position` | The enabled plugin node `/mavros/global_position`. |
| `frames.imu` | The enabled plugin node `/mavros/imu`. |
| Per-Adapter values | The selected Adapter's deployment configuration, restricted to the override table below. |

The runtime configuration correction made during pre-implementation finalization
removes the forced executable name that collapsed loader, router, and UAS nodes
into duplicate `/mavros` names. Parameters must reach their declared owners;
public telemetry, command topics, services, message types, IDs, and namespace
remain unchanged.

MAVROS 2.15.1 declares scheduled alpha/beta gains and `convergence_window`, not
`timesync_avg_alpha`. The earlier `0.6` alias was unsupported and had no effect.
The four values above explicitly freeze the pinned implementation's effective
upstream defaults; they are not numerically equivalent to a single `0.6`
filter coefficient.

### Migration from 1.0.0 to 2.0.0

Version `1.0.0` prescribed an unimplementable `timesync_average_alpha: 0.6`
field. Version `2.0.0` removes that field, specifies the supported filter gains
and convergence window at the existing MAVROS 2.15.1 defaults, and corrects
loader/router/UAS parameter ownership. The unsupported local-position
`tf.send_fcu` parameter is also removed; supported `tf.send: false` continues to
prohibit dynamic motion TF. This changes the normative configuration
contract and therefore advances its major version. Public ROS interfaces,
message types, namespace, MAVLink IDs, and intended protocol remain unchanged.
The unsupported alias had no runtime effect; the new gains do not claim
numerical equivalence to it. There are no released hardware or production
autonomy clients to migrate. Both environment implementations must target
`2.0.0`; Hardware Adapter implementation remains deferred. Future supported
timing changes follow the compatibility rules below.

The pinned plugin implementation ignores global ROS arguments, including the
parameters file. Simulation bringup therefore applies the canonical plugin
groups through their parameter services after loading the plugins, before
semantic readiness can pass. Diagnostics independently verifies each value and
unique node ownership and detects later parameter changes. YAML presence or a
successful setter call alone is not conformance evidence.

The enabled list is closed: implementations must configure it as an explicit
allowlist and must also configure the explicit disabled list. A newly installed
plugin is disabled until a contract revision adds it. The MAVROS 2.15.1 APM
package configuration currently names `image_pub` and `vision_speed_estimate`
in its denylist, but neither name resolves to a declared 2.15.1 plugin.
Consequently, `vision_speed` is part of the frozen enabled behavior; the two
non-matching selectors are not part of the canonical configuration.

ROS uses ENU world coordinates and FLU body coordinates. MAVROS converts the
FCU's NED/FRD data at the boundary. The only MAVROS-owned transforms permitted
on shared `/tf` or `/tf_static` are the fixed convention transforms
`map -> map_ned`, `odom -> odom_ned`, and
`base_link -> base_link_frd`. MAVROS must not publish a dynamic
`map -> base_link` or `odom -> base_link` transform. State integration, not an
environment Adapter or simulator truth, will own the estimated vessel-motion
transform.

## Allowed per-Adapter overrides

No shared manifest field above is an environment override. The complete
per-Adapter override surface is:

| Override class | Simulation Adapter | Hardware Adapter |
|---|---|---|
| MAVLink transport | `fcu_url: udp://:14552@` | Must be supplied explicitly for the selected FCU connection; this contract chooses no hardware URL. |
| Physical device access | None for UDP SITL. | Device mapping, group membership, permissions, and udev integration required by the separately selected transport. No device is granted implicitly. |
| Environment timing | Adapter orchestration may set startup deadlines, retry budgets, and telemetry-freshness test thresholds appropriate to that environment. | Same, with values recorded by the Hardware Adapter. |

Environment timing overrides must not change `use_sim_time`, header timestamp
meaning, heartbeat parameters, or any `time` manifest value. Transport overrides
must not change the MAVLink protocol, IDs, namespace, plugins, frames, or public
ROS surface. UDP ports 14550 and 14551 retain their existing GCS and program/test
roles; the Simulation Adapter's MAVROS stream remains UDP 14552.

## Public ROS surface

Only the interfaces below are stable dependencies of contract `2.0.0`.
Additional endpoints may appear because an enabled MAVROS plugin creates them,
but autonomy and GCS code must not depend on an unlisted endpoint without a
contract revision.

### State, telemetry, and diagnostics

| Interface | Type | Contract meaning |
|---|---|---|
| `/mavros/state` | `mavros_msgs/msg/State` | FCU connection plus armed, guided, manual-input, mode, and system-status state. `connected` is the canonical connection bit. |
| `/mavros/imu/data` | `sensor_msgs/msg/Imu` | FCU attitude, angular velocity, and linear acceleration in ROS conventions; frame `base_link`. |
| `/mavros/local_position/odom` | `nav_msgs/msg/Odometry` | FCU local pose and velocity with covariance; parent frame `map`, child frame `base_link`. |
| `/mavros/global_position/global` | `sensor_msgs/msg/NavSatFix` | Fused FCU latitude, longitude, altitude, validity, and covariance. |
| `/mavros/global_position/compass_hdg` | `std_msgs/msg/Float64` | Heading in degrees when supplied by the FCU. |
| `/mavros/battery` | `sensor_msgs/msg/BatteryState` | FCU-reported power state and validity fields. |
| `/mavros/extended_state` | `mavros_msgs/msg/ExtendedState` | FCU extended vehicle state when supported. |
| `/mavros/sys_status` | `mavros_msgs/msg/SysStatus` | FCU sensor, load, voltage, current, communication, and error status. |
| `/mavros/statustext/recv` | `mavros_msgs/msg/StatusText` | FCU status-text severity and message. |
| `/mavros/status_event` | `mavros_msgs/msg/StatusEvent` | Structured FCU status event when supported. |
| `/mavros/time_reference` | `sensor_msgs/msg/TimeReference` | FCU time reference with source `fcu`. |
| `/mavros/timesync_status` | `mavros_msgs/msg/TimesyncStatus` | Observable time-offset and round-trip synchronization status. |
| `/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | MAVROS heartbeat, connection, sensor, link, and plugin diagnostics. This standard ROS aggregate is the sole public exception to the `/mavros/...` root. |

Messages retain MAVROS timestamps, validity/status fields, covariance, units,
and frame IDs. A relay must not replace a measurement timestamp with receipt or
publication time, relabel a frame without transforming the data, invent a valid
global fix, or treat a missing topic as zero-valued telemetry.

### Commands and acknowledgments

| Interface | Type | Required acknowledgment semantics |
|---|---|---|
| `/mavros/cmd/arming` | `mavros_msgs/srv/CommandBool` | The response carries `success` and the raw MAVLink `result`. Success must also be confirmed by the requested `armed` state on `/mavros/state`. |
| `/mavros/set_mode` | `mavros_msgs/srv/SetMode` | `mode_sent` means MAVROS parsed and sent the request; completion requires the requested `mode` on `/mavros/state`. |
| `/mavros/cmd/command` | `mavros_msgs/srv/CommandLong` | The response carries `success` and raw `COMMAND_ACK.result`. A command-specific state or telemetry transition is still required where one exists. |
| `/mavros/cmd/command_int` | `mavros_msgs/srv/CommandInt` | The response carries `success` and raw `COMMAND_ACK.result`. A command-specific state or telemetry transition is still required where one exists. |
| `/mavros/rc/override` | `mavros_msgs/msg/OverrideRCIn` | This stream has no protocol acknowledgment. Consumers must use bounded publication, then neutral or release all affected channels, and observe the intended safe state independently. |

Interface availability is not permission to issue a command. Command-ID
allowlists, operator/autonomy arbitration, pre-arm policy, failsafes, and GCS
loss behavior are owned by later safety and mission design. Generic conformance
checks on hardware must remain non-actuating unless an approved bench or
in-water procedure explicitly authorizes motion.

## Readiness states

The following states are deliberately separate and ordered:

1. **Process liveness:** the MAVROS process and `/mavros` node exist and respond
   to ROS graph and parameter queries. This says nothing about an FCU or data.
2. **Source readiness:** every required public publisher and service exists with
   the exact type above, required plugins match the manifest, and TF policy is
   correct. This still says nothing about an FCU connection.
3. **FCU readiness:** `/mavros/state` is fresh and has `connected: true`; required
   mission telemetry is fresh and valid; configured IDs and MAVLink v2 match;
   timesync and diagnostics are within the environment's declared limits.
4. **Mission readiness:** FCU readiness plus mission-specific state quality,
   transform availability, command authority, operator link, mode, pre-arm
   checks, health policy, and failsafes. This contract does not declare mission
   readiness and `connected: true` alone never implies it.

## Dependency control and rebuild policy

Both package names and the complete Debian versions in the manifest are build
lock values. Image builds must install those exact versions and fail closed if
they are unavailable. The ROS base image must be selected by an immutable image
digest recorded in the deployment build lock; a mutable
`ros:jazzy-ros-base-noble` tag alone is not sufficient. The produced image must
record the base digest, package versions, and contract version as inspectable
metadata.

A rebuild is accepted only when all of these checks pass:

- `dpkg-query -W ros-jazzy-mavros ros-jazzy-mavros-extras` exactly matches the
  two package versions in the manifest.
- The runtime parameter snapshot and ROS graph contract checks below pass.
- The Simulation Adapter semantic MAVROS smoke test passes, including a command
  acknowledgment and the final disarmed state.
- The Hardware Adapter's non-actuating connection/telemetry suite passes before
  any separately approved motion test.

Changing an upstream package version, image digest, plugin behavior, or any
public interface requires review; rebuilding must never resolve a newer apt
package silently.

## Observable conformance checks

Run these after sourcing the environment's ROS setup. Contract automation must
perform the assertions, rather than relying on visual inspection alone.

1. **Namespace and types:** capture `ros2 topic list -t` and
   `ros2 service list -t`; assert every public interface and type in this
   document exists, no public endpoint begins `/mavros/mavros/`, and the
   diagnostics exception is exactly `/diagnostics`.
2. **Plugins:** run `ros2 param get /mavros plugin_allowlist` and
   `ros2 param get /mavros plugin_denylist`; compare the resolved initialized
   and ignored plugin names exactly with the closed enabled and disabled lists.
   Any unlisted initialized plugin fails the check.
3. **IDs and protocol:** run
   `ros2 param get /mavros system_id`,
   `ros2 param get /mavros component_id`,
   `ros2 param get /mavros target_system_id`,
   `ros2 param get /mavros target_component_id`,
   `ros2 param get /mavros_node tgt_system`,
   `ros2 param get /mavros_node tgt_component`, and
   `ros2 param get /mavros fcu_protocol`; require `255`, `191`, `1`, `1`,
   `1`, `1`, and `v2.0` respectively. Capture the loader
   transport and router `fcu_urls`, `uas_urls`, and `gcs_urls`; require the
   resolved endpoint values match the selected configuration. The Adapter-side
   wire check must observe MAVLink 2 framing
   (`0xFD`) on the selected link.
4. **Connection:** receive a fresh `/mavros/state` sample and require
   `connected: true`; then continue sampling longer than the 10-second
   connection timeout to prove heartbeats persist. A Docker health status or
   node name is not a substitute.
5. **Telemetry:** receive fresh samples of `/mavros/imu/data`,
   `/mavros/local_position/odom`, and `/mavros/global_position/global`; verify
   exact types, finite required fields, expected frames, carried timestamps,
   and source validity/covariance. Mission-specific tests decide whether a
   reported invalid global fix is acceptable.
6. **Acknowledgment:** in simulation, call `/mavros/set_mode` and
   `/mavros/cmd/arming`, require their response fields and matching
   `/mavros/state` transitions, and always finish confirmed disarmed. Check a
   bounded `/mavros/setpoint_velocity/cmd_vel` command only in the explicit
   simulation smoke test, followed by zero-velocity stop, HOLD, and disarm.
   Hardware uses an approved non-actuating or bench procedure.
7. **Time and diagnostics:** capture `ros2 param dump /mavros/time` and
   `ros2 param dump /mavros/sys`; compare `time_ref_source`, `timesync_mode`,
   `timesync_alpha_initial`, `timesync_beta_initial`, `timesync_alpha_final`,
   `timesync_beta_final`, `convergence_window`, `timesync_rate`,
   `system_time_rate`, `heartbeat_rate`,
   `heartbeat_mav_type`, `conn_timeout`, and `disable_diag` with the manifest.
   Receive
   `/mavros/time_reference`, `/mavros/timesync_status`, and `/diagnostics`, and
   fail on stale/error connection diagnostics or a mission-specific timesync
   limit violation.
8. **TF:** inspect both `/tf` and `/tf_static`; allow the three fixed MAVROS
   convention transforms, reject MAVROS-owned dynamic `map -> base_link` and
   `odom -> base_link`, and reject all `/blueboat/ground_truth/...` data as an
   autonomy navigation source. Capture `ros2 param dump /mavros/local_position`,
   `ros2 param dump /mavros/global_position`, and
   `ros2 param dump /mavros/imu`; compare the frame and TF fields with the
   manifest. The existing
   `tests/ros_boundary_smoke.py` provides the current simulation-side boundary
   assertion.

## Compatibility and change control

The contract version follows semantic versioning:

- **Patch:** clarification or a stricter check that does not alter a value,
  name, type, unit, frame meaning, QoS expectation, or readiness semantic.
- **Minor:** backward-compatible addition. Existing interfaces and behavior
  remain available.
- **Major:** removal, rename, type change, namespace change, unit/frame/time
  semantic change, plugin-set change that removes or changes an endpoint,
  MAVLink/ID change, or changed acknowledgment/readiness meaning.

The conformance suite stores a normalized snapshot of public names/types,
parameters, resolved plugins, and permitted TF edges under the contract
version. A mismatch fails CI and Adapter acceptance. An intentional incompatible
change must first update the manifest and major version, update both Adapter
tests and consumers, and include an explicit migration note. Simulation and
Hardware may not advance contract versions independently.

## Current implementation status

The Simulation Adapter owns MAVROS in `Adapter/simulation/`, using a digest-pinned
ROS Jazzy base and exact MAVROS/MAVROS extras Debian revisions. Its canonical
`blueboat_sim_bringup/config/mavros.yaml` selects the root namespace, MAVLink v2,
source system/component 255/191, target 1/1, blank GCS URL, simulation UDP 14552,
and the frozen plugin, frame, and time configuration. Adapter diagnostics check
runtime identity, telemetry freshness, and command-service availability.

The [velocity benchmark verification](../../Simulation/docs/MAVROS_VELOCITY_BENCHMARK_VERIFICATION.md)
and subsequent [full RGB-D regression](../../Simulation/docs/RGBD_TRANSPORT_VERIFICATION.md)
record passing simulation command and data checks. These results do not
establish hardware transport, physical FCU compatibility, or vessel readiness;
the Hardware Adapter remains deferred.
