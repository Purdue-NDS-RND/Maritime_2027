"""Exercise the existing core with asynchronous normalized inputs, offline or ROS 2.

This is a bounded survey test harness, not raw IMU/GNSS fusion or a smoother.
Single-threaded admission preserves the processing core's ownership of its state.
"""
import argparse
from collections import Counter
from copy import deepcopy
import heapq
import json
from pathlib import Path
import random
import time

from .pipeline import PerceptionPipeline
from .replay import line, write_json
from .validation import Unavailable, load_json, timestamp


class AsyncRunner:
    def __init__(self, settings, *, wait_s=.5, reorder_s=.05, max_pending=32):
        if not 0 <= reorder_s <= wait_s <= 30 or type(max_pending) is not int or not 1 <= max_pending <= 1024:
            raise Unavailable("invalid_async_limits")
        if settings["pose_history_s"] <= wait_s + reorder_s:
            raise Unavailable("async_wait_exceeds_pose_history")
        self.pipeline = PerceptionPipeline(settings)
        self.wait_ns, self.reorder_ns = round(wait_s*1e9), round(reorder_s*1e9)
        self.max_pending = max_pending
        self.pending, self.pending_ids = [], set()
        self.counter, self.counts, self.diagnostics = 0, Counter(), []
        self.max_depth, self.max_wait_ns = 0, 0

    def reject(self, reason, **extra):
        self.counts["rejected:" + reason] += 1
        self.diagnostics.append(dict(status="rejected", reason=reason, **extra))

    def submit(self, event, arrival_ns):
        timestamp(arrival_ns)
        try:
            if not isinstance(event, dict) or set(event) != {"kind", "data"}:
                raise Unavailable("invalid_event_envelope")
            kind, data = event["kind"], event["data"]
            self.counts["input:"+kind] += 1
            if kind in ("vehicle_state", "imu_state"):
                before = len(self.pipeline.pending_diagnostics)
                if kind == "vehicle_state":
                    self.pipeline.add_state(data)
                else:
                    self.pipeline.add_imu_state(data)
                added = self.pipeline.pending_diagnostics[before:]
                for item in added:
                    self.reject(item["reason"], kind=kind, arrival_ns=arrival_ns)
                if not added:
                    self.counts["accepted_states"] += 1
            elif kind == "frame":
                stamp, _ = self.pipeline.clock.at(data["stamp_ns"], data["clock_id"])
                frame_id = data.get("id")
                if not isinstance(frame_id, str) or not frame_id:
                    raise Unavailable("invalid_frame_id")
                if stamp <= self.pipeline.last_frame_ns or frame_id in self.pending_ids or frame_id in self.pipeline.frame_ids:
                    raise Unavailable("async_late_or_duplicate_frame")
                if len(self.pending) >= self.max_pending:
                    raise Unavailable("async_frame_queue_full")
                heapq.heappush(self.pending, (stamp, self.counter, arrival_ns, deepcopy(data)))
                self.counter += 1
                self.pending_ids.add(frame_id)
                self.max_depth = max(self.max_depth, len(self.pending))
            else:
                raise Unavailable("unknown_event_kind")
        except (Unavailable, AttributeError, KeyError, TypeError, ValueError) as exc:
            self.reject(str(exc), arrival_ns=arrival_ns)

    def tick(self, now_ns, *, published_ns=None, final=False):
        timestamp(now_ns)
        results = []
        while self.pending:
            stamp, _, received, frame = self.pending[0]
            age = max(0, now_ns-received)
            if not final and age < self.reorder_ns:
                break
            reason = None
            try:
                self.pipeline.pose.at(stamp)
            except Unavailable as exc:
                reason = str(exc)
            if reason == "pose_not_bracketed" and not final and age < self.wait_ns:
                break
            heapq.heappop(self.pending)
            self.pending_ids.remove(frame["id"])
            self.max_wait_ns = max(self.max_wait_ns, age)
            if reason == "pose_not_bracketed":
                self.reject("async_pose_wait_timeout", frame_id=frame["id"], wait_ns=age)
                self.pipeline.pending_diagnostics.append(dict(kind="async", status="rejected", reason="async_pose_wait_timeout"))
            if stamp <= self.pipeline.last_frame_ns:
                self.reject("async_late_or_duplicate_frame", frame_id=frame["id"])
                continue
            # In virtual replay, retain the original publication epoch and add queue delay.
            # Live mode supplies host UTC only when settings already map input clocks to UTC.
            try:
                frame["published_ns"] = timestamp(published_ns if published_ns is not None else frame["published_ns"]+age)
                report, ledger = self.pipeline.process_frame(frame)
                self.counts["reports"] += 1
                self.counts["observations"] += len(ledger)
                self.counts["frames_with_observations"] += bool(ledger)
                for item in report["diagnostics"]:
                    if item.get("status") == "rejected":
                        self.counts["report_rejected:"+item["reason"]] += 1
                results.append((report, ledger))
            except (Unavailable, KeyError, TypeError, ValueError) as exc:
                self.reject(str(exc), frame_id=frame["id"])
        return results

    def summary(self):
        return dict(schema="maritime.async_test", version=1, counts=dict(sorted(self.counts.items())),
                    pending_frames=len(self.pending), maximum_queue_depth=self.max_depth,
                    maximum_queue_wait_s=self.max_wait_ns*1e-9,
                    physical_accuracy_validated=False,
                    scope="normalized source contracts; no raw-sensor fusion or fixed-lag smoothing")


