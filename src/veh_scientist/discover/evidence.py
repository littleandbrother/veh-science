"""Evidence-link scaffolding for the discovery program."""

from __future__ import annotations

from veh_scientist.interfaces import (
    ClaimCard,
    DerivationCard,
    EvidenceRecord,
    ExperimentArtifact,
    GapCandidate,
    ToolRunRecord,
)


def _matching_derivations(claim: ClaimCard, derivations: list[DerivationCard]) -> tuple[str, ...]:
    claim_text = claim.claim_text.lower()
    matched: list[str] = []
    for card in derivations:
        title = card.title.lower()
        if any(token in title for token in ("dispersion", "stiffness", "beam", "energy", "voltage")) and any(
            token in claim_text for token in ("bandgap", "truncation", "piezo", "energy", "beam", "voltage", "design")
        ):
            matched.append(card.derivation_id)
    return tuple(dict.fromkeys(matched))


def draft_evidence_records(
    claims: list[ClaimCard],
    derivations: list[DerivationCard],
    gap_candidates: list[GapCandidate],
    artifacts: list[ExperimentArtifact] | None = None,
    tool_runs: list[ToolRunRecord] | None = None,
) -> list[EvidenceRecord]:
    """Create a lightweight claim-to-evidence matrix.

    The current version is intentionally conservative: it marks claims as
    supported when they are backed by at least one derivation and a non-empty
    ranked-gap set for design-rule claims, otherwise it leaves them as pending.
    """

    artifacts = artifacts or []
    tool_runs = tool_runs or []
    run_ids = tuple(run.run_id for run in tool_runs if run.status in {"passed", "planned"})
    artifact_ids = tuple(artifact.artifact_id for artifact in artifacts)

    records: list[EvidenceRecord] = []
    for claim in claims:
        derivation_ids = _matching_derivations(claim, derivations)
        supporting_artifacts = artifact_ids
        verdict = "supported" if derivation_ids else "pending"
        if claim.claim_type == "design_rule" and not gap_candidates:
            verdict = "pending"
        records.append(
            EvidenceRecord(
                claim_id=claim.claim_id,
                supporting_derivations=derivation_ids,
                supporting_artifacts=supporting_artifacts,
                supporting_runs=run_ids,
                verdict=verdict,
                notes="auto-linked evidence scaffold",
            )
        )
    return records
