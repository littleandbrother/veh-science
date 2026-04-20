"""Core interface schemas for the VEH Scientist system.

These dataclasses define the typed contracts between all modules.
Every module reads/writes only these structures at its boundaries.

Blueprint references:
    - §5.1   TaskCard
    - §5.4   CandidateDesignFamily
    - §5.5   MechanismScreenResult, GateResult
    - §5.7   VerificationResult
    - §5.8   CriticDecision
    - §5.10  MemoryRecord
    - §8.5   Interface Definition Rules
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_id(prefix: str = "") -> str:
    """Generate a short unique ID with optional prefix."""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# §5.1  Task Card Layer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExcitationSpec:
    """Excitation conditions for the task."""
    type: Literal["base_acceleration", "base_displacement", "force"] = "base_acceleration"
    waveform: Literal["harmonic", "narrowband_random", "broadband_random"] = "harmonic"
    amplitude: float = 0.5          # fixed amplitude: g for acceleration, mm for displacement
    amplitude_unit: str = "g"
    spectrum: str | None = None     # file path or inline for random excitation


@dataclass(frozen=True)
class FrequencyTarget:
    """Target frequency range."""
    band_of_interest: tuple[float, float] = (300.0, 1000.0)   # Hz
    primary_target_frequency: float | None = None               # Hz, None = auto


@dataclass(frozen=True)
class SuppressionSpec:
    """Suppression requirements."""
    suppression_metric: str = "span_wise_transmission"
    suppression_location: str = "downstream of cell N"
    max_allowed_transmission_dB: float = -10.0
    suppression_bandwidth: tuple[float, float] | None = None    # Hz
    tr_frequency_exception: bool = True


@dataclass(frozen=True)
class HarvestingSpec:
    """Harvesting requirements."""
    target_output: Literal["power", "current", "voltage"] = "power"
    output_type: Literal["peak", "rms", "time_averaged"] = "peak"
    minimum_output: float | None = None                          # mW
    minimum_output_unit: str = "mW"
    load_topology: Literal["resistive", "resistive_rectified", "capacitive_storage"] = "resistive"
    load_value: float | None = None                              # Ohm, None = optimize


@dataclass(frozen=True)
class EnvelopeConstraints:
    """Physical envelope constraints."""
    total_mass_kg: float | None = None
    total_length_m: float | None = None
    max_cross_section_m2: float | None = None
    piezo_volume_m3: float | None = None
    piezo_material: str = "PZT-5H"


@dataclass(frozen=True)
class BaselineSpec:
    """Comparison baseline definitions."""
    mechanism_baseline: str = "same_structure_delta_1_PB1"
    engineering_baseline: str = "conventional_uniform_cantilever"
    constraints_locked: tuple[str, ...] = (
        "total_mass", "total_length", "piezo_volume",
        "excitation", "load_topology", "target_frequency_window",
    )


@dataclass(frozen=True)
class TaskCard:
    """§5.1 — System entry point.

    A normalized, machine-readable design problem specification.
    A task card is valid only if the objective is explicit, constraints are
    explicit or defaulted with traceable assumptions, and ambiguity is tagged.
    """
    task_id: str
    description: str = ""
    excitation: ExcitationSpec = field(default_factory=ExcitationSpec)
    frequency_target: FrequencyTarget = field(default_factory=FrequencyTarget)
    suppression_requirements: SuppressionSpec = field(default_factory=SuppressionSpec)
    harvesting_requirements: HarvestingSpec = field(default_factory=HarvestingSpec)
    envelope_constraints: EnvelopeConstraints = field(default_factory=EnvelopeConstraints)
    comparison_baselines: BaselineSpec = field(default_factory=BaselineSpec)
    mechanism_preference: str = "truncation_resonance"
    schema_version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# §5.4  Candidate Design Family
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StructuralParams:
    """Structural parameterization of a candidate design.

    Corresponds to the four-level design parameter hierarchy (§2.4.3):
        Level 1 — Switch:  delta
        Level 2 — Tuners:  alpha, beta
        Level 4 — Q-Amp:   N
    """
    alpha: float                    # mass ratio m_b / m_a
    beta: float                     # stiffness ratio k_b / k_a
    delta: float                    # boundary asymmetry m_{a+} / m_a
    N: int                          # number of unit cells
    material_A: str = "Aluminum"    # substrate material
    material_B: str = "Epoxy"       # contrast layer material
    boundary_condition: str = "free_clamped"


@dataclass(frozen=True)
class TransducerParams:
    """Transducer placement plan."""
    piezo_material: str = "PZT-5H"
    location: str = "cell_interface_1_2"
    coverage: str = "single_patch"
    d31: float = -274e-12           # piezoelectric strain constant (m/V)
    epsilon_33: float = 3400.0      # relative permittivity


@dataclass(frozen=True)
class ElectricalParams:
    """Electrical interface specification.

    Corresponds to Level 3 — Matchers (§2.4.3):
        kappa2 = theta^2 / (k_b * C_p)
        epsilon = 1 / (R * C_p * omega_b)
    """
    kappa2: float                   # coupling factor
    epsilon: float | None = None    # electrical damping ratio, None = auto-match
    load_resistance: float | None = None  # Ohm, None = optimize
    load_topology: str = "resistive"
    C_p: float | None = None        # piezo capacitance (F)


@dataclass
class CandidateDesignFamily:
    """§5.4 — A complete candidate with all three domains.

    A candidate family is valid only if all three domains are represented:
    structure, transducer, and electrical interface.
    """
    candidate_id: str = field(default_factory=lambda: _gen_id("C-"))
    round_id: int = 0
    source: str = "brainstorm"      # "memory" | "paper" | "brainstorm" | "llm:<model>"

    # Three mandatory domains
    structure: StructuralParams = field(default_factory=lambda: StructuralParams(
        alpha=1.0, beta=0.5, delta=1.5, N=10
    ))
    transducer: TransducerParams = field(default_factory=TransducerParams)
    electrical: ElectricalParams = field(default_factory=lambda: ElectricalParams(kappa2=0.05))

    mechanism_hypothesis: str = ""
    assumptions: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check that all three domains are present and consistent."""
        return (
            self.structure is not None
            and self.transducer is not None
            and self.electrical is not None
            and self.structure.alpha > 0
            and self.structure.beta > 0
            and self.structure.N >= 5
        )


