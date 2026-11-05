"""Replay only config and measurements. No scene/truth dependency."""
import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

from .pipeline import PerceptionPipeline
from .validation import Unavailable, load_json


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n")


def line(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n"


def replay_session(session, output):
    session, output = Path(session), Path(output)
    if output.exists() and any(output.iterdir()):
        raise Unavailable("output_directory_must_be_empty")
    output.mkdir(parents=True, exist_ok=True)
    settings = load_json(session/"config.json")
    pipeline = PerceptionPipeline(settings)
    count = 0
    with (output/"reports.jsonl").open("w") as reports, (output/"observations.jsonl").open("w") as observations, (output/"replay_errors.jsonl").open("w") as errors:
        with (session/"measurements.jsonl").open() as measurements:
            for number, raw in enumerate(measurements, 1):
                try:
                    event = json.loads(raw, parse_constant=lambda v: (_ for _ in ()).throw(Unavailable("nonfinite_json")))
                    if set(event) != {"kind", "data"}:
                        raise Unavailable("invalid_event_envelope")
                    if event["kind"] == "vehicle_state":
                        pipeline.add_state(event["data"])
                    elif event["kind"] == "frame":
                        report, ledger = pipeline.process_frame(event["data"])
                        reports.write(line(report))
                        for item in ledger:
                            observations.write(line(item))
                        count += 1
                    else:
                        raise Unavailable("unknown_event_kind")
                except (Unavailable, KeyError, TypeError, ValueError) as exc:
                    errors.write(line({"line": number, "status": "rejected", "reason": str(exc)}))
    module_root = Path(__file__).parent
    manifest = {"schema": "maritime.replay_manifest", "version": 1, "report_count": count,
                "runtime": {"python": platform.python_version(),
                            "packages": {name: version(name) for name in ("numpy", "scipy", "pyproj", "opencv-python-headless", "jsonschema")}},
                "code_sha256": {str(path.relative_to(module_root)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in sorted(module_root.rglob("*.py"))},
                "inputs_sha256": {name: hashlib.sha256((session/name).read_bytes()).hexdigest()
                                  for name in ("config.json", "measurements.jsonl")},
                "outputs_sha256": {name: hashlib.sha256((output/name).read_bytes()).hexdigest()
                                   for name in ("reports.jsonl", "observations.jsonl", "replay_errors.jsonl")}}
    write_json(output/"manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(replay_session(args.session, args.output), indent=2))


if __name__ == "__main__":
    main()
