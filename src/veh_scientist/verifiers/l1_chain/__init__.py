"""L1 Chain Verifier: Diatomic spring-mass chain model.

Step 0a: dispersion.py     - Infinite chain dispersion relation + bandgap
Step 0b: finite_chain.py   - Finite chain eigenfrequencies + TR identification
Step 0c+0d: piezo_harvesting.py - Mode shapes, energy, piezo coupling, PEF
"""

from .dispersion import (
    BandgapResult,
    compute_bandgap,
    dimensional_frequency,
    dispersion_relation,
)
from .finite_chain import (
    FiniteChainResult,
    analyze_finite_chain,
    build_dynamic_stiffness,
    find_eigenfrequencies,
)
from .piezo_harvesting import (
    ForcedResponseResult,
    HarvestingMetrics,
    ModeShapeResult,
    compute_harvesting_metrics,
    compute_mode_shape_energy,
    frequency_sweep,
)

__all__ = [
    "BandgapResult",
    "compute_bandgap",
    "dimensional_frequency",
    "dispersion_relation",
    "FiniteChainResult",
    "analyze_finite_chain",
    "build_dynamic_stiffness",
    "find_eigenfrequencies",
    "ForcedResponseResult",
    "HarvestingMetrics",
    "ModeShapeResult",
    "compute_harvesting_metrics",
    "compute_mode_shape_energy",
    "frequency_sweep",
]
