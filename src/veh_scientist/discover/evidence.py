"""Evidence-link helpers for the executable discovery program."""

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
    text = claim.claim_text.lower()
    matched: list[str] = []
    for card in derivations:
        title = card.title.lower()
        if "beam" in text and "beam" in title:
            matched.append(card.derivation_id)
        elif any(token in text for token in ("piezo", "voltage", "power")) and any(
            token in title for token in ("voltage", "stiffness")
        ):
            matched.append(card.derivation_id)
        elif any(token in text for token in ("bandgap", "truncation", "resonance")) and any(
            token in title for token in ("dispersion", "dynamic stiffness")
        ):
            matched.append(card.derivation_id)
        elif any(token in text for token in ("energy", "localized", "eta")) and "energy" in title:
            matched.append(card.derivation_id)
        elif any(token in text for token in ("delta", "alpha", "beta", "kappa", "epsilon", "n")) and any(
            token in title for token in ("stiffness", "dispersion", "beam")
        ):
            matched.append(card.derivation_id)
    return tuple(dict.fromkeys(matched))


def _matching_artifacts(claim: ClaimCard, artifacts: list[ExperimentArtifact]) -> tuple[str, ...]:
    text = claim.claim_text.lower()
    matched: list[str] = []
    for artifact in artifacts:
        label = f"{artifact.label} {artifact.description} {artifact.path}".lower()
        if any(token in text for token in ("bandgap", "resonance", "truncation")) and any(
            token in label for token in ("dispersion", "spectrum", "band", "tr")
        ):
            matched.append(artifact.artifact_id)
        if any(token in text for token in ("localized", "energy", "eta")) and any(
            token in label for token in ("mode", "eta", "local")
        ):
            matched.append(artifact.artifact_id)
        if any(token in text for token in ("piezo", "voltage", "power", "harvest")) and any(
            token in label for token in ("harvest", "voltage", "power")
        ):
            matched.append(artifact.artifact_id)
        if "beam" in text and "beam" in label:
            matched.append(artifact.artifact_id)
        if any(token in text for token in ("delta", "alpha", "beta", "kappa", "epsilon", "n")) and any(
            token in label for token in ("scan", "map", "ranking")
        ):
            matched.append(artifact.artifact_id)
    return tuple(dict.fromkeys(matched))


def draft_evidence_records(
    claims: list[ClaimCard],
    derivations: list[DerivationCard],
    gap_candidates: list[GapCandidate],
    artifacts: list[ExperimentArtifact] | None = None,
    tool_runs: list[ToolRunRecord] | None = None,
) -> list[EvidenceRecord]:
    """Create a claim-to-evidence matrix."""

    artifacts = artifacts or []
    tool_runs = tool_runs or []
    passed_runs = tuple(run.run_id for run in tool_runs if run.status in {"passed", "skipped"})

    records: list[EvidenceRecord] = []
    for claim in claims:
        derivation_ids = _matching_derivations(claim, derivations)
        artifact_ids = _matching_artifacts(claim, artifacts)
        verdict = "supported" if derivation_ids or artifact_ids else "pending"
        if claim.claim_type == "design_rule" and not gap_candidates:
            verdict = "pending"
        notes = []
        if claim.claim_type == "design_rule" and gap_candidates:
            notes.append(f"{len(gap_candidates)} ranked gap candidates available")
        if not passed_runs:
            notes.append("no completed tool runs")
        records.append(
            EvidenceRecord(
                claim_id=claim.claim_id,
                supporting_derivations=derivation_ids,
                supporting_artifacts=artifact_ids,
                supporting_runs=passed_runs,
                verdict=verdict,
                notes="; ".join(notes) or "auto-linked evidence",
            )
        )
    return records
