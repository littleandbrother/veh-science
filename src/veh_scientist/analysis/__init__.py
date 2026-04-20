"""Analysis helpers for objective-aligned verification."""

from .objectives import (
    OutputComparison,
    build_output_comparison,
    metric_unit_for_target,
    primary_output_value,
    primary_metric_label,
    ratio_status,
    threshold_status,
)

__all__ = [
    "OutputComparison",
    "build_output_comparison",
    "metric_unit_for_target",
    "primary_output_value",
    "primary_metric_label",
    "ratio_status",
    "threshold_status",
]
