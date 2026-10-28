# Canonical runtime images and launch defaults

The current runtime tags are `maritime-sim:latest`, `maritime-boat:latest` and
`maritime-gcs:latest`. `SIM_IMAGE`, `BOAT_IMAGE` and `GCS_IMAGE` retain overrides.
Build/run from each application's directory with `make build` / `make run`.
Simulator teleop, static image checks and buoy smoke use `SIM_IMAGE` too.
GCS tests use the selected GCS runtime as their base; `GCS_TEST_IMAGE` overrides
the temporary test tag. Remove that test tag when finished if keeping inventory minimal.

`make -C simulation build-cached` verifies the four pinned source revisions,
then rebuilds application/plugin assets over the installed canonical simulator.
It defaults `BASE_IMAGE` to `maritime-sim:latest`; no deleted historical base tag
is needed. `make build` remains the clean dependency/bootstrap build. This
maintenance checked a cached build, not a fresh network dependency build.

Plain simulator `make run` defaults to calm water, fixed slalom, cameras off.
In a terminal it opens the existing setup menu; Enter preserves those defaults.
The menu controls water, scene, seed, cameras, enabled camera layout and telemetry
rate. Environment values skip the corresponding questions; explicit WORLD or
SCENARIO skips the menu. `scripts/run.sh --non-interactive` uses environment/defaults.
Resolved settings are printed before Docker startup and recorded in each run.
`CAMERA_FPS` and `SIM_GPU` remain environment controls. An explicit `BOAT_MODEL`
enables its camera layout unless CAMERAS is supplied. Telemetry remains 4 Hz by
default; no firmware parameters, gains, physics, source pins or ports changed.

## Fresh integration check, 2026-10-28

Evidence: `simulation/logs/canonical-runtime/`; simulator run
`20261028T175441-1211274`. This is one integration pass, separate from historical
three-consecutive-run acceptance. It used the canonical tags through the normal
launcher/Compose paths, with explicit `MAVLINK_STREAMRATE=20 WIPE_PARAMS=1` for
the existing measured `sim-slalom-2_0-p16-20hz-v2` profile.

Before boat startup, the retained simulation-only `profile_settings.py` explicitly
staged the profile and saved original gains in `settings.json`. It was invoked
from `maritime-boat:latest` with `simulation/` mounted at `/simulation`, using
`apply <profile> --state <new-state-file> --baseline-position-hz 20`. The boat
Compose environment also supplied the profile's exact `BOAT_GEOMETRY_SHA256`.
These are mandatory setup steps for this measured mission, not launch defaults.
The boat only verifies settings; it never silently applies them.

The frozen map's scene, live image/snapshot and all buoy centres matched
(`frozen-map-check.json` in the run directory, zero buoy difference). A fresh
stationary alignment observation passed; the map retains its historical
multi-position/two-heading proof. The previously manually authored seven-waypoint
workspace was imported without approval, then Validate, Approve, Upload and
Start were clicked separately in Chrome. Upload and Start operation results
were confirmed successful. New approval/mission: `eff52d5f-39ca-4c99-9bcd-f835396ab011`,
revision `f6bdffc1214d2f2c6c0ea574c1fd720b44e46604e8e2480674562b14d62bace3`.
The browser showed actual movement, oriented marker, forward arrow and changing
permanent heading label (`browser-map.png`).

Independent evaluation passed all six passage/side/stern checks, contacts,
whole-hull clearance and finish settling, using 73,621 contiguous physics samples:

| Measurement | Result |
| --- | --- |
| Minimum full-attitude collision-prism clearance | 1.26141 m |
| Evaluated motion/finish window | 73.620 s |
| Actual mean / peak speed (target 2.0 m/s) | 0.73935 / 1.91754 m/s |
| Maximum finish-window position error | 0.56826 m |
| Peak finish-window speed over 5 s | 0.19969 m/s |

The auxiliary HTTP observer initially exited before the boat HTTP server was
ready. Its failure and empty output remain saved. The independent physics
recorder was complete. `evaluation-driver.py` derives the start boundary one
second before the first 1 cm translation from the alignment-verified stationary
pose, and ends after the independently detected five-second finish window.
`evaluation-extended-hold.json` also passes with the longer stopped tail.
This check therefore does not claim a complete HTTP tracking-error observation.
Contact-recorder qualification reuses the saved deliberate-contact proof for the
same physical scene; no new deliberate collision was staged.

Final HOLD (mode 4), zero speed, explicit browser Disarm and successful operation
were confirmed. The boat was stopped before `profile_settings.py restore`;
`settings.json` verifies every original parameter equals its restored readback,
with no errors. All task runtimes were shut down, and the pre-test GCS workspace
was restored after saving the test workspace/approval. Mission journals and
approvals remain intact. A subsequent plain `make run` reached readiness in
`20261028T175956-1230599` with calm/slalom/cameras off and 4 Hz, then was stopped.

Static validation passed, including 13 terminal-menu tests, 15 evaluator tests
and 6 calibration qualification tests. All 26 boat and 25 GCS tests passed;
normal GCS/boat builds and React production build passed. Source checks verified
all candidate boat/GCS Python modules against the checkout. The simulator pins
were checked before its cached rebuild. Candidate runtime IDs during the slalom
and final rebuilt IDs are both retained in `integration-containers.json`,
`candidates.json` and `canonical-images.json`; rebuilding boat/GCS did not change
application sources. The final rebuilt images also passed the container suites.

Physical boat/radio behavior remains unverified. No new RC, telemetry-loss,
backend-outage or camera acceptance is claimed by this check. Historical
acceptance records retain their truthful image names, superseded for current use.

## Scoped Docker cleanup

Refreshed inventory and stopped-container mount/diff inspection are saved before
cleanup. Bind-mounted logs, recordings, profiles, missions and workspaces were
retained. The legacy Foxglove container's writable ROS logs were copied and its
entire filesystem exported/compressed as `legacy-gcs-container.tar.gz` before
removal. Its image is no longer a runtime dependency.

Removed 43 obsolete/test image tags, including old simulator, milestone/followup,
Foxglove, adapter, mapping, autonomy/Nav2, monitor, benchmark and evaluation images.
Exact tags and Docker deletion output are in `removed-image-tags.json` and
`image-removal.log`. Five original stopped containers were explicitly removed;
the other two original Compose containers were replaced through normal launch
and subsequently shut down/removed. All seven original obsolete containers are
gone, with journals/mount data preserved. No volume or shared build cache was
pruned; unrelated `python:3.12-slim` and `alpine:3.21` remain.

Host filesystem used space fell from 225,759,506,432 to 217,777,389,568 bytes:
**7,982,116,864 bytes (7.98 GB / 7.43 GiB) net recovered**, including new evidence,
backups and build output. This is a measured whole-filesystem delta, so unrelated
host activity can affect it. Docker's image accounting fell from 27.27 to 10.19 GB;
that apparent difference is not physical recovery because layers/cache are shared.

Final canonical image identities:

| Runtime | Image ID |
| --- | --- |
| `maritime-boat:latest` | `sha256:17b8231e1667bbdd3c9444a5458548124768ab060ce5aa155b9f0876508007fd` |
| `maritime-gcs:latest` | `sha256:6b263bbd934f3016b7f904ad878d08a7ead24d23d6ea4f71d18cbf11ccc7d526` |
| `maritime-sim:latest` | `sha256:4f1b103403659b6ab23972e6883ea1f3067c36d03d1a0ca4bea8368fad795e1a` |
