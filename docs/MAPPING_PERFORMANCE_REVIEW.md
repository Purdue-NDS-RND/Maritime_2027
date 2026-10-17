# Mapping performance review — 2026-10-17

Reviewed commit `9339e225fba48d2c808f00b25c2daafac7a38a98` on
`review/mapping-performance`. This is an investigation, with no production code,
threshold, launch configuration, or running-session changes.

The popup is the clearest immediate optimization target. The small-map bearing
filter is fast, but its diagnostic timer excludes much of the pipeline. Larger
maps also expose expensive initialization and association work.

## Measured evidence

The existing live session had two initialized tracks, one confirmed and one
stale. SHA-256 checks confirmed the running viewer, mapper core, and mapper node
matched this checkout. A five-second `/proc` CPU delta inside the container gave:

| Process | CPU, where 100% is one core |
| --- | ---: |
| Matplotlib popup | 100.2% |
| ArUco detector | 79.2% |
| Mapper ROS process | 49.0% |
| Live clock adapter | 34.4% |
| Headless RViz overlay process | 10.8% |

These are short observations of an already-running simulation, not isolated
benchmarks. An eight-second read-only subscription sample received 5,936 clock
messages, 119 detection arrays, 24 aligned poses, and 63 diagnostics. At the
sample's end, latest simulation time was 1988.771 s, detection time 1988.713 s,
aligned pose time 1988.464 s, and map time 1988.449 s. The approximately 0.322 s
map age is one snapshot, not a latency distribution. No stale-image warning or
queue-overflow counter was present; five frames were pending. The cumulative
`invalid_input` count was 39; its cause was not established by this audit.

Synthetic component timings on the host, with one OpenBLAS thread:

| Component | Median | p95 | Repetitions |
| --- | ---: | ---: | ---: |
| Initialize, 4 views | 1.30 ms | 1.47 ms | 20 |
| Initialize, 20 views | 21.30 ms | 22.07 ms | 20 |
| Initialize, 40 views | 89.06 ms | 112.83 ms | 20 |
| Assign, 2 tracks / 2 detections | 0.043 ms | 0.062 ms | 20 |
| Assign, 32 tracks / 32 detections | 3.08 ms | 3.75 ms | 20 |
| Assign, 128 tracks / 128 detections | 53.34 ms | 73.54 ms | 20 |
| Full popup redraw, 2 tracks | 284.66 ms | 383.98 ms | 8 |
| Full popup redraw, 16 tracks | 508.35 ms | 648.46 ms | 8 |

Initialization used exact bearings toward (10, 3) from camera positions
(0, 0.4i). Assignment used 20 m radius landmarks distributed across a 2.8 radian
arc and four repeating categories. Plotting used 600 history samples per track,
a 1,500-point boat trail, and no truth overlay. It executed the unchanged `Plot`
class extracted from the source using Python AST, with synthetic node state and
Matplotlib Agg. Agg includes rendering synchronously in `draw_idle`; Tk schedules
that rendering differently. These numbers establish component costs, not live
GUI frame rates or full-pipeline throughput. The 16-track run also emitted a
warning that tight layout could not accommodate all decorations.

Local scripts and raw output are retained in ignored
`Simulation/logs/mapping-review/`: `profile_mapping.py`, `profile.txt`,
`live-sample.txt`, and `live-cpu.txt`. Reproduce the synthetic measurements from
the repository root with:

```bash
OPENBLAS_NUM_THREADS=1 MPLCONFIGDIR=/tmp/mapping-review-mpl \
  python3 Simulation/logs/mapping-review/profile_mapping.py
```

## Findings and recommended order