# ---------------------------------------------------------------------------
# §5.5  Mechanism Screening Layer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateResult:
    """Result of a single screening gate."""
    gate_id: int                    # 1-6
    gate_name: str
    passed: bool
    value: float | None = None
    threshold: float | None = None
    message: str = ""


@dataclass
class MechanismScreenResult:
    """§5.5 — Gate-by-gate screening verdict."""
    candidate_id: str
    verdict: Literal["pass", "revise", "reject"] = "reject"
    gates: list[GateResult] = field(default_factory=list)
    tr_frequency: float | None = None
    eta: float | None = None
    revision_hints: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# §5.7  Multi-Fidelity Verification Layer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricValue:
    """A single named metric with status classification."""
    label: str
    value: float | str
    unit: str = ""
    status: Literal["pass", "warn", "fail"] = "pass"


@dataclass
class VerificationResult:
    """§5.7 — Multi-fidelity verification output."""
    candidate_id: str
    tier: Literal["L1", "L2", "L3"]
    status: Literal["pass", "partial", "fail", "missing"] = "missing"
    metrics: list[MetricValue] = field(default_factory=list)
    details: str = ""
    log: str = ""
    runtime_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# §5.8  Critic and Decision Layer
# ---------------------------------------------------------------------------

@dataclass
class CriticDecision:
    """§5.8 — What to do next.

    A critic decision is acceptable only if it includes the decision type,
    reason, affected module, and next action.
    """
    candidate_id: str
    decision: Literal["accept", "revise", "switch_family", "abandon"] = "revise"
    reason: str = ""
    affected_module: str = ""
    next_action: str = ""
    failure_modes_triggered: list[str] = field(default_factory=list)
    confidence: float = 0.0         # 0.0 to 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# §5.10  Persistent Memory Layer
# ---------------------------------------------------------------------------

@dataclass
class MemoryRecord:
    """§5.10 — Persistent knowledge entry.

    Memory entries must be structured, tagged, and traceable back to experiments.
    """
    memory_id: str = field(default_factory=lambda: _gen_id("M-"))
    round_id: int = 0
    category: Literal["motif", "failure", "knowledge", "rule", "strategy"] = "knowledge"
    observation: str = ""
    interpretation: str = ""
    next_step: str = ""
    tags: list[str] = field(default_factory=list)
    source_candidate_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Round-level state (used by Coordinator)
# ---------------------------------------------------------------------------

@dataclass
class RoundState:
    """Complete state of a single research round."""
    round_id: int
    task_id: str
    phase: Literal[
        "discussing", "screening", "verifying",
        "critiquing", "memorizing", "completed"
    ] = "discussing"
    candidates: list[CandidateDesignFamily] = field(default_factory=list)
    screen_results: list[MechanismScreenResult] = field(default_factory=list)
    verification_results: list[VerificationResult] = field(default_factory=list)
    critic_decisions: list[CriticDecision] = field(default_factory=list)
    memory_records: list[MemoryRecord] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    budget_used: int = 0
    budget_total: int = 6
    best_candidate_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
