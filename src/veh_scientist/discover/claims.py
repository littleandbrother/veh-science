"""Claim-graph scaffolding for TR replay mode."""

from __future__ import annotations

from veh_scientist.interfaces import ClaimCard, DiscoverTaskCard

_TR_CLAIMS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "mechanism",
        "A non-periodic boundary in a finite periodic structure can create a truncation resonance inside the Bloch bandgap.",
        ("tr", "bandgap", "boundary"),
    ),
    (
        "experiment",
        "The truncation resonance state is boundary-localized and concentrates a disproportionate share of the total energy near the first unit cells.",
        ("localization", "energy", "eta"),
    ),
    (
        "mechanism",
        "Placing a piezoelectric port across the high-gap interface converts truncation-resonance gap motion into co-located voltage and power peaks while transmission remains below 0 dB.",
        ("piezo", "harvesting", "suppression"),
    ),
    (
        "design_rule",
        "delta acts as the truncation-resonance switch, alpha and beta place the bandgap and TR frequency, kappa2 and epsilon perform electromechanical matching, and N sharpens the resonance.",
        ("delta", "alpha", "beta", "kappa2", "epsilon", "N"),
    ),
    (
        "workflow",
        "The discovery path should move from infinite-chain band structure, to finite-chain TR identification, to piezoelectric harvesting, to parameter maps, and finally to beam-level validation.",
        ("workflow", "chain", "beam"),
    ),
)


def build_claim_graph(task: DiscoverTaskCard) -> list[ClaimCard]:
    """Create a lightweight claim graph from the discovery corpus.

    The current implementation is deterministic and seed-driven: it pulls any
    seed claims from source documents and augments them with the canonical TR
    mechanism claims needed for the replay workflow.
    """

    claims: list[ClaimCard] = []
    seen_text: set[str] = set()

    for doc in task.source_corpus:
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

    if task.mechanism_focus == "truncation_resonance":
        target_doc_id = next((doc.document_id for doc in task.source_corpus if doc.role == "target_paper"), "")
        for claim_type, claim_text, tags in _TR_CLAIMS:
            if claim_text in seen_text:
                continue
            claims.append(
                ClaimCard(
                    document_id=target_doc_id,
                    claim_type=claim_type,
                    claim_text=claim_text,
                    provenance_note="canonical-tr-replay",
                    tags=tags,
                )
            )
            seen_text.add(claim_text)

    return claims
