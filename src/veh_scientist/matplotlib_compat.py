"""Matplotlib backend helpers for headless artifact generation."""

from __future__ import annotations

import os


def configure_headless_matplotlib() -> str:
    """Force a non-interactive backend suitable for worker threads."""
    os.environ.setdefault("MPLBACKEND", "Agg")

    import matplotlib

    backend = str(matplotlib.get_backend())
    if backend.lower() != "agg":
        matplotlib.use("Agg", force=True)
        backend = str(matplotlib.get_backend())
    return backend
