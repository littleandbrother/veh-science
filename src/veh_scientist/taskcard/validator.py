"""Task Card Validator.

A task card is valid only if the objective is explicit, constraints are
explicit or defaulted with traceable assumptions, units are normalized,
and ambiguity is tagged rather than hidden.
"""

from __future__ import annotations

from veh_scientist.interfaces.schemas import TaskCard


def validate_task_card(card: TaskCard) -> list[str]:
    """Validate a task card and return a list of issues.

    Returns
    -------
    list[str]
        Empty list if valid; otherwise, list of issue descriptions.
    """
    issues: list[str] = []

    # Task ID
    if not card.task_id or not card.task_id.strip():
        issues.append("task_id is required and must be non-empty")

    # Excitation
    exc = card.excitation
    if exc.amplitude <= 0:
        issues.append(f"excitation.amplitude must be > 0, got {exc.amplitude}")
    if exc.type not in ("base_acceleration", "base_displacement", "force"):
        issues.append(f"excitation.type invalid: {exc.type}")

    # Frequency target
    ft = card.frequency_target
    if ft.band_of_interest[0] >= ft.band_of_interest[1]:
        issues.append(
            f"frequency_target.band_of_interest lower >= upper: {ft.band_of_interest}"
        )
    if ft.band_of_interest[0] <= 0:
        issues.append("frequency_target.band_of_interest lower must be > 0")

    # Suppression
    sup = card.suppression_requirements
    if sup.max_allowed_transmission_dB > 0:
        issues.append(
            f"suppression max_allowed_transmission should be <= 0 dB, "
            f"got {sup.max_allowed_transmission_dB}"
        )

    # Harvesting target
    harv = card.harvesting_requirements
    if harv.target_output not in ("power", "current", "voltage"):
        issues.append(f"harvesting.target_output invalid: {harv.target_output}")
    if harv.load_topology not in ("resistive", "resistive_rectified", "capacitive_storage"):
        issues.append(f"harvesting.load_topology invalid: {harv.load_topology}")
    if harv.minimum_output is not None and harv.minimum_output < 0:
        issues.append("harvesting.minimum_output must be >= 0 when provided")

    # Mechanism preference
    supported_mechanisms = ["truncation_resonance"]
    if card.mechanism_preference not in supported_mechanisms:
        issues.append(
            f"mechanism_preference '{card.mechanism_preference}' not supported. "
            f"V1 supports: {supported_mechanisms}"
        )

    return issues
