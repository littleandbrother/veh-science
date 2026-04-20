"""MATLAB reference wrapper for the continuous periodic beam model."""

from .periodic_beam_matlab import (
    PeriodicBeamMatlabConfig,
    run_periodic_beam_matlab,
)

__all__ = [
    "PeriodicBeamMatlabConfig",
    "run_periodic_beam_matlab",
]
