"""Fail-closed policy for the temporary simulation bootstrap."""

SIMULATION_ENVIRONMENT = "simulation"
PLACEHOLDER_OPT_IN = "1"


def validate_environment(adapter_environment: str | None, placeholder_opt_in: str | None) -> str | None:
    """Return a stable rejection reason, or ``None`` for the explicit opt-in."""
    if adapter_environment != SIMULATION_ENVIRONMENT:
        return "adapter_environment_not_simulation"
    if placeholder_opt_in != PLACEHOLDER_OPT_IN:
        return "placeholder_opt_in_missing"
    return None
