"""Pure acceptance rules for the read-only cross-container boundary probe."""

REQUIRED_READY = {
    "adapter/process_liveness",
    "camera_adapter/camera_0/source_readiness",
    "mavros_adapter/source_readiness",
    "mavros_adapter/fcu_readiness",
}
PLACEHOLDER = "maritime/preimplementation_placeholder"
MISSION = "adapter/mission_readiness"
EXPECTED_FRAMES = {
    ("base_link", "camera_0_link"),
    ("camera_0_link", "camera_0_optical_frame"),
}
ALLOWED_FRAMES = EXPECTED_FRAMES | {
    ("map", "map_ned"), ("odom", "odom_ned"), ("base_link", "base_link_frd"),
}


def diagnostic_level(level):
    """Normalize ROS byte fields and integer fixtures to the same severity."""
    if isinstance(level, bytes):
        if len(level) != 1:
            raise ValueError("diagnostic severity must contain exactly one byte")
        return level[0]
    return int(level)


def validate_evidence(diagnostics, frames, placeholder_publishers, placeholder_subscribers, placeholder_clients):
    """Reject readiness confusion and command capability using observed evidence.

    diagnostics maps status names to (level, reason, key/value map). Caller
    enforces arrival freshness independently; cached status is not liveness.
    """
    for name in REQUIRED_READY:
        assert name in diagnostics, f"missing readiness evidence: {name}"
        level, reason, values = diagnostics[name]
        assert level == 0 and values.get("source_ready") == "true", f"unready: {name}: level={level}, reason={reason}, evidence={values}"
    assert MISSION in diagnostics, "missing Adapter mission policy diagnostic"
    level, reason, values = diagnostics[MISSION]
    assert level != 0 and reason == "mission_policy_unavailable", "Adapter claims mission readiness"
    assert values.get("source_ready") == "false", "Adapter claims mission readiness"
    assert PLACEHOLDER in diagnostics, "missing placeholder diagnostic"
    level, reason, values = diagnostics[PLACEHOLDER]
    assert level == 1 and reason == "preimplementation_placeholder", "placeholder identity mismatch"
    for key, expected in {
        "adapter_environment": "simulation", "placeholder_active": "true",
        "mission_ready": "false", "vehicle_commands_permitted": "false",
    }.items():
        assert values.get(key) == expected, f"unsafe placeholder state: {key}"
    assert EXPECTED_FRAMES <= frames, f"missing camera TF: {frames}"
    assert frames <= ALLOWED_FRAMES, f"truth or pose leaked to shared TF: {frames}"
    assert set(placeholder_publishers) <= {"/diagnostics", "/rosout", "/parameter_events"}, "placeholder has command publisher"
    assert not placeholder_subscribers, "placeholder consumes application/truth inputs"
    assert not placeholder_clients, "placeholder has command client"
