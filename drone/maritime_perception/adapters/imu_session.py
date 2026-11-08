"""Join recorded IMU samples to exact-time navigation for standard pipeline replay."""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from ..replay import line, write_json
from ..validation import Unavailable, load_json, timestamp
from .imu_formatter import ImuSample
from .ros_conversion import imu_to_state


def _json(raw):
    return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(Unavailable("nonfinite_json")))


def samples(path):
    previous = -1
    with Path(path).open() as stream:
        for raw in stream:
            sample = ImuSample.from_record(_json(raw))
            if sample.stamp_ns <= previous:
                raise Unavailable("unordered_or_duplicate_imu")
            previous = sample.stamp_ns
            yield sample


def integrate_session(session, imu_path, contract_path, output):
    """Offline exact join; reject missing data rather than reuse a nearby/latest IMU.

    Retain original navigation pose covariances ONLY when their externally verified
    model describes the combined IMU/navigation estimate. No new fusion runs here.
    """
    session, imu_path, contract_path, output = map(Path, (session, imu_path, contract_path, output))
    if output.exists():
        raise Unavailable("output_directory_must_be_new")
    config, contract = load_json(session/"config.json"), load_json(contract_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Complete validation before publishing a usable session directory.
    with tempfile.TemporaryDirectory(prefix="imu-join-", dir=output.parent) as temporary:
        stage = Path(temporary)/"session"
        stage.mkdir()
        count, previous = 0, -1
        iterator = samples(imu_path)
        sample = next(iterator, None)
        with (session/"measurements.jsonl").open() as source, (stage/"measurements.jsonl").open("w") as target:
            for raw in source:
                event = _json(raw)
                if set(event) != {"kind", "data"}:
                    raise Unavailable("invalid_event_envelope")
                if event["kind"] == "vehicle_state":
                    navigation = event["data"]
                    stamp = timestamp(navigation["stamp_ns"])
                    if stamp <= previous:
                        raise Unavailable("unordered_navigation")
                    previous = stamp
                    while sample is not None and sample.stamp_ns < stamp:
                        sample = next(iterator, None)
                    if sample is None or sample.stamp_ns != stamp:
                        raise Unavailable("imu_navigation_time_mismatch")
                    imu_to_state(sample, navigation, **contract)
                    event = {"kind": "imu_state", "data": {"imu": sample.to_record(),
                              "navigation": navigation, "contract": contract}}
                    count += 1
                elif event["kind"] != "frame":
                    raise Unavailable("unsupported_navigation_session_event")
                target.write(line(event))
        for _ in iterator:
            pass  # Validate remaining samples, including duplicate/out-of-order tails.
        if count == 0:
            raise Unavailable("navigation_states_required")
        provenance = {}
        for name, path in (("navigation_config", session/"config.json"),
                           ("navigation_measurements", session/"measurements.jsonl"),
                           ("imu", imu_path), ("contract", contract_path)):
            with path.open("rb") as stream:
                provenance[name + "_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        config["imu_integration"] = dict(version=1, alignment="exact_stamp_only", state_count=count, **provenance)
        write_json(stage/"config.json", config)
        shutil.copyfile(imu_path, stage/"imu_samples.jsonl")
        # Exclusive mkdir prevents replacing a concurrently created recording.
        output.mkdir(exist_ok=False)
        for path in stage.iterdir():
            shutil.move(str(path), output/path.name)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("session", "imu", "contract", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    print(f"Integrated {integrate_session(args.session, args.imu, args.contract, args.output)} IMU/navigation states")


if __name__ == "__main__":
    main()
