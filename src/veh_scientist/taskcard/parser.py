"""Task Card Parser — YAML/JSON → TaskCard.

Reads a YAML or JSON file and produces a fully typed TaskCard instance.
Supports YAML (if pyyaml is installed) or JSON format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from veh_scientist.interfaces.schemas import (
    BaselineSpec,
    EnvelopeConstraints,
    ExcitationSpec,
    FrequencyTarget,
    HarvestingSpec,
    SuppressionSpec,
    TaskCard,
)


def _optional_float(value: Any) -> float | None:
    """Convert optional scalar values to float, preserving null/empty input."""
    if value is None or value == "":
        return None
    return float(value)


def _load_file(path: Path) -> dict[str, Any]:
    """Load a YAML or JSON file."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        if _HAS_YAML:
            return yaml.safe_load(text)
        else:
            raise ImportError(
                f"pyyaml is required to parse {path.name}. "
                f"Install: pip install pyyaml, or use .json format."
            )
    elif path.suffix == ".json":
        return json.loads(text)
    else:
        # Try YAML first, then JSON
        if _HAS_YAML:
            return yaml.safe_load(text)
        return json.loads(text)


def parse_task_card(source: str | Path | dict[str, Any]) -> TaskCard:
    """Parse a task card from YAML/JSON file, string, or dict.

    Parameters
    ----------
    source : str | Path | dict
        A file path (YAML or JSON), a JSON string, or an already-parsed dict.

    Returns
    -------
    TaskCard
        A fully typed task card instance.

    Raises
    ------
    ValueError
        If the source is missing required fields.
    FileNotFoundError
        If the source is a path that doesn't exist.
    """
    if isinstance(source, dict):
        data = source
    elif isinstance(source, Path) or (isinstance(source, str) and Path(source).exists()):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Task card file not found: {path}")
        data = _load_file(path)
    else:
        # Try parsing as JSON string
        try:
            data = json.loads(source)
        except json.JSONDecodeError:
            if _HAS_YAML:
                data = yaml.safe_load(source)
            else:
                raise ValueError(
                    "Could not parse task card string. "
                    "Provide JSON or install pyyaml for YAML support."
                )

    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping, got {type(data).__name__}")

    return _build_task_card(data)


def _build_task_card(data: dict[str, Any]) -> TaskCard:
    """Build a TaskCard from a parsed dict, filling defaults for missing fields."""

    task_id = data.get("task_id", "task-001")
    description = data.get("description", "")

    # Excitation
    exc_data = data.get("excitation", {})
    excitation = ExcitationSpec(
        type=exc_data.get("type", "base_acceleration"),
        waveform=exc_data.get("waveform", "harmonic"),
        amplitude=float(exc_data.get("amplitude", 0.5)),
        amplitude_unit=exc_data.get("amplitude_unit", "g"),
        spectrum=exc_data.get("spectrum"),
    )

    # Frequency target
    ft_data = data.get("frequency_target", {})
    band = ft_data.get("band_of_interest", [300.0, 1000.0])
    freq_target = FrequencyTarget(
        band_of_interest=tuple(band),
        primary_target_frequency=_optional_float(ft_data.get("primary_target_frequency")),
    )

    # Suppression
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
            tuple(sup_data["suppression_bandwidth"])
            if sup_data.get("suppression_bandwidth") is not None
            else None
        ),
        tr_frequency_exception=sup_data.get("tr_frequency_exception", True),
    )

    # Harvesting
    harv_data = data.get("harvesting_requirements", {})
    harvesting = HarvestingSpec(
        target_output=harv_data.get("target_output", "power"),
        output_type=harv_data.get("output_type", "peak"),
        minimum_output=_optional_float(harv_data.get("minimum_output")),
        minimum_output_unit=harv_data.get("minimum_output_unit", "mW"),
        load_topology=harv_data.get("load_topology", "resistive"),
        load_value=_optional_float(harv_data.get("load_value")),
    )

    # Envelope constraints
    env_data = data.get("envelope_constraints", {})
    envelope = EnvelopeConstraints(
        total_mass_kg=_optional_float(env_data.get("total_mass_kg")),
        total_length_m=_optional_float(env_data.get("total_length_m")),
        max_cross_section_m2=_optional_float(env_data.get("max_cross_section_m2")),
        piezo_volume_m3=_optional_float(env_data.get("piezo_volume_m3")),
        piezo_material=env_data.get("piezo_material", "PZT-5H"),
    )

    # Baselines
    bl_data = data.get("comparison_baselines", {})
    baselines = BaselineSpec(
        mechanism_baseline=bl_data.get("mechanism_baseline", "same_structure_delta_1_PB1"),
        engineering_baseline=bl_data.get("engineering_baseline", "conventional_uniform_cantilever"),
        constraints_locked=tuple(
            bl_data.get(
                "constraints_locked",
                (
                    "total_mass", "total_length", "piezo_volume",
                    "excitation", "load_topology", "target_frequency_window",
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