1. **Reuse plot objects and layout instead of rebuilding the popup.**
   [`Plot.draw`](../Monitor/tools/mapping_view.py#L213) clears all three axes,
   recreates lines, labels, legends and ticks, and calls `tight_layout()` every
   redraw. The loop requests redraws every 0.5 s even when estimates are unchanged.
   One instrumented two-track draw spent 0.288 s of its 0.638 s in `tight_layout`
   under cProfile; instrumentation increases total cost. Create artists once,
   update their data, and update legends only when track membership/state changes.
   Recompute layout on resize, and redraw based on dirty data plus a slow status
   heartbeat. Keep the current separate plotting process. Also preserve pan/zoom
   on the history axes: clearing them currently resets their limits each draw.

2. **Measure full processing latency before optimizing the EKF.**
   [`drain`](../autonomy/ros_ws/src/maritime_localization/maritime_localization/mapping_node.py#L200)
   starts `last_processing_ms` immediately before `mapper.process()`. The live
   sample reported 0.076 ms, but that excludes pose lookup, TF, bearing building,
   message construction/publication, map/grid publication, and executor overhead.
   Add separate queue-wait, build, algorithm, and publication timing distributions,
   plus source age and detector replacement counters. The receipt-clock adapter
   waits for enclosing FCU references; reducing filter computation cannot remove
   that wait. Keep acquisition-time interpolation and explicit timing uncertainty.
   Around 742 clock messages/s were observed; profile callback/executor overhead
   and required clock consumption before changing clock delivery. Its contribution
   to the measured process CPU remains a hypothesis.

3. **Bound initialization seed work more tightly.**
   [`initialize`](../autonomy/ros_ws/src/maritime_localization/maritime_localization/bearing.py#L39)
   considers every view pair, then scores each accepted seed against all views.
   Seed scoring can grow cubically with view count; the solver iteration setting
   does not bound this preceding work. At 40 views, one attempt already took
   about 89 ms median in the fixture. Multiple unresolved tracks may attempt
   initialization in the same single-threaded mapper callback. Precompute residual
   arrays and select a bounded, geometrically diverse seed set. Validate robustness
   against the existing noisy/outlier and weak-geometry cases before adoption.

4. **Reduce association work for larger scenes while preserving ambiguity checks.**
   [`_assign`](../autonomy/ros_ws/src/maritime_localization/maritime_localization/mapping.py#L127)
   builds every observation/track cost, copies the assignment matrix, and reruns
   Hungarian assignment for each chosen real edge to check its alternative.
   At two tracks this is inexpensive; at 128 tracks/detections it took about
   53 ms median. Partition by category and independent feasible-candidate
   components, retaining explicit unmatched alternatives and global-margin
   semantics within each component. Do not replace ambiguity handling with greedy
   nearest-neighbor matching merely to improve timings.

5. **Separate map updates from visualization and grid refresh.**
   [`publish_map`](../autonomy/ros_ws/src/maritime_localization/maritime_localization/mapping_node.py#L255)
   rebuilds the semantic map, 200×200 grid, covariance markers and diagnostics at
   10 Hz, including when no new frame was processed. It publishes the grid on two
   topics and uses DELETEALL plus replacement markers. Cache derived content by
   map revision and let diagnostics keep their own heartbeat. Preserve transient
   local delivery, late subscribers, deletion behavior, and the compatibility
   topic. This is observed repeated work; its individual runtime share was not
   measured. The live launcher also forces debug images on: make that optional,
   and avoid annotation/serialization when no debug viewer subscribes.

6. **Plan track retention before longer missions.**
   [`process`](../autonomy/ros_ws/src/maritime_localization/maritime_localization/mapping.py#L183)
   expires only unresolved tracks. Initialized tracks, including stale and
   inconsistent ones, retain the 128 available slots indefinitely. Eventually
   new landmarks are rejected. Define active versus archived map storage and
   explicit reactivation/identity rules rather than silently deleting obstacles.
   Also, category probability is currently hardcoded to 1.0 and existence
   confidence is a heuristic. These fields should be distinguished from calibrated
   probabilities before consumers rely on them.

## Validation and limits

The existing 20 mapping/pose-buffer tests passed:

```bash
cd Simulation
PYTHONPATH=../autonomy/ros_ws/src/maritime_localization:../autonomy/ros_ws/src/maritime_perception \
  python3 -m unittest discover -s tests/evaluation/benchmarking -p test_mapping.py -v
```

This review did not modify production behavior, restart the simulator, move the
boat, or perform a new accuracy benchmark. Runtime observations do not establish
on-water accuracy. The practical next change is incremental popup rendering,
with a before/after CPU and GUI responsiveness comparison at the same map size;
the next diagnostic change is full-pipeline timing.
