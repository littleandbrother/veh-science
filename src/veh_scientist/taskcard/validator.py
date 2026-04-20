"""Task card validation helpers for engineering and discovery workflows."""

from __future__ import annotations

from veh_scientist.interfaces.schemas import DiscoverTaskCard, TaskCard

_SUPPORTED_MECHANISMS = {"truncation_resonance"}
_SUPPORTED_TOOLS = {"python", "matlab", "comsol", "sympy", "manual", "llm"}


def _validate_engineering_task_card(card: TaskCard) -> list[str]:
    issues: list[str] = []
    if not card.task_id or not card.task_id.strip():
        issues.append("task_id is required and must be non-empty")

    exc = card.excitation
    if exc.amplitude <= 0:
        issues.append(f"excitation.amplitude must be > 0, got {exc.amplitude}")
    if exc.type not in ("base_acceleration", "base_displacement", "force"):
        issues.append(f"excitation.type invalid: {exc.type}")

    ft = card.frequency_target
    if ft.band_of_interest[0] >= ft.band_of_interest[1]:
        issues.append(
            f"frequency_target.band_of_interest lower >= upper: {ft.band_of_interest}"
        )
    if ft.band_of_interest[0] <= 0:
        issues.append("frequency_target.band_of_interest lower must be > 0")

    sup = card.suppression_requirements
    if sup.max_allowed_transmission_dB > 0:
        issues.append(
            f"suppression max_allowed_transmission should be <= 0 dB, got {sup.max_allowed_transmission_dB}"
        )

    harv = card.harvesting_requirements
    if harv.target_output not in ("power", "current", "voltage"):
        issues.append(f"harvesting.target_output invalid: {harv.target_output}")
    if harv.load_topology not in ("resistive", "resistive_rectified", "capacitive_storage"):
        issues.append(f"harvesting.load_topology invalid: {harv.load_topology}")
    if harv.minimum_output is not None and harv.minimum_output < 0:
        issues.append("harvesting.minimum_output must be >= 0 when provided")

    if card.mechanism_preference not in _SUPPORTED_MECHANISMS:
        issues.append(
            f"mechanism_preference '{card.mechanism_preference}' not supported. V1 supports: {sorted(_SUPPORTED_MECHANISMS)}"
        )
    return issues


def validate_discover_task_card(card: DiscoverTaskCard) -> list[str]:
    issues: list[str] = []
    if not card.task_id or not card.task_id.strip():
        issues.append("task_id is required and must be non-empty")
    if card.discovery_mode not in {"replay", "discover", "hybrid"}:
        issues.append(f"discovery_mode invalid: {card.discovery_mode}")
    if card.mechanism_focus not in _SUPPORTED_MECHANISMS:
        issues.append(
            f"mechanism_focus '{card.mechanism_focus}' not supported. V1 supports: {sorted(_SUPPORTED_MECHANISMS)}"
        )
    if not card.source_corpus:
        issues.append("source_corpus must include at least one document")
    if card.source_corpus and not any(doc.role == "target_paper" for doc in card.source_corpus):
        issues.append("source_corpus must include exactly at least one target_paper document")
    if not card.milestones:
        issues.append("milestones must not be empty")
    if not card.target_outcomes:
        issues.append("target_outcomes must not be empty")
    if not card.required_artifacts:
        issues.append("required_artifacts must not be empty")

    unknown_tools = sorted(set(card.allowed_tools) - _SUPPORTED_TOOLS)
    if unknown_tools:
        issues.append(f"allowed_tools contain unsupported entries: {unknown_tools}")

    for doc in card.source_corpus:
        if not doc.title.strip():
            issues.append(f"source_corpus document {doc.document_id} missing title")
        if not doc.path.strip():
            issues.append(f"source_corpus document '{doc.title or doc.document_id}' missing path")

    if card.engineering_task is not None:
        issues.extend(f"engineering_task.{issue}" for issue in _validate_engineering_task_card(card.engineering_task))
    return issues


def validate_task_card(card: TaskCard | DiscoverTaskCard) -> list[str]:
    if isinstance(card, DiscoverTaskCard):
        return validate_discover_task_card(card)
    return _validate_engineering_task_card(card)
