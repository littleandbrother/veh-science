"""Critic and Decision Layer.

Blueprint §5.8: The system must explain failure rather than merely
report poor performance.
"""

from .decision import RuleBasedCritic

__all__ = ["RuleBasedCritic"]
