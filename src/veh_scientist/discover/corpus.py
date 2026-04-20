"""Corpus helpers for replay/discover mode."""

from __future__ import annotations

from veh_scientist.interfaces import CorpusDocument, DiscoverTaskCard

_ROLE_PRIORITY = {
    "target_paper": 0,
    "reference_paper": 1,
    "notes": 2,
    "artifact": 3,
    "code": 4,
}


def build_corpus_manifest(task: DiscoverTaskCard) -> list[CorpusDocument]:
    """Return corpus documents ordered by replay priority."""
    return sorted(
        task.source_corpus,
        key=lambda doc: (_ROLE_PRIORITY.get(doc.role, 99), doc.title.lower(), doc.document_id),
    )


def target_documents(task: DiscoverTaskCard) -> list[CorpusDocument]:
    """Return target-paper documents from the corpus."""
    return [doc for doc in build_corpus_manifest(task) if doc.role == "target_paper"]
