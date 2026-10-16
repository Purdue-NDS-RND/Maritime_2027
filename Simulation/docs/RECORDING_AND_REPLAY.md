# Record and replay a buoy run

Record one manually driven simulation run and reuse its ROS messages while
developing buoy detection, positioning, and mapping algorithms. Playback does
not need Gazebo, SITL, MAVROS, or the Adapter. This first milestone provides
datasets and replay; it does not implement algorithms or accuracy scoring.

## One-command terminal menu

From `Simulation/`, run:

```bash
make record
```

The menu offers recording, browsing saved runs, quality/details, recorder logs,
replay, replay with RViz, and building/updating the recording tools. Recording
prompts for a name and optional duration. Playback prompts for speed, ROS domain,
and whether to start paused. Replay with RViz opens the viewer automatically and
closes that viewer when playback ends; existing Monitor windows stay open.

Ctrl-C finishes an active recording/replay and returns to the menu. At prompts,
`q` goes back; at the main menu it exits. EOF or Ctrl-C at a prompt closes the
menu. The simulation must already be running for capture; continue driving with
teleop or QGroundControl. Browsing and playback work with the simulator stopped.

The explicit commands below remain available for automation. `NAME=...` skips
the menu. Redirected/non-interactive calls require explicit arguments and never
wait for menu input.

The menu was verified in a real terminal with a live capture, saved quality
inspection, and replay with automatic RViz cleanup. The focused menu tests
also cover cancellation, invalid input, non-interactive use, and isolated cleanup.

## Capture

Build the existing Monitor image once, then start a buoy scenario:

```bash
make -C ../Monitor build
SCENARIO=gate make run
```

All commands in this guide run from `Simulation/`. In a second terminal:

```bash
make record NAME=gate-pass-01
```

Wait for **Recording**, then drive using `make teleop` in another terminal or
QGroundControl. Approach the buoys, pass them, and turn to view them from another
angle. Stop the recording with Ctrl-C. This stops only recording; the boat and
simulator keep running. Stop or disarm the boat through your driving tool.

For a bounded capture, `make record NAME=gate-pass-02 DURATION=60` records for
60 wall seconds after the recorder subscribes. Names cannot be reused or
overwritten. Capture itself never arms or commands the boat.

Full-resolution RGB-D needs substantial storage: the local ten-second capture
used about 0.8 GB with compression. Actual size depends on the scene.

## Inspect

```bash
make recording-info RECORDING=gate-pass-01
```

Each dataset lives in ignored `logs/recordings/<name>/`:

| File | Contents |
| --- | --- |
| `bag/` | Standard ROS 2 MCAP bag with fast Zstd chunk compression. |
| `dataset.json` | Capture status, source run, revision, image IDs, and clock caveat. |
| `scenario.manifest.json` | Resolved buoy entities, categories, seed, and spawn poses. |
| `compose.yaml`, `identity.txt` | Immutable configuration copied from the running simulation. |
| `topics.yaml`, `qos.yaml` | Topic selection and static-TF QoS used for this dataset. |
| `transport.xml` | Snapshot of the Adapter's tested shared-memory transport profile. |
| `clock.csv` | Simulation clock paired with system/monotonic receipt times, up to 10 Hz. |
| `quality.json` | Message counts, gaps, source timestamp ranges, RGB-D matches, and boat movement. |
| `recorder.log` | Standard rosbag recorder output and errors. |

The topic list includes RGB/depth/calibration, camera transforms, MAVROS boat
state, clock/time diagnostics, and boat/buoy ground truth. Buoy topics come from
entity names in the saved manifest, so repeated marker IDs remain separate.
Commands, service requests, private camera intermediates, and Monitor visuals
are not recorded. `topics.yaml` is the one place to edit the default topic list.

Dataset checks read the bag itself. Required streams and camera transforms
must exist, synchronized RGB-D triples must meet the unchanged 8 Hz gate, and
required continuous streams must have no gaps over two simulation seconds.
Unmatched frames are counted and reported. A **complete** capture means the
recorder finalized and checks ran; check **PASS/FAIL** separately. A dataset
check does not establish localization accuracy or scene difficulty.

Camera receive queues buffer 30 messages and the 1 kHz simulation clock buffers
1000 messages. These recorder-side settings avoid shallow live-view queues;
the Adapter's source settings and the 8 Hz gate are unchanged. Total transport
losses reported by rosbag are also shown; a passing gate does not mean zero loss.

Failed captures remain available as **incomplete** with an error reason.
Simulation clock resets end capture as incomplete; start a fresh recording.
Interrupted shutdown or disk exhaustion can also leave an incomplete bag.

## Replay and view

```bash
make replay RECORDING=gate-pass-01
```

Playback uses ROS domain **97** by default, independently of the live stack.
Sensor, state, and truth topics replay together under their original names.
The player publishes the replay clock; it does not also republish the captured
`/clock`. Only the saved topic list is played. Existing input publishers on the
replay domain cause an error rather than mixing live and recorded inputs.

