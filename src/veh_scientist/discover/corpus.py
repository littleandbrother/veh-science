"""Corpus helpers for replay/discover mode."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from veh_scientist.discover.pdf import build_pdf_digest, extract_pdf_text
from veh_scientist.discover.utils import resolve_path
from veh_scientist.interfaces import CorpusDocument, DiscoverTaskCard

_ROLE_PRIORITY = {
    "target_paper": 0,
    "reference_paper": 1,
    "notes": 2,
    "artifact": 3,
    "code": 4,
}


def build_corpus_manifest(task: DiscoverTaskCard, base_dir: str | Path | None = None) -> list[CorpusDocument]:
    """Return corpus documents ordered by replay priority and enriched with path resolution."""

    manifest: list[CorpusDocument] = []
    for doc in task.source_corpus:
        resolved = resolve_path(doc.path, base_dir=base_dir)
        manifest.append(
            replace(
                doc,
                resolved_path=str(resolved),
                exists=resolved.exists(),
            )
        )
    return sorted(
        manifest,
        key=lambda doc: (_ROLE_PRIORITY.get(doc.role, 99), doc.title.lower(), doc.document_id),
    )


def target_documents(task: DiscoverTaskCard, base_dir: str | Path | None = None) -> list[CorpusDocument]:
    """Return target-paper documents from the corpus."""
    return [doc for doc in build_corpus_manifest(task, base_dir=base_dir) if doc.role == "target_paper"]


def read_document_text(doc: CorpusDocument) -> str:
    """Read a corpus document into plain text when supported."""

    path = Path(doc.resolved_path or doc.path)
    if not path.exists():
        return ""
    if doc.source_type == "pdf":
        return extract_pdf_text(path)
    return path.read_text(encoding="utf-8")


def corpus_digests(manifest: list[CorpusDocument]) -> dict[str, dict[str, Any]]:
    """Build lightweight digests for the resolved corpus."""

    digests: dict[str, dict[str, Any]] = {}
    for doc in manifest:
        if not doc.exists:
            digests[doc.document_id] = {
                "title": doc.title,
                "path": doc.path,
                "resolved_path": doc.resolved_path,
                "exists": False,
                "summary": doc.summary,
            }
            continue
        path = Path(doc.resolved_path or doc.path)
        if doc.source_type == "pdf":
            digest = build_pdf_digest(path)
        else:
            text = path.read_text(encoding="utf-8")
            digest = {
                "path": str(path.resolve()),
                "n_pages": None,
                "section_titles": [],
                "preview": text[:3000],
            }
        digest.update(
            {
                "title": doc.title,
                "role": doc.role,
                "source_type": doc.source_type,
                "summary": doc.summary,
                "tags": list(doc.tags),
                "exists": True,
            }
        )
        digests[doc.document_id] = digest
    return digests


def gap_statement(task: DiscoverTaskCard, manifest: list[CorpusDocument], digests: dict[str, dict[str, Any]]) -> str:
    """Write the discovery gap in a replay-oriented form."""

    available_refs = [doc.title for doc in manifest if doc.role == "reference_paper" and doc.exists]
    missing_refs = [doc.title for doc in manifest if doc.role == "reference_paper" and not doc.exists]
    target_title = next((doc.title for doc in manifest if doc.role == "target_paper"), "target paper")

    lines = [
        f"# Gap statement for {task.task_id}",
        "",
        f"Target outcome: replay the mechanism-development path culminating in **{target_title}**.",
        "",
        "The replay is centered on the following missing bridge:",
        "",
        "1. establish when truncation resonance appears inside a bandgap,",
        "2. quantify how strongly the corresponding mode localizes energy near the boundary,",
        "3. convert that hotspot into a piezoelectric harvesting port without losing attenuation,",
        "4. separate switch/tuner/matcher/Q-factor parameters into interpretable design roles, and",
        "5. transfer the same logic from the fast chain model to a continuous beam oracle.",
        "",
    ]
    if available_refs:
        lines.extend([
            "Available precursor documents:",
            *[f"- {title}" for title in available_refs],
            "",
        ])
    if missing_refs:
        lines.extend([
            "Missing precursor documents (kept in the corpus manifest, but unresolved on disk):",
            *[f"- {title}" for title in missing_refs],
            "",
        ])
    lines.extend([
        "Mechanism focus:",
        f"- {task.mechanism_focus}",
        "",
        "This executable replay therefore emphasizes derivation + L1 chain evidence first, then uses L2 beam evidence to test whether the same mechanism persists in a continuous structure.",
    ])
    return "\n".join(lines)
