"""Persistent Memory Store — JSON-file backed.

Blueprint §5.10: Memory entries must be structured, tagged, and
traceable back to experiments.

Memory categories:
    - motif:      successful design motifs
    - failure:    failed design patterns
    - knowledge:  mechanism knowledge
    - rule:       electrical interface matching rules
    - strategy:   reusable refinement strategies
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from veh_scientist.interfaces.schemas import MemoryRecord


class MemoryStore:
    """JSON-file backed persistent memory store.

    Each task gets its own memory file. Records are append-only
    and can be queried by round, category, or tag.

    Usage
    -----
    >>> store = MemoryStore(Path("results/memory"))
    >>> store.add(record)
    >>> failures = store.query(category="failure")
    """

    def __init__(self, base_dir: Path | str):
        """
        Parameters
        ----------
        base_dir : Path or str
            Directory where memory files are stored.
            One JSON file per task: ``{base_dir}/{task_id}.json``
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, list[MemoryRecord]] = {}

    def _file_path(self, task_id: str) -> Path:
        return self.base_dir / f"{task_id}.json"

    def _load(self, task_id: str) -> list[MemoryRecord]:
        if task_id in self._cache:
            return self._cache[task_id]

        path = self._file_path(task_id)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            records = [self._dict_to_record(d) for d in data]
        else:
            records = []

        self._cache[task_id] = records
        return records

    def _save(self, task_id: str) -> None:
        path = self._file_path(task_id)
        records = self._cache.get(task_id, [])
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in records], f, indent=2, ensure_ascii=False)

    @staticmethod
    def _dict_to_record(d: dict) -> MemoryRecord:
        return MemoryRecord(
            memory_id=d.get("memory_id", ""),
            round_id=d.get("round_id", 0),
            category=d.get("category", "knowledge"),
            observation=d.get("observation", ""),
            interpretation=d.get("interpretation", ""),
            next_step=d.get("next_step", ""),
            tags=d.get("tags", []),
            source_candidate_id=d.get("source_candidate_id", ""),
            timestamp=d.get("timestamp", ""),
        )

    def add(self, record: MemoryRecord, task_id: str = "default") -> None:
        """Add a memory record to the store.

        Parameters
        ----------
        record : MemoryRecord
            The record to store.
        task_id : str
            The task this record belongs to.
        """
        records = self._load(task_id)
        records.append(record)
        self._save(task_id)

    def query(
        self,
        task_id: str = "default",
        category: str | None = None,
        round_id: int | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryRecord]:
        """Query memory records with optional filters.

        Parameters
        ----------
        task_id : str
            The task to query.
        category : str, optional
            Filter by category (motif, failure, knowledge, rule, strategy).
        round_id : int, optional
            Filter by round number.
        tags : list[str], optional
            Filter by tags (any match).

        Returns
        -------
        list[MemoryRecord]
            Matching records, ordered by timestamp.
        """
        records = self._load(task_id)
        result = records

        if category is not None:
            result = [r for r in result if r.category == category]
        if round_id is not None:
            result = [r for r in result if r.round_id == round_id]
        if tags:
            tag_set = set(tags)
            result = [r for r in result if tag_set & set(r.tags)]

        return result

    def get_all(self, task_id: str = "default") -> list[MemoryRecord]:
        """Get all memory records for a task."""
        return self._load(task_id)

    def get_latest(
        self, task_id: str = "default", n: int = 5
    ) -> list[MemoryRecord]:
        """Get the most recent N memory records."""
        records = self._load(task_id)
        return records[-n:]
