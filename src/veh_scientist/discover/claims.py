"""Claim-graph builders for executable TR replay mode."""

from __future__ import annotations

from pathlib import Path

from veh_scientist.discover.corpus import build_corpus_manifest, read_document_text
from veh_scientist.discover.pdf import keyword_matches, sentence_candidates
from veh_scientist.interfaces import ClaimCard, DiscoverTaskCard

_CLAIM_PATTERNS: tuple[tuple[str, tuple[str, ...], str, tuple[str, ...]], ...] = (
    (
        "mechanism",
        ("truncation resonance", "bandgap", "boundary"),
        "A non-periodic boundary in a finite periodic structure can create a truncation resonance inside the Bloch bandgap.",
        ("tr", "bandgap", "boundary"),
    ),
    (
        "experiment",
        ("localized", "energy", "boundary"),
        "The truncation resonance state is boundary-localized and concentrates a disproportionate share of the total energy near the first unit cells.",
        ("localization", "energy", "eta"),
    ),
    (
        "equation",
        ("piezoelectric", "voltage", "power"),
        "Placing a piezoelectric port across the high-gap interface converts truncation-resonance gap motion into co-located voltage and power peaks while transmission remains below 0 dB.",
        ("piezo", "harvesting", "suppression"),
    ),
    (
        "design_rule",
        ("delta", "alpha", "beta", "kappa", "epsilon", "N"),
        "delta acts as the truncation-resonance switch, alpha and beta place the bandgap and TR frequency, kappa2 and epsilon perform electromechanical matching, and N sharpens the resonance.",
        ("delta", "alpha", "beta", "kappa2", "epsilon", "N"),
    ),
    (
        "workflow",
        ("diatomic chain", "Timoshenko beam", "transfer"),
        "The discovery path should move from infinite-chain band structure, to finite-chain TR identification, to piezoelectric harvesting, to parameter maps, and finally to beam-level validation.",
        ("workflow", "chain", "beam"),
    ),
)


def build_claim_graph(task: DiscoverTaskCard, base_dir: str | Path | None = None) -> list[ClaimCard]:
    """Create a replay-ready claim graph grounded in the available corpus."""

    manifest = build_corpus_manifest(task, base_dir=base_dir)
    claims: list[ClaimCard] = []
    seen_text: set[str] = set()

    for doc in manifest:
        for seed in doc.seed_claims:
            normalized = seed.strip()
            if not normalized or normalized in seen_text:
                continue
            claims.append(
                ClaimCard(
                    document_id=doc.document_id,
                    claim_type="mechanism" if doc.role != "notes" else "workflow",
                    claim_text=normalized,
                    provenance_note=f"seed:{doc.title}",
                    tags=doc.tags,
                )
            )
            seen_text.add(normalized)

        if not doc.exists:
            continue
        text = read_document_text(doc)
        sentences = sentence_candidates(text)
        if not sentences:
            continue
        for claim_type, keywords, fallback_text, tags in _CLAIM_PATTERNS:
            matches = keyword_matches(sentences, keywords, limit=1)
            if matches:
                sentence = matches[0]
                if sentence not in seen_text:
                    claims.append(
                        ClaimCard(
                            document_id=doc.document_id,
                            claim_type=claim_type,
                            claim_text=sentence,
                            provenance_note=f"pdf:{Path(doc.resolved_path or doc.path).name}",
                            tags=tags,
                        )
                    )
                    seen_text.add(sentence)

    target_doc_id = next((doc.document_id for doc in manifest if doc.role == "target_paper"), "")
    for claim_type, _, fallback_text, tags in _CLAIM_PATTERNS:
        if fallback_text in seen_text:
            continue
        claims.append(
            ClaimCard(
                document_id=target_doc_id,
                claim_type=claim_type,
                claim_text=fallback_text,
                provenance_note="canonical-tr-replay",
                tags=tags,
            )
        )
        seen_text.add(fallback_text)

    return claims
