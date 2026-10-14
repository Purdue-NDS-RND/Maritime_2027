# RGB-D transport configuration verification

Date: 2026-10-04. Base revision: `3975a3c` on local `Pre_Implementation`.
The fix was developed on `codex/fix-rgbd-shm` and validated before integration.

## Problem and change

At the base revision, `make verify-rgbd` failed at 3.44 synchronized triples/sec
against the unchanged 8.00 Hz minimum. Controlled instrumentation subsequently
observed bridge conversion and successful ROS publication calls at 30.30 Hz,
but incomplete image receipt both by the camera boundary and public subscribers.
Profiles differing only in Fast DDS shared-memory segment capacity produced
public exact-triple rates of 30.30 Hz (32 MiB), 2.53 Hz (512 KiB), and 30.08 Hz
(32 MiB repeat). Complete received triples were preserved by matching in the
trimmed comparison windows. The internal allocator/discard operation was not
instrumented; these results isolate the capacity setting rather than every
individual loss mechanism.

The Simulation Adapter now loads
[`Adapter/simulation/config/fastdds.xml`](../../Adapter/simulation/config/fastdds.xml)
through a read-only Compose bind mount at `/etc/maritime/fastdds.xml`, selected by
`FASTRTPS_DEFAULT_PROFILES_FILE`. It configures a tested 32 MiB segment per DDS
participant and preserves UDPv4 discovery alongside SHM transport. This is a
sufficient tested budget, not a measured minimum. Its per-participant allocation
increases shared-memory use compared with the default 512 KiB configuration.

Only the Simulation Adapter service receives this profile. Existing images were
reused: a rebuild is unnecessary for the mounted configuration. No instrumentation,
transport profile override for evaluation, QoS/history change, callback change,
normalization optimization, timestamp tolerance change, freshness change, boat
dynamics change, or upstream pin change was used for production validation.
Hardware settings and checklist status are outside this change.

## Static and runtime validation

`make validate` passed, including Compose resolution, XML parsing of the profile,
and Docker-backed Gazebo SDF checks. All 34 existing unit tests passed:

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s Simulation/tests -p 'test_*.py' -v
python3 -m unittest discover -s Simulation/tests/evaluation -p 'test_*.py' -v
python3 -m unittest discover -s autonomy/tests -p 'test_*.py' -v
```

Live inspection verified the read-only mount, the profile environment variable,
and equal host/container SHA-256:
`b7f3dd6ec8c7bf0cf89b931d5e66809d0ff4c4c5e2079b475a62046baf67b669`.
The active camera-boundary participant's segment was 35,127,840 bytes including
Fast DDS management overhead, consistent with the configured 32 MiB capacity.
Production validation used standard Makefile launch/evaluation paths from
`Simulation/`, not the temporary investigation launcher or an LD_PRELOAD probe.

`make verify-rgbd` passed with exit 0. The existing suite exercised:

| Stage | Result |
|---|---|
| `one` source | PASS: 119 exact RGB/depth timestamp pairs at 30.30 Hz simulated cadence. |
| `one` public RGB-D | PASS: 100 exact triples at 30.30 Hz; deferred ArUco, depth, geometry, entity truth, and public TF checks passed. |
| Cross-container boundary | PASS: public camera and FCU data; truth TF excluded from shared navigation TF. |
| MAVROS control | PASS: GUIDED velocity movement, zero-velocity stop, HOLD, and disarm. |
| `gate` source | PASS: 120 exact RGB/depth timestamp pairs at 30.30 Hz simulated cadence. |
| `gate` public RGB-D | PASS: 100 exact triples at 30.30 Hz, with the same semantic checks. |
| `multi`, seed 42 | PASS: live world contains the boat, water surface, and all four buoy entities. The existing suite does not run the RGB-D evaluator for this case. |
| Camera-only original control | PASS: autonomous BlueBoat MAVLink smoke, including travel, HOLD, RTL return, and disarm. |

The full command ended with:

```text
Full RGB-D, scenario, MAVROS, and original-control verification passed.
```

The unchanged RGB-D minimum remains 8.00 Hz. These are simulator results, not
hardware or shared-autonomy readiness evidence.

Final cleanup showed an empty Compose project, no running Docker containers,
no matching simulator/bridge/Adapter/MAVROS processes, and no UDP listeners on
14550/14551/14552/9002. Three temporary Xauthority files from this suite were
left by the existing shutdown wrapper and removed explicitly after shutdown;
this change does not repair that separate lifecycle issue. No matching temporary
Xauthority files remain. SITL parameter state was retained. `git diff --check`
passed before commit.

## Evidence

Ignored runtime evidence under `Simulation/logs/`:

- `rgbd-shm-validate.log`: static and Gazebo SDF checks.
- `rgbd-shm-verification.log`: full regression command output.
- `rgbd-shm-runtime-inspection.txt`: deployed profile and active participant evidence.
- `verify-one.log`, `verify-gate.log`, `verify-multi.log`, and
  `verify-camera-only.log`: standard scenario launch logs.
- `rgbd-investigation/followup-findings.md`: controlled capacity comparisons and
  the independent, uninstrumented one-scenario evaluator trial that preceded this fix.

These logs are local runtime artifacts and are not committed. This report supplies
the reviewable result summary without committing generated worlds or logs.
