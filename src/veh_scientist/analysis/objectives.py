"""Objective helpers for power/current/voltage aligned evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from veh_scientist.interfaces.schemas import HarvestingSpec


RECTIFIED_AVG_FACTOR = 2.0 / math.pi
RMS_FACTOR = 1.0 / math.sqrt(2.0)


@dataclass(frozen=True)
class OutputComparison:
    """Primary-output comparison against mechanism and engineering baselines."""

    label: str
    unit: str
    tr_value: float
    mechanism_baseline_value: float
    mechanism_ratio: float
    engineering_baseline_value: float | None = None
    engineering_ratio: float | None = None


def primary_metric_label(spec: HarvestingSpec) -> str:
    """Stable metric label used by verification and critic."""
    target = spec.target_output.lower()
    return {
        "power": "PrimaryOutput(TR)",
        "current": "PrimaryOutput(TR)",
        "voltage": "PrimaryOutput(TR)",
    }[target]


def metric_unit_for_target(
    spec: HarvestingSpec,
    normalized: bool = False,
) -> str:
    """Render an output unit for the requested target."""
    if normalized:
        return "arb."
    if spec.target_output == "power":
        return spec.minimum_output_unit or "W"
    if spec.target_output == "current":
        return spec.minimum_output_unit or "A"
    return spec.minimum_output_unit or "V"


def threshold_status(
    value: float,
    threshold: float | None,
    normalized: bool = False,
) -> str:
    """Classify a value against an optional threshold."""
    if threshold is None or normalized:
        return "pass" if value > 0 else "fail"
    if value >= threshold:
        return "pass"
    if value >= 0.8 * threshold:
        return "warn"
    return "fail"


def ratio_status(value: float | None) -> str:
    """Classify a baseline ratio."""
    if value is None:
        return "warn"
    if value >= 1.0:
        return "pass"
    if value >= 0.8:
        return "warn"
    return "fail"


def build_output_comparison(
    spec: HarvestingSpec,
    *,
    normalized: bool,
    tr_voltage_peak: float,
    mechanism_voltage_peak: float,
    tr_power: float,
    mechanism_power: float,
    tr_current_peak: float,
    mechanism_current_peak: float,
    engineering_voltage_peak: float | None = None,
    engineering_power: float | None = None,
    engineering_current_peak: float | None = None,
) -> OutputComparison:
    """Build a primary-output comparison for the requested task output."""

    target = spec.target_output
    unit = metric_unit_for_target(spec, normalized=normalized)

    tr_value = primary_output_value(
        spec,
        voltage_peak=tr_voltage_peak,
        power=tr_power,
        current_peak=tr_current_peak,
    )
    mechanism_value = primary_output_value(
        spec,
        voltage_peak=mechanism_voltage_peak,
        power=mechanism_power,
        current_peak=mechanism_current_peak,
    )

    engineering_value: float | None
    if (
        engineering_voltage_peak is None
        and engineering_power is None
        and engineering_current_peak is None
    ):
        engineering_value = None
    else:
        engineering_value = primary_output_value(
            spec,
            voltage_peak=engineering_voltage_peak or 0.0,
            power=engineering_power or 0.0,
            current_peak=engineering_current_peak or 0.0,
        )

    return OutputComparison(
        label=primary_metric_label(spec),
        unit=unit,
        tr_value=tr_value,
        mechanism_baseline_value=mechanism_value,
        mechanism_ratio=_safe_ratio(tr_value, mechanism_value),
        engineering_baseline_value=engineering_value,
        engineering_ratio=_safe_ratio(tr_value, engineering_value),
    )


def primary_output_value(
    spec: HarvestingSpec,
    *,
    voltage_peak: float,
    power: float,
    current_peak: float,
) -> float:
    """Select the task's primary output in the requested output mode."""
    if spec.target_output == "power":
        return power

    if spec.target_output == "voltage":
        return _convert_signal_output(
            voltage_peak,
            output_type=spec.output_type,
            rectified=spec.load_topology in {"resistive_rectified", "capacitive_storage"},
        )

    return _convert_signal_output(
        current_peak,
        output_type=spec.output_type,
        rectified=spec.load_topology in {"resistive_rectified", "capacitive_storage"},
    )


def _convert_signal_output(
    peak_value: float,
    *,
    output_type: str,
    rectified: bool,
) -> float:
    """Convert peak voltage/current to peak/rms/time-averaged output."""
    if output_type == "peak":
        return peak_value
    if output_type == "rms":
        return peak_value * RMS_FACTOR
    if rectified:
        return peak_value * RECTIFIED_AVG_FACTOR
    return peak_value * RMS_FACTOR


def _safe_ratio(numerator: float, denominator: float | None) -> float | None:
    if denominator is None:
        return None
    if abs(denominator) < 1e-30:
        return 0.0
    return numerator / denominator
