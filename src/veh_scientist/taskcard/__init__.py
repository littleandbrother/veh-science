"""Task Card Layer.

Blueprint §5.1: Convert vague engineering requests into structured
machine-readable design problems.
"""

from .parser import parse_task_card
from .validator import validate_task_card

__all__ = ["parse_task_card", "validate_task_card"]
