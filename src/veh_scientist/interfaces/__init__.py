"""Core interface schemas for the VEH Scientist system.

All module boundaries exchange these typed contracts.
"""

from .schemas import (
    CandidateDesignFamily,
    CriticDecision,
    ElectricalParams,
    EnvelopeConstraints,
    ExcitationSpec,
    FrequencyTarget,
    GateResult,
    HarvestingSpec,
    MemoryRecord,
    MetricValue,
    RoundState,
    StructuralParams,
    SuppressionSpec,
    TaskCard,
    TransducerParams,
    VerificationResult,
    MechanismScreenResult,
)

__all__ = [
    "CandidateDesignFamily",
    "CriticDecision",
    "ElectricalParams",
    "EnvelopeConstraints",
    "ExcitationSpec",
    "FrequencyTarget",
    "GateResult",
    "HarvestingSpec",
    "MemoryRecord",
    "MetricValue",
    "RoundState",
    "StructuralParams",
    "SuppressionSpec",
    "TaskCard",
    "TransducerParams",
    "VerificationResult",
    "MechanismScreenResult",
]
