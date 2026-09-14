import argparse


def main():
    parser = argparse.ArgumentParser(description="Simulation-only evaluation entrypoints (never launched by Adapter bringup).")
    parser.add_argument("evaluator", nargs="?", choices=("sensor_smoke", "mavros_smoke"))
    args = parser.parse_args()
    if args.evaluator:
        parser.error(f"invoke with: ros2 run blueboat_sim_evaluation {args.evaluator}")
