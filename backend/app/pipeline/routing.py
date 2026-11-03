from __future__ import annotations

from ..analysis.need_detection import THRESHOLDS

# Need-detection label -> owning department.
DEPARTMENT_BY_NEED = {
    "healthcare": "Healthcare",
    "municipal": "Public Municipal",
    "law": "Law & Order",
    "tourism": "Tourism",
}
# Confirmed disaster with no need clearing its threshold.
DEFAULT_DEPARTMENT = "Disaster Management"


def route_department(needs: dict[str, float]) -> tuple[str, list[str]]:
    """Pick the owning department for a situation from its (cluster-averaged)
    need probabilities. Returns (department, active_needs) where active_needs
    are the labels clearing their per-label threshold, strongest first."""
    active = sorted(
        (name for name, prob in needs.items() if prob >= THRESHOLDS.get(name, 0.5)),
        key=lambda name: needs[name],
        reverse=True,
    )
    if not active:
        return DEFAULT_DEPARTMENT, []
    return DEPARTMENT_BY_NEED.get(active[0], DEFAULT_DEPARTMENT), active
