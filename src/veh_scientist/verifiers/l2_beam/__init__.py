"""
L2 Beam Verifier: Timoshenko beam Transfer Matrix Method (TMM).

Phase 1 implementation:
  Step 1a: tmm.py         - Single-layer Timoshenko transfer matrix T(L,ω)
  Step 1b: dispersion.py  - Unit cell transfer matrix + Bloch dispersion
  Step 1c: beam_analysis.py - Finite beam TR identification + forced response
"""

from .tmm import (
    timo_layer_transfer_matrix,
    MaterialProperties,
    BeamGeometry,
)
from .dispersion import (
    compute_beam_dispersion,
    compute_beam_bandgaps,
    BeamBandgapResult,
)
from .beam_analysis import (
    BeamForcedResponseResult,
    beam_frequency_sweep,
    BeamHarvestingMetrics,
    compute_beam_harvesting_metrics,
)

__all__ = [
    "timo_layer_transfer_matrix",
    "MaterialProperties",
    "BeamGeometry",
    "compute_beam_dispersion",
    "compute_beam_bandgaps",
    "BeamBandgapResult",
    "BeamForcedResponseResult",
    "beam_frequency_sweep",
    "BeamHarvestingMetrics",
    "compute_beam_harvesting_metrics",
]
