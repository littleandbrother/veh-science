"""
L3 COMSOL Oracle: 3D FEM validation for periodic TR beam.

Phase 4 uses COMSOL via mph to validate L1 (chain) and L2 (TMM/FEM) results.

Key design:
  - 3D periodic Timoshenko beam: N cells of Al + Epoxy
  - Piezo patch (PZT-5H) on first cell top face
  - Fixed harmonic base acceleration input
    (implemented in the wrapper as equivalent boundary displacement)
  - Direct circuit path for electrical power (not hybrid)
  - Compare bandgap, TR frequency, and power with L2 results
"""

from .periodic_beam_comsol import (
    PeriodicBeamCOMSOLConfig,
    PeriodicPiezoBeamCOMSOLOracle,
    build_and_run_periodic_beam,
)

__all__ = [
    "PeriodicBeamCOMSOLConfig",
    "PeriodicPiezoBeamCOMSOLOracle",
    "build_and_run_periodic_beam",
]
