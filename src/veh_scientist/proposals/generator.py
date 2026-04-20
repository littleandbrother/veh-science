"""Heuristic proposal generator for candidate design families."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    ElectricalParams,
    MemoryRecord,
    StructuralParams,
    TaskCard,
    TransducerParams,
)


class ProposalGenerator:
    """Generate a small, diverse candidate family each round."""

    def __init__(self, task: TaskCard, max_candidates: int = 3):
        self.task = task
        self.max_candidates = max_candidates

    def generate(
        self,
        round_id: int,
        seed_params: dict[str, Any],
        memory_records: list[MemoryRecord] | None = None,
        guidance_notes: list[str] | None = None,
    ) -> list[CandidateDesignFamily]:
        """Produce multiple candidate families around the current seed."""
        memory_records = memory_records or []
        guidance_notes = guidance_notes or []
        failure_text = " ".join(record.observation.lower() for record in memory_records[-5:])
        guidance_text = " ".join(note.lower() for note in guidance_notes[-5:])

        variants: list[tuple[str, dict[str, Any], list[str]]] = [
            (
                "proposal:seed",
                dict(seed_params),
                ["Seed candidate carried over from previous round."],
            ),
            (
                "proposal:localization",
                {
                    **seed_params,
                    "delta": min(max(seed_params["delta"] * 1.25, 0.35), 3.2),
                    "N": min(seed_params["N"] + 4, 28),
                },
                ["Boosted boundary localization by increasing |delta-1| and N."],
            ),
            (
                "proposal:electrical",
                {
                    **seed_params,
                    "kappa2": min(seed_params["kappa2"] * 1.4, 0.18),
                    "beta": min(max(seed_params["beta"] * 0.9, 0.2), 4.0),
                },
                ["Shifted toward stronger electromechanical coupling."],
            ),
        ]

        if "suppression" in failure_text or "bandgap edge" in failure_text:
            variants.append(
                (
                    "proposal:suppression",
                    {
                        **seed_params,
                        "delta": 1.0 + 0.65 * (seed_params["delta"] - 1.0),
                        "kappa2": max(seed_params["kappa2"] * 0.85, 0.01),
                    },
                    ["Pulled TR away from the gap edge to recover suppression margin."],
                )
            )

        if "tuning layer" in guidance_text or "soft layer" in guidance_text:
            variants.append(
                (
                    "proposal:tuning_layer",
                    {
                        **seed_params,
                        "delta": min(max(seed_params["delta"] * 1.1, 0.4), 3.2),
                        "beta": min(max(seed_params["beta"] * 0.82, 0.18), 4.0),
                    },
                    ["Applied user guidance for a tuning-layer-like softer boundary transition."],
                )
            )

        if "defect" in guidance_text:
            variants.append(
                (
                    "proposal:defect",
                    {
                        **seed_params,
                        "beta": min(max(seed_params["beta"] * 0.75, 0.15), 4.0),
                        "N": min(seed_params["N"] + 2, 30),
                    },
                    ["Applied user guidance for a near-boundary defect to reshape localization."],
                )
            )

        if "suppression" in guidance_text:
            variants.append(
                (
                    "proposal:user_suppression",
                    {
                        **seed_params,
                        "delta": 1.0 + 0.55 * (seed_params["delta"] - 1.0),
                        "kappa2": max(seed_params["kappa2"] * 0.8, 0.01),
                    },
                    ["Applied user guidance to preserve suppression margin before maximizing output."],
                )
            )

        if self.task.harvesting_requirements.target_output == "current":
            variants.append(
                (
                    "proposal:current",
                    {
                        **seed_params,
                        "kappa2": min(seed_params["kappa2"] * 1.6, 0.20),
                        "N": min(seed_params["N"] + 2, 30),
                    },
                    ["Biased toward stronger current extraction under matched load."],
                )
            )

        candidates: list[CandidateDesignFamily] = []
        seen = set()
        for source, params, assumptions in variants:
            key = (
                round(params["alpha"], 6),
                round(params["beta"], 6),
                round(params["delta"], 6),
                int(params["N"]),
                round(params["kappa2"], 6),
            )
            if key in seen:
                continue
            seen.add(key)
            candidates.append(self._build_candidate(round_id, source, params, assumptions))
            if len(candidates) >= self.max_candidates:
                break

        return candidates

    def _build_candidate(
        self,
        round_id: int,
        source: str,
        params: dict[str, Any],
        assumptions: list[str],
    ) -> CandidateDesignFamily:
        structure = StructuralParams(
            alpha=params["alpha"],
            beta=params["beta"],
            delta=params["delta"],
            N=params["N"],
        )
        electrical = ElectricalParams(
            kappa2=params["kappa2"],
            epsilon=params.get("epsilon"),
            load_resistance=self.task.harvesting_requirements.load_value,
            load_topology=self.task.harvesting_requirements.load_topology,
        )
        transducer = replace(
            TransducerParams(),
            piezo_material=self.task.envelope_constraints.piezo_material,
        )
        return CandidateDesignFamily(
            round_id=round_id,
            source=source,
            structure=structure,
            transducer=transducer,
            electrical=electrical,
            mechanism_hypothesis=(
                "Use TR-enabled boundary localization to maintain suppression "
                "while preserving the target electrical output."
            ),
            assumptions=assumptions,
            provenance={
                "target_output": self.task.harvesting_requirements.target_output,
                "load_topology": self.task.harvesting_requirements.load_topology,
            },
        )
