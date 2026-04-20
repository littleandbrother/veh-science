"""Task card parsing helpers for engineering and discovery workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml

    _HAS_YAML = True
except ImportError:  # pragma: no cover - optional dependency
    _HAS_YAML = False

from veh_scientist.interfaces.schemas import (
    BaselineSpec,
    CorpusDocument,
    DiscoverTaskCard,
    EnvelopeConstraints,
    ExcitationSpec,
    FrequencyTarget,
    HarvestingSpec,
    L3Anchor,
    SuppressionSpec,
    TaskCard,
)

TaskCardLike = TaskCard | DiscoverTaskCard


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _string_tuple(value: Any, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _load_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        if not _HAS_YAML:
            raise ImportError(
                f"pyyaml is required to parse {path.name}. Install: pip install pyyaml"
            )
        return yaml.safe_load(text)
    if path.suffix == ".json":
        return json.loads(text)
    if _HAS_YAML:
        return yaml.safe_load(text)
    return json.loads(text)


def _load_mapping(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(source, dict):
        data = source
    elif isinstance(source, Path) or (isinstance(source, str) and Path(source).exists()):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Task card file not found: {path}")
        data = _load_file(path)
    else:
        try:
            data = json.loads(source)
        except json.JSONDecodeError:
            if not _HAS_YAML:
                raise ValueError(
                    "Could not parse task card string. Provide JSON or install pyyaml for YAML support."
                )
            data = yaml.safe_load(source)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping, got {type(data).__name__}")
    return data


def parse_task_card(source: str | Path | dict[str, Any]) -> TaskCardLike:
    """Parse a standard TaskCard or a DiscoverTaskCard.

    Discovery cards are detected when ``task_type: discover`` is present or
    when ``source_corpus`` is provided.
    """

    data = _load_mapping(source)
    if data.get("task_type") == "discover" or data.get("source_corpus") is not None:
        return _build_discover_task_card(data)
    return _build_task_card(data)


def parse_discover_task_card(source: str | Path | dict[str, Any]) -> DiscoverTaskCard:
    """Parse a discovery/replay task card explicitly."""
    return _build_discover_task_card(_load_mapping(source))


def _build_task_card(data: dict[str, Any]) -> TaskCard:
    task_id = data.get("task_id", "task-001")
    description = data.get("description", "")

    exc_data = data.get("excitation", {})
    excitation = ExcitationSpec(
        type=exc_data.get("type", "base_acceleration"),
        waveform=exc_data.get("waveform", "harmonic"),
        amplitude=float(exc_data.get("amplitude", 0.5)),
        amplitude_unit=exc_data.get("amplitude_unit", "g"),
        spectrum=exc_data.get("spectrum"),
    )

    ft_data = data.get("frequency_target", {})
    band = ft_data.get("band_of_interest", [300.0, 1000.0])
    freq_target = FrequencyTarget(
        band_of_interest=tuple(float(v) for v in band),
        primary_target_frequency=_optional_float(ft_data.get("primary_target_frequency")),
    )

    sup_data = data.get("suppression_requirements", {})
    suppression = SuppressionSpec(
        suppression_metric=sup_data.get("suppression_metric", "span_wise_transmission"),
        suppression_location=sup_data.get("suppression_location", "downstream of cell N"),
        max_allowed_transmission_dB=float(
            sup_data.get(
                "max_allowed_transmission_dB",
                sup_data.get("max_allowed_transmission", -10.0),
            )
        ),
        suppression_bandwidth=(
            tuple(float(v) for v in sup_data["suppression_bandwidth"])
            if sup_data.get("suppression_bandwidth") is not None
            else None
        ),
        tr_frequency_exception=bool(sup_data.get("tr_frequency_exception", True)),
    )

    harv_data = data.get("harvesting_requirements", {})
    harvesting = HarvestingSpec(
        target_output=harv_data.get("target_output", "power"),
        output_type=harv_data.get("output_type", "peak"),
        minimum_output=_optional_float(harv_data.get("minimum_output")),
        minimum_output_unit=harv_data.get("minimum_output_unit", "mW"),
        load_topology=harv_data.get("load_topology", "resistive"),
        load_value=_optional_float(harv_data.get("load_value")),
    )

    env_data = data.get("envelope_constraints", {})
    envelope = EnvelopeConstraints(
        total_mass_kg=_optional_float(env_data.get("total_mass_kg")),
        total_length_m=_optional_float(env_data.get("total_length_m")),
        max_cross_section_m2=_optional_float(env_data.get("max_cross_section_m2")),
        piezo_volume_m3=_optional_float(env_data.get("piezo_volume_m3")),
        piezo_material=env_data.get("piezo_material", "PZT-5H"),
    )

    bl_data = data.get("comparison_baselines", {})
    baselines = BaselineSpec(
        mechanism_baseline=bl_data.get("mechanism_baseline", "same_structure_delta_1_PB1"),
        engineering_baseline=bl_data.get("engineering_baseline", "conventional_uniform_cantilever"),
        constraints_locked=tuple(
            bl_data.get(
                "constraints_locked",
                (
                    "total_mass",
                    "total_length",
                    "piezo_volume",
                    "excitation",
                    "load_topology",
                    "target_frequency_window",
                ),
            )
        ),
    )

    return TaskCard(
        task_id=task_id,
        description=description,
        excitation=excitation,
        frequency_target=freq_target,
        suppression_requirements=suppression,
        harvesting_requirements=harvesting,
        envelope_constraints=envelope,
        comparison_baselines=baselines,
        mechanism_preference=data.get("mechanism_preference", "truncation_resonance"),
    )


def _build_corpus_document(raw: Any) -> CorpusDocument:
    if isinstance(raw, str):
        path = raw
        title = Path(raw).stem or raw
        return CorpusDocument(title=title, path=path)
    if not isinstance(raw, dict):
        raise ValueError(f"Each source_corpus entry must be a mapping or string, got {type(raw).__name__}")
    return CorpusDocument(
        document_id=str(raw.get("document_id", "")) or CorpusDocument().document_id,
        title=str(raw.get("title", "")),
        path=str(raw.get("path", "")),
        role=str(raw.get("role", "reference_paper")),
        source_type=str(raw.get("source_type", "pdf")),
        summary=str(raw.get("summary", "")),
        key_questions=_string_tuple(raw.get("key_questions")),
        seed_claims=_string_tuple(raw.get("seed_claims")),
        tags=_string_tuple(raw.get("tags")),
    )



def _build_l3_anchor(raw: Any) -> L3Anchor:
    if not isinstance(raw, dict):
        raise ValueError(f"Each l3_anchors entry must be a mapping, got {type(raw).__name__}")
    stopband = raw.get("stopband_hz")
    stopband_tuple = None
    if stopband is not None:
        stopband_tuple = tuple(float(v) for v in stopband)
    return L3Anchor(
        anchor_id=str(raw.get("anchor_id", "")) or L3Anchor().anchor_id,
        label=str(raw.get("label", "TR")),
        frequency_hz=float(raw.get("frequency_hz", 0.0)),
        band_index=int(raw["band_index"]) if raw.get("band_index") is not None else None,
        stopband_hz=stopband_tuple,
        target_power_mw=_optional_float(raw.get("target_power_mw")),
        target_transmission_db=_optional_float(raw.get("target_transmission_db")),
        target_pef=_optional_float(raw.get("target_pef")),
        note=str(raw.get("note", "")),
    )

def _build_discover_task_card(data: dict[str, Any]) -> DiscoverTaskCard:
    engineering_task = None
    if data.get("engineering_task") is not None:
        engineering_task = _build_task_card(data["engineering_task"])

    corpus = tuple(_build_corpus_document(item) for item in data.get("source_corpus", ()))
    anchors = tuple(_build_l3_anchor(item) for item in data.get("l3_anchors", ()))
    milestones = _string_tuple(
        data.get(
            "milestones",
            (
                "claim_graph",
                "hypothesis_ladder",
                "derivation_cards",
                "experiment_ladder",
                "gap_ranking",
                "discovery_report",
            ),
        )
    )
    target_outcomes = _string_tuple(
        data.get(
            "target_outcomes",
            (
                "claim_graph.json",
                "hypothesis_ladder.md",
                "derivation_cards.md",
                "gap_ranking.json",
                "discovery_report.md",
            ),
        )
    )
    required_artifacts = _string_tuple(
        data.get(
            "required_artifacts",
            (
                "claim_graph.json",
                "derivation_report.md",
                "gap_ranking.json",
                "evidence_matrix.json",
            ),
        )
    )

    return DiscoverTaskCard(
        task_id=str(data.get("task_id", "discover-001")),
        description=str(data.get("description", "")),
        discovery_mode=str(data.get("discovery_mode", "replay")),
        mechanism_focus=str(data.get("mechanism_focus", data.get("mechanism_preference", "truncation_resonance"))),
        research_question=str(data.get("research_question", "")),
        source_corpus=corpus,
        milestones=milestones,
        target_outcomes=target_outcomes,
        allowed_tools=_string_tuple(data.get("allowed_tools"), ("python", "matlab", "comsol", "sympy")),
        required_artifacts=required_artifacts,
        replay_notes=_string_tuple(data.get("replay_notes")),
        l3_anchors=anchors,
        engineering_task=engineering_task,
    )
