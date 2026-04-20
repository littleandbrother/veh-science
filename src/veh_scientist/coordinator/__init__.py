"""Research Coordinator.

Blueprint §5.2: A top-level controller manages research direction,
budget, and strategy transitions.
"""

from .loop import ResearchLoop

__all__ = ["ResearchLoop"]
