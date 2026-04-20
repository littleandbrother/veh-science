"""Critic and Decision Layer — objective-aligned rule-based implementation."""

from __future__ import annotations

from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    CriticDecision,
    MechanismScreenResult,
    TaskCard,
    VerificationResult,
)


class RuleBasedCritic:
    """Rule-based critic that aligns decisions to the active task objective."""

    def __init__(self, task: TaskCard | None = None):
        self.task = task

    def decide(
        self,
        candidate: CandidateDesignFamily,
        screen_result: MechanismScreenResult | None = None,
        verification_result: VerificationResult | None = None,
    ) -> CriticDecision:
        """Produce a critic decision based on screening and verification results."""
        failure_modes: list[str] = []

        if screen_result is not None:
            if screen_result.verdict == "reject":
                return CriticDecision(
                    candidate_id=candidate.candidate_id,
                    decision="abandon",
                    reason=self._format_gate_failures(screen_result),
                    affected_module="mechanism",
                    next_action="Generate a new candidate family with a different bandgap/TR layout.",
                    failure_modes_triggered=failure_modes,
                    confidence=0.95,
                )
            if screen_result.verdict == "revise":
                return CriticDecision(
                    candidate_id=candidate.candidate_id,
                    decision="revise",
                    reason=self._format_gate_failures(screen_result),
                    affected_module="mechanism",
                    next_action="; ".join(screen_result.revision_hints),
                    failure_modes_triggered=failure_modes,
                    confidence=0.75,
                )

        if verification_result is not None:
            return self._evaluate_verification(candidate, verification_result, failure_modes)

        return CriticDecision(
            candidate_id=candidate.candidate_id,
            decision="revise",
            reason="No screening or verification results available",
            affected_module="coordinator",
            next_action="Run mechanism screening first",
            confidence=0.0,
        )

    def _evaluate_verification(
        self,
        candidate: CandidateDesignFamily,
        result: VerificationResult,
        failure_modes: list[str],
    ) -> CriticDecision:
        metrics = {m.label: m for m in result.metrics}

        primary_output = self._get_metric_value(metrics, "PrimaryOutput(TR)")
        mechanism_ratio = self._get_metric_value(metrics, "MechanismRatio")
        engineering_ratio = self._get_metric_value(metrics, "EngineeringRatio")
        eta = self._get_metric_value(metrics, "eta")
        transmission = self._get_metric_value(metrics, "T(Omega_TR)")
        if transmission is None:
            transmission = self._get_metric_value(metrics, "T(f_TR)")
        current_tr = self._get_metric_value(metrics, "I(TR)")
        rectified_current = self._get_metric_value(metrics, "I_rectified(TR)")

        if mechanism_ratio is not None and mechanism_ratio < 1.0:
            failure_modes.append("F10: Target output underperforms the mechanism baseline")
        if engineering_ratio is not None and engineering_ratio < 1.0:
            if self.task and self.task.harvesting_requirements.target_output == "current":
                failure_modes.append("F5: Target current underperforms the engineering baseline")
            else:
                failure_modes.append("F10: Output underperforms the engineering baseline")
        if eta is not None and eta < 0.3:
            failure_modes.append("F2: Insufficient boundary localization")
        if transmission is not None and transmission > 0:
            failure_modes.append("F7: Suppression violated at the TR peak")
        if (
            rectified_current is not None
            and current_tr is not None
            and current_tr > 0
            and rectified_current / current_tr < 0.7
        ):
            failure_modes.append("F5: Rectification-induced current collapse")

        if result.status == "pass":
            return self._accept_decision(candidate, result, primary_output, engineering_ratio)
        if result.status == "partial":
            return self._partial_decision(
                candidate,
                result,
                failure_modes,
                mechanism_ratio,
                engineering_ratio,
                transmission,
            )
        return self._fail_decision(
            candidate,
            result,
            failure_modes,
            mechanism_ratio,
            engineering_ratio,
            transmission,
        )

    def _accept_decision(
        self,
        candidate: CandidateDesignFamily,
        result: VerificationResult,
        primary_output: float | None,
        engineering_ratio: float | None,
    ) -> CriticDecision:
        target_name = self._target_name()
        if result.tier == "L1":
            reason = (
                f"L1 passed with mechanism-aligned {target_name}. "
                f"Escalate to L2 for engineering-baseline confirmation."
            )
            next_action = "Escalate to L2 beam verification."
            confidence = 0.78
        elif result.tier == "L2":
            if engineering_ratio is not None:
                reason = (
                    f"L2 passed. {target_name.capitalize()} at TR meets both mechanism and "
                    f"engineering baselines."
                )
            else:
                reason = f"L2 passed for the requested {target_name} objective."
            next_action = "Accepted for structural/electrical design iteration; run L3 when COMSOL is available."
            confidence = 0.92
        else:
            reason = f"{result.tier} verification passed for the requested {target_name} objective."
            next_action = "Design accepted. Generate final report."
            confidence = 0.95

        if primary_output is not None and primary_output <= 0:
            reason = f"{result.tier} reported pass but primary output is non-positive."
            next_action = "Re-check the verification metrics and solver settings."
            confidence = 0.35

        return CriticDecision(
            candidate_id=candidate.candidate_id,
            decision="accept",
            reason=reason,
            affected_module="verifiers",
            next_action=next_action,
            confidence=confidence,
        )

    def _partial_decision(
        self,
        candidate: CandidateDesignFamily,
        result: VerificationResult,
        failure_modes: list[str],
        mechanism_ratio: float | None,
        engineering_ratio: float | None,
        transmission: float | None,
    ) -> CriticDecision:
        severe_count = sum(
            1
            for value in (mechanism_ratio, engineering_ratio)
            if value is not None and value < 0.8
        )
        if transmission is not None and transmission > 0:
            severe_count += 1

        if severe_count >= 2 or len(failure_modes) >= 3:
            return CriticDecision(
                candidate_id=candidate.candidate_id,
                decision="switch_family",
                reason=(
                    "Partial verification exposed multiple coupled failures: "
                    + ", ".join(failure_modes)
                ),
                affected_module="proposals",
                next_action="Switch to a different TR family or a different structural contrast map.",
                failure_modes_triggered=failure_modes,
                confidence=0.82,
            )

        return CriticDecision(
            candidate_id=candidate.candidate_id,
            decision="revise",
            reason=self._build_revision_reason(result, mechanism_ratio, engineering_ratio, transmission),
            affected_module="codesign",
            next_action=self._build_revision_action(mechanism_ratio, engineering_ratio, transmission, candidate),
            failure_modes_triggered=failure_modes,
            confidence=0.63,
        )

    def _fail_decision(
        self,
        candidate: CandidateDesignFamily,
        result: VerificationResult,
        failure_modes: list[str],
        mechanism_ratio: float | None,
        engineering_ratio: float | None,
        transmission: float | None,
    ) -> CriticDecision:
        if (
            transmission is not None
            and transmission > 0
            and (
                (mechanism_ratio is not None and mechanism_ratio < 0.8)
                or (engineering_ratio is not None and engineering_ratio < 0.8)
            )
        ):
            return CriticDecision(
                candidate_id=candidate.candidate_id,
                decision="abandon",
                reason=f"Verification failed with incompatible suppression/output trade-off: {', '.join(failure_modes)}",
                affected_module="proposals",
                next_action="Abandon this family and regenerate from a different contrast or boundary strategy.",
                failure_modes_triggered=failure_modes,
                confidence=0.90,
            )

        return CriticDecision(
            candidate_id=candidate.candidate_id,
            decision="revise",
            reason=f"Verification failed at {result.tier}: {result.details}",
            affected_module="codesign",
            next_action=self._build_revision_action(mechanism_ratio, engineering_ratio, transmission, candidate),
            failure_modes_triggered=failure_modes,
            confidence=0.55,
        )

    @staticmethod
    def _format_gate_failures(sr: MechanismScreenResult) -> str:
        failed = [g for g in sr.gates if not g.passed]
        parts = [f"Gate {g.gate_id} ({g.gate_name}): {g.message}" for g in failed]
        return "Screening failed — " + "; ".join(parts)

    @staticmethod
    def _get_metric_value(metrics: dict, label: str) -> float | None:
        metric = metrics.get(label)
        if metric is None:
            return None
        if isinstance(metric.value, (int, float)):
            return float(metric.value)
        try:
            return float(str(metric.value).replace("x", "").strip())
        except ValueError:
            return None

    def _build_revision_reason(
        self,
        result: VerificationResult,
        mechanism_ratio: float | None,
        engineering_ratio: float | None,
        transmission: float | None,
    ) -> str:
        parts = [f"{result.tier} partial verification"]
        if mechanism_ratio is not None and mechanism_ratio < 1.0:
            parts.append(f"mechanism ratio={mechanism_ratio:.2f} < 1.0")
        if engineering_ratio is not None and engineering_ratio < 1.0:
            parts.append(f"engineering ratio={engineering_ratio:.2f} < 1.0")
        if transmission is not None and transmission > 0:
            parts.append(f"transmission={transmission:.2f} dB > 0 dB")
        return "; ".join(parts)

    def _build_revision_action(
        self,
        mechanism_ratio: float | None,
        engineering_ratio: float | None,
        transmission: float | None,
        candidate: CandidateDesignFamily,
    ) -> str:
        actions = []
        if transmission is not None and transmission > 0:
            actions.append("Move the TR farther from the gap edge or reduce electrical loading.")
        if mechanism_ratio is not None and mechanism_ratio < 1.0:
            actions.append(
                f"Increase boundary localization by adjusting delta away from 1.0 (current delta={candidate.structure.delta:.2f}) or increase N."
            )
        if engineering_ratio is not None and engineering_ratio < 1.0:
            target_name = self._target_name()
            actions.append(f"Improve {target_name} retention against the conventional beam by retuning coupling and load.")
        if not actions:
            actions.append("Fine-tune structure/electrical parameters within the current family.")
        return " ".join(actions)

    def _target_name(self) -> str:
        if self.task is None:
            return "output"
        return self.task.harvesting_requirements.target_output
