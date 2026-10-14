import os


def require_explicit_simulation(command_capable=False):
    if os.environ.get("ADAPTER_ENVIRONMENT") != "simulation":
        raise SystemExit("refusing evaluation: ADAPTER_ENVIRONMENT must equal simulation")
    if os.environ.get("SIMULATION_EVALUATION") != "1":
        raise SystemExit("refusing evaluation: set SIMULATION_EVALUATION=1 explicitly")
    if os.path.exists("/dev/serial/by-id"):
        raise SystemExit("refusing evaluation: physical serial devices are visible")
    if command_capable and os.environ.get("FCU_URL") != "udp://:14552@":
        raise SystemExit("refusing command evaluation: FCU_URL must equal the SITL endpoint udp://:14552@")