In another terminal, open the existing recorded scene view:

```bash
make -C ../Monitor rviz-sim ROS_DOMAIN_ID=97
```

Start paused when you need time to open RViz or launch future algorithm nodes:

```bash
make replay RECORDING=gate-pass-01 START_PAUSED=1
make replay RECORDING=gate-pass-01 RATE=0.5
```

With an interactive terminal, Space pauses/resumes rosbag playback. Use
`REPLAY_DOMAIN_ID=98` and match Monitor/algorithm nodes if domain 97 is occupied.
Future algorithm nodes should use simulation time and subscribe only to their
documented sensor/state inputs. Truth remains evaluation data, even though it
is visible on the replay graph. Monitor derives its scene transforms privately.

## Timing limitation

Camera and simulator-truth headers currently use simulation time. MAVROS
odometry/IMU headers use Unix time. Recording uses simulation time for bag
ordering while preserving all original message headers. Playback reproduces
those headers, including their different clock domains.

`clock.csv` saves receipt-time correspondence for later analysis. It is not
calibrated sensor synchronization: transport delay and FCU timestamp behavior
still matter. Before fusing camera observations with boat state at image capture
time, implement and validate that alignment explicitly. Do not compare these
raw header timestamps directly or assume MAVROS `map` equals Gazebo `world`.

The bags already support camera-only algorithm work and recorded-scene
inspection. They also retain the raw state/truth needed for later mapping work.
Replay gives algorithms the same recorded inputs; asynchronous processing and
subscriber drops can still change which messages an algorithm processes.

For the shared-memory transport verified here, run the consumer with the player's
host UID/GID, host IPC, and the saved `transport.xml` Fast DDS profile. For
example, with playback on domain 97, run a sourced ROS shell using:

```bash
docker run --rm -it --network host --ipc host --user "$(id -u):$(id -g)" \
  -e ROS_DOMAIN_ID=97 -e FASTRTPS_DEFAULT_PROFILES_FILE=/dataset/transport.xml \
  -v "$PWD/logs/recordings/gate-pass-01:/dataset:ro" \
  maritime-monitor:jazzy bash --noprofile --norc
```

Monitor's regular UDP view is useful for visualization but may drop image
frames. Future per-frame benchmarks can also read the MCAP directly through
`rosbag2_py`, avoiding subscriber delivery as an experimental variable.

## Code organization and checks

`recordings/recordings.py` handles host paths, provenance, and the disposable
Monitor container. `recordings/session.py` runs the ROS-side session and reads
the finished bag. Both stay under Simulation; no new ROS package, image,
Adapter relay, or autonomy service is needed.

`recordings/menu.py` provides the terminal interface and invokes the same CLI
commands. Its temporary RViz viewer has a unique Compose project for isolated
cleanup; the menu does not manage the running simulator.

Capture shares host IPC and runs with the same user as the root Adapter so it
can use that profile's shared-memory transport. It restores generated files to
the host user's ownership on exit. Playback and ordinary Monitor sessions run
as the host user. Playback also enables shared memory using the saved profile;
ordinary Monitor sessions keep their existing UDP profile.

```bash
make validate
python3 -m unittest discover -s tests -p 'test_record*.py' -v
docker run --rm --network none -v "$PWD:/simulation:ro" \
  maritime-monitor:jazzy \
  python3 -m unittest discover -s /simulation/tests -p test_recordings.py -v
```

The container command also exercises real MCAP files. For live acceptance,
capture a 60-second manual pass, inspect the saved data, and replay on the
separate domain with RViz. Confirm boat movement and changing buoy views;
container health and a successful recorder startup are not sufficient.

### Local verification, October 15, 2026

- Final stationary capture: 30 wall seconds, 612 exact RGB/depth/CameraInfo
  triples at 30.30 Hz, zero unmatched camera frames, and zero recorder-reported
  transport losses. The bag covers 20.20 simulation seconds and uses 2.04 GB.
- Full-speed replay with matching shared memory: all 612 messages on each
  camera topic, 80 MAVROS odometry samples, 1010 boat-truth samples, and 101/99
  buoy-truth samples arrived. Source headers and payloads matched the bag.
  A late subscriber received both camera mounting transforms.
- The existing Monitor scene probe passed against half-speed playback in RViz:
  boat/buoy poses, connected private camera transforms, calibrated RGB plane,
  and native CameraInfo subscription. Start-paused playback resumed with Space.
- SIGINT finalized a recording; an isolated backward-clock trial was marked
  incomplete. Static validation and all ten focused tests passed.

Earlier trials lost frames with UDP or shallow receive queues. The final
settings use shared memory and explicit queues; inspection reports unmatched
frames and transport losses rather than assuming success. Local probe results
are retained under `logs/recording-verification-20261015/`.

A 60-second manually driven pass and localization accuracy evaluation have not
been performed. Camera-to-MAVROS time alignment remains unvalidated.
