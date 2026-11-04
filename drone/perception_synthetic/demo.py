"""Explicitly selected synthetic generator -> production replay -> withheld evaluation."""
import argparse
import json
from pathlib import Path

from maritime_perception.replay import replay_session, write_json
from maritime_perception.validation import Unavailable

from .evaluate import evaluate
from .generator import generate, load_scenario


def run(scenario, output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise Unavailable("output_directory_must_be_empty")
    generate(scenario, output/"session")
    replay_session(output/"session", output/"result")
    summary = evaluate(output/"session", output/"result")
    write_json(output/"evaluation.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, choices=["synthetic"])
    parser.add_argument("--scenario", required=True, help="analytic, stationary, or explicit scenario JSON path")
    parser.add_argument("--output", required=True, help="new/empty output directory")
    args = parser.parse_args()
    print(json.dumps(run(load_scenario(args.scenario), args.output), indent=2))


if __name__ == "__main__":
    main()