class Results:
    def __init__(self, output):
        self.path = Path(output)
        self.path.mkdir(parents=True, exist_ok=False)
        self.reports = self.observations = self.arrivals = None
        try:
            self.reports = (self.path/"reports.jsonl").open("x")
            self.observations = (self.path/"observations.jsonl").open("x")
            self.arrivals = (self.path/"arrivals.jsonl").open("x")
        except Exception:
            self.close()
            raise

    def write(self, results):
        for report, ledger in results:
            self.reports.write(line(report))
            for item in ledger:
                self.observations.write(line(item))
        self.reports.flush()

    def finish(self, runner):
        write_json(self.path/"summary.json", runner.summary())
        with (self.path/"diagnostics.jsonl").open("x") as stream:
            stream.writelines(line(item) for item in runner.diagnostics)

    def close(self):
        for stream in (self.reports, self.observations, self.arrivals):
            if stream is not None:
                stream.close()


def arrival_schedule(session, *, frame_delay_ms=20., state_delay_ms=80., jitter_ms=0.,
                     drop_state_every=0, drop_frame_every=0, seed=7):
    if min(frame_delay_ms, state_delay_ms, jitter_ms, drop_state_every, drop_frame_every) < 0:
        raise Unavailable("invalid_async_fault_settings")
    session = Path(session)
    settings = load_json(session/"config.json")
    from .timing import ClockMapper
    mapper, rng, events, counts = ClockMapper(settings["clocks"]), random.Random(seed), [], Counter()
    with (session/"measurements.jsonl").open() as stream:
        for index, raw in enumerate(stream):
            event = json.loads(raw)
            kind, data = event["kind"], event["data"]
            counts[kind] += 1
            divisor = drop_frame_every if kind == "frame" else drop_state_every
            if divisor and counts[kind] % divisor == 0:
                continue
            if kind == "frame":
                stamp, _ = mapper.at(data["stamp_ns"], data["clock_id"])
                delay = frame_delay_ms
            elif kind in ("vehicle_state", "imu_state"):
                stamp = data["stamp_ns"] if kind == "vehicle_state" else data["navigation"]["stamp_ns"]
                delay = state_delay_ms
            else:
                raise Unavailable("unknown_event_kind")
            events.append((timestamp(stamp)+round((delay+rng.uniform(0, jitter_ms))*1e6), index, event))
    if not events:
        raise Unavailable("empty_async_input")
    events.sort(key=lambda item: item[:2])
    start = events[0][0]
    return settings, [(arrival-start, index, event) for arrival, index, event in events]


def run_replay(session, output, *, wait_s=.5, reorder_s=.05, max_pending=32, **faults):
    settings, schedule = arrival_schedule(session, **faults)
    runner = AsyncRunner(settings, wait_s=wait_s, reorder_s=reorder_s, max_pending=max_pending)
    result, tick, step = Results(output), 0, 10_000_000
    try:
        write_json(result.path/"config.json", settings)
        write_json(result.path/"test_settings.json", dict(faults=faults, wait_s=wait_s, reorder_s=reorder_s, max_pending=max_pending))
        for arrival, _, event in schedule:
            while tick < arrival:
                result.write(runner.tick(tick))
                tick += step
            result.arrivals.write(line(dict(arrival_ns=arrival, event=event)))
            runner.submit(event, arrival)
            result.write(runner.tick(arrival))
        end = schedule[-1][0]+round((wait_s+reorder_s+.02)*1e9)
        while tick <= end:
            result.write(runner.tick(tick))
            tick += step
        result.write(runner.tick(end, final=True))
        result.finish(runner)
        return runner.summary()
    finally:
        result.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session")
    parser.add_argument("--config")
    parser.add_argument("--output")
    parser.add_argument("--ros-live", action="store_true")
    parser.add_argument("--ros-publish", action="store_true")
    parser.add_argument("--duration-s", type=float, default=30.)
    parser.add_argument("--wait-s", type=float, default=.5)
    parser.add_argument("--reorder-s", type=float, default=.05)
    parser.add_argument("--max-pending", type=int, default=32)
    parser.add_argument("--frame-delay-ms", type=float, default=20.)
    parser.add_argument("--state-delay-ms", type=float, default=80.)
    parser.add_argument("--jitter-ms", type=float, default=0.)
    parser.add_argument("--drop-state-every", type=int, default=0)
    parser.add_argument("--drop-frame-every", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--require-observations", action="store_true")
    args, ros_args = parser.parse_known_args()
    if ros_args and (not (args.ros_live or args.ros_publish) or ros_args[0] != "--ros-args"):
        parser.error("unrecognized arguments: " + " ".join(ros_args))
    if args.ros_live and args.ros_publish:
        parser.error("choose listen or publish mode")
    faults = {key: getattr(args, key) for key in ("frame_delay_ms", "state_delay_ms", "jitter_ms", "drop_state_every", "drop_frame_every", "seed")}
    if args.ros_live or args.ros_publish:
        from .adapters.async_ros import run
        summary = run(args, ros_args, faults)
    else:
        if not args.session or not args.output:
            parser.error("offline replay requires --session and a new --output directory")
        summary = run_replay(args.session, args.output, wait_s=args.wait_s, reorder_s=args.reorder_s,
                             max_pending=args.max_pending, **faults)
    print(json.dumps(summary, indent=2))
    if args.require_observations and summary.get("counts", {}).get("observations", 0) == 0:
        raise SystemExit("No usable observations; inspect diagnostics and upstream contracts")


if __name__ == "__main__":
    main()
