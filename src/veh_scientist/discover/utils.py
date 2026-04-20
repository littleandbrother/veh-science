"""Utility helpers for executable discovery replay."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from veh_scientist.interfaces import DiscoveryStep


REPO_MARKERS = {"pyproject.toml", ".git"}


def repo_root(start: str | Path | None = None) -> Path:
    """Return the repository root by walking upward from *start* or this file."""

    current = Path(start or __file__).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if any((candidate / marker).exists() for marker in REPO_MARKERS):
            return candidate
    return Path.cwd()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_path(raw_path: str | Path, base_dir: str | Path | None = None) -> Path:
    """Resolve a task-card document path.

    Resolution order:
        1. absolute path
        2. relative to *base_dir*
        3. relative to cwd
        4. relative to repository root
        5. under /mnt/data by basename
    """

    candidate = Path(raw_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()

    search_roots: list[Path] = []
    if base_dir is not None:
        search_roots.append(Path(base_dir))
    search_roots.extend([Path.cwd(), repo_root()])
    basename = candidate.name

    for root in search_roots:
        probe = (root / candidate).resolve()
        if probe.exists():
            return probe
    mnt_probe = Path("/mnt/data") / basename
    if mnt_probe.exists():
        return mnt_probe.resolve()
    return candidate.resolve()


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses and paths into JSON-serializable structures."""

    if is_dataclass(value):
        return {key: to_jsonable(val) for key, val in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    return value


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(json.dumps(to_jsonable(payload), indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def write_text(path: str | Path, text: str) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(text, encoding="utf-8")
    return target


def write_csv(path: str | Path, rows: Iterable[dict[str, Any]], fieldnames: list[str] | None = None) -> Path:
    import csv

    target = Path(path)
    ensure_dir(target.parent)
    rows = list(rows)
    if not rows and fieldnames is None:
        fieldnames = []
    elif fieldnames is None:
        fieldnames = list(rows[0].keys())
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return target


def update_step_status(steps: list[DiscoveryStep], stage: str, status: str) -> list[DiscoveryStep]:
    """Return a new step list with the matching stage status replaced."""

    updated: list[DiscoveryStep] = []
    for step in steps:
        if step.stage == stage:
            updated.append(replace(step, status=status))
        else:
            updated.append(step)
    return updated
