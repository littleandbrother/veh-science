"""Mechanism Screening Layer.

Blueprint §5.5: Reject candidates that do not satisfy mechanism preconditions
before expensive evaluation.
"""

from .gates import (
    gate_1_bandgap_existence,
    gate_2_boundary_asymmetry,
    gate_3_tr_in_bandgap,
    gate_4_energy_localization,
    gate_5_topological_classification,
    gate_6_suppression_compatibility,
)
from .screening import MechanismScreener

__all__ = [
    "MechanismScreener",
    "gate_1_bandgap_existence",
    "gate_2_boundary_asymmetry",
    "gate_3_tr_in_bandgap",
    "gate_4_energy_localization",
    "gate_5_topological_classification",
    "gate_6_suppression_compatibility",
]
