"""Integration constants."""

DOMAIN = "fermax_lynx"
PLATFORMS = ["sensor", "binary_sensor", "event", "camera", "button"]
EVENT_KINDS = [
    "incoming",
    "outgoing",
    "call_ended",
    "open_manual",
    "open_auto",
    "open_unknown",
    "open_denied",
    "control_failed",
]
