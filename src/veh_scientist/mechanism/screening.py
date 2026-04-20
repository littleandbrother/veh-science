"""Mechanism Screening Orchestrator.

Blueprint §5.5: Reject candidates that do not satisfy mechanism preconditions
before expensive evaluation.

The MechanismScreener runs Gates 1-6 in order against a CandidateDesignFamily,
producing a MechanismScreenResult with verdict: pass / revise / reject.
"""

from __future__ import annotations

from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    GateResult,
    MechanismScreenResult,
    TaskCard,
)
from veh_scientist.mechanism.beam_screening import screen_candidate_with_beam
from veh_scientist.mechanism.gates import (
    gate_1_bandgap_existence,
    gate_2_boundary_asymmetry,
    gate_3_tr_in_bandgap,
    gate_4_energy_localization,
    gate_5_topological_classification,
    gate_6_suppression_compatibility,
)


class MechanismScreener:
    """Run Gates 1-6 against a candidate and produce a screening verdict.

    Usage
    -----
    >>> screener = MechanismScreener()
    >>> result = screener.screen(candidate)
    >>> print(result.verdict)  # "pass", "revise", or "reject"
    """

    def __init__(
        self,
        eta_threshold: float = 0.3,
        max_transmission_dB: float = 0.0,
        skip_topological: bool = False,
        task: TaskCard | None = None,
        allow_tr_frequency_exception: bool = False,
    ):
        """
        Parameters
        ----------
        eta_threshold : float
            Minimum energy concentration ratio for Gate 4.
        max_transmission_dB : float
            Maximum allowed transmission at TR frequency for Gate 6.
        skip_topological : bool
            If True, skip Gate 5 (topological classification).
        task : TaskCard | None
            When provided, screening is executed on the continuous beam model
            instead of the legacy lumped-chain proxy.
        """
        self.eta_threshold = eta_threshold
        self.max_transmission_dB = max_transmission_dB
        self.skip_topological = skip_topological
        self.task = task
        self.allow_tr_frequency_exception = allow_tr_frequency_exception

    def screen(self, candidate: CandidateDesignFamily) -> MechanismScreenResult:
        """Run all gates in sequence and produce a screening result.

        Early termination: if a mandatory gate fails with REJECT,
        remaining gates are skipped.

        Parameters
        ----------
        candidate : CandidateDesignFamily
            The candidate to screen.

        Returns
        -------
        MechanismScreenResult
            Contains per-gate results, overall verdict, and revision hints.
        """
        if self.task is not None:
            return screen_candidate_with_beam(
                candidate,
                self.task,
                eta_threshold=self.eta_threshold,
                max_transmission_dB=self.max_transmission_dB,
                allow_tr_frequency_exception=self.allow_tr_frequency_exception,
            )

        s = candidate.structure
        e = candidate.electrical
        gates = []
        revision_hints: list[str] = []
        tr_frequency: float | None = None
        eta: float | None = None

        # ----- Gate 1: Bandgap existence (REJECT if fail) -----
        g1 = gate_1_bandgap_existence(s.alpha, s.beta)
        gates.append(g1)
        if not g1.passed:
            return MechanismScreenResult(
                candidate_id=candidate.candidate_id,
                verdict="reject",
                gates=gates,
                revision_hints=[
                    "Change (alpha, beta) to create a bandgap. "
                    "Try alpha != 1.0 or beta != 1.0."
                ],
            )

        # ----- Gate 2: Boundary asymmetry (REJECT if fail) -----
        g2 = gate_2_boundary_asymmetry(s.delta)
        gates.append(g2)
        if not g2.passed:
            return MechanismScreenResult(
                candidate_id=candidate.candidate_id,
                verdict="reject",
                gates=gates,
                revision_hints=[
                    "Set delta != 1.0 to break boundary symmetry. "
                    "Typical range: 0.1-0.9 or 1.1-4.0."
                ],
            )

        # ----- Gate 3: TR inside bandgap (REVISE if fail) -----
        g3 = gate_3_tr_in_bandgap(s.alpha, s.beta, s.delta, s.N)
        gates.append(g3)
        if not g3.passed:
            revision_hints.append(
                "No TR found in bandgap. Adjust delta to shift TR frequency, "
                "or modify (alpha, beta) to reposition the bandgap."
            )
            return MechanismScreenResult(
                candidate_id=candidate.candidate_id,
                verdict="revise",
                gates=gates,
                revision_hints=revision_hints,
            )
        tr_frequency = g3.value

        # ----- Gate 4: Energy localization (REVISE if fail) -----
        g4 = gate_4_energy_localization(
            s.alpha, s.beta, s.delta, s.N,
            kappa2=e.kappa2,
            epsilon=e.epsilon,
            eta_threshold=self.eta_threshold,
        )
        gates.append(g4)
        eta = g4.value
        if not g4.passed:
            revision_hints.append(
                f"Energy localization η={eta:.4f} too weak (< {self.eta_threshold}). "
                f"Increase |delta - 1| or increase N for sharper localization."
            )
            # Don't return yet — continue to gather more diagnostic info

        # ----- Gate 5: Topological classification (advisory) -----
        if not self.skip_topological:
            g5 = gate_5_topological_classification(s.alpha, s.beta)
            gates.append(g5)
            if g5.value == 0:
                revision_hints.append(
                    "C_g = 0: TR may not be topologically protected. "
                    "Recommend sensitivity analysis for robustness."
                )

        # ----- Gate 6: Suppression compatibility (REVISE if fail) -----
        g6 = gate_6_suppression_compatibility(
            s.alpha, s.beta, s.delta, s.N,
            kappa2=e.kappa2,
            epsilon=e.epsilon,
            max_transmission_dB=self.max_transmission_dB,
        )
        if self.allow_tr_frequency_exception and not g6.passed:
            g6 = GateResult(
                gate_id=g6.gate_id,
                gate_name=g6.gate_name,
                passed=True,
                value=g6.value,
                threshold=g6.threshold,
                message=(
                    f"{g6.message} Task card enables tr_frequency_exception, so Gate 6 is treated as advisory at the TR peak."
                ),
            )
        gates.append(g6)
        if not g6.passed:
            revision_hints.append(
                "Suppression violated at TR frequency. "
                "This may indicate TR is near the bandgap edge or model inconsistency."
            )

        # ----- Overall verdict -----
        all_mandatory_passed = all(
            g.passed for g in gates if g.gate_name != "topological_classification"
        )

        if all_mandatory_passed:
            verdict = "pass"
        elif any(not g.passed for g in gates if g.gate_id in (1, 2)):
            verdict = "reject"
        else:
            verdict = "revise"

        return MechanismScreenResult(
            candidate_id=candidate.candidate_id,
            verdict=verdict,
            gates=gates,
            tr_frequency=tr_frequency,
            eta=eta,
            revision_hints=revision_hints,
        )
