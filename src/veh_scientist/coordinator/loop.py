"""Research Coordinator — objective-aligned research loop."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from veh_scientist.analysis import (
    build_output_comparison,
    primary_output_value,
    ratio_status,
    threshold_status,
)
from veh_scientist.codesign import CandidateToBeamTranslator
from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    CriticDecision,
    MemoryRecord,
    MetricValue,
    RoundState,
    TaskCard,
    VerificationResult,
)
from veh_scientist.mechanism.screening import MechanismScreener
from veh_scientist.critic.decision import RuleBasedCritic
from veh_scientist.memory.store import MemoryStore
from veh_scientist.proposals import ProposalGenerator
from veh_scientist.taskcard.parser import parse_task_card
from veh_scientist.taskcard.validator import validate_task_card
from veh_scientist.verifiers.l1_chain import compute_harvesting_metrics
from veh_scientist.verifiers.l2_beam import compute_beam_harvesting_metrics
from veh_scientist.verifiers.l2_beam.baseline_comparison import compute_dual_baseline


logger = logging.getLogger(__name__)


class ResearchLoop:
    """Execute a multi-candidate research loop aligned to the active task."""

    def __init__(
        self,
        task: TaskCard,
        max_rounds: int = 6,
        output_dir: Path | str = "results/runs",
        guidance_notes: list[str] | None = None,
    ):
        self.task = task
        self.max_rounds = max_rounds
        self.output_dir = Path(output_dir) / task.task_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.guidance_notes = guidance_notes or []

        self.screener = MechanismScreener(
            task=task,
            eta_threshold=0.3,
            max_transmission_dB=task.suppression_requirements.max_allowed_transmission_dB,
            allow_tr_frequency_exception=task.suppression_requirements.tr_frequency_exception,
        )
        self.critic = RuleBasedCritic(task)
        self.memory = MemoryStore(self.output_dir / "memory")
        self.proposer = ProposalGenerator(task)
        self.translator = CandidateToBeamTranslator(task)

        self.rounds: list[RoundState] = []
        self.best_candidate: CandidateDesignFamily | None = None
        self.best_pef: float = 0.0
        self.best_score: float = float("-inf")

    def run(self) -> list[RoundState]:
        """Execute the full research loop."""
        logger.info(f"Starting research loop for task '{self.task.task_id}'")
        logger.info(f"Max rounds: {self.max_rounds}")

        seed_params = {
            "alpha": 1.0,
            "beta": 0.5,
            "delta": 1.5,
            "N": 10,
            "kappa2": 0.05,
            "epsilon": None,
        }

        for round_idx in range(1, self.max_rounds + 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"  ROUND {round_idx}")
            logger.info(f"{'=' * 60}")

            round_state = self._execute_round(round_idx, seed_params)
            self.rounds.append(round_state)

            accepted = any(
                d.decision == "accept"
                and v.status == "pass"
                and v.tier in {"L2", "L3"}
                for d in round_state.critic_decisions
                for v in round_state.verification_results
                if d.candidate_id == v.candidate_id
            )
            if accepted:
                logger.info(f"✅ Feasible design found in round {round_idx}!")
                break

            seed_params = self._suggest_next_params(seed_params, round_state)
            logger.info(f"Next round seed params: {seed_params}")

        self._save_report()
        return self.rounds

    def _execute_round(self, round_id: int, seed_params: dict[str, Any]) -> RoundState:
        """Execute a single research round with multiple candidate families."""
        state = RoundState(
            round_id=round_id,
            task_id=self.task.task_id,
            phase="discussing",
        )

        candidates = self.proposer.generate(
            round_id=round_id,
            seed_params=seed_params,
            memory_records=self.memory.get_latest(task_id=self.task.task_id, n=6),
            guidance_notes=self.guidance_notes,
        )
        state.candidates.extend(candidates)

        round_best_candidate: CandidateDesignFamily | None = None
        round_best_score = float("-inf")

        for candidate in candidates:
            logger.info(
                "  Candidate %s: alpha=%s, beta=%s, delta=%s, N=%s, kappa2=%s",
                candidate.candidate_id,
                candidate.structure.alpha,
                candidate.structure.beta,
                candidate.structure.delta,
                candidate.structure.N,
                candidate.electrical.kappa2,
            )

            state.phase = "screening"
            screen_result = self.screener.screen(candidate)
            state.screen_results.append(screen_result)
            logger.info(f"  Screening verdict: {screen_result.verdict}")
            for gate in screen_result.gates:
                status = "✅" if gate.passed else "❌"
                logger.info(f"    {status} Gate {gate.gate_id} ({gate.gate_name}): {gate.message}")

            latest_verification: VerificationResult | None = None

            if screen_result.verdict == "pass":
                state.phase = "verifying"
                l1_result = self._run_l1_verification(candidate, screen_result)
                state.verification_results.append(l1_result)
                self._update_best_pef(l1_result)
                logger.info(f"  L1 Verification: {l1_result.status}")
                self._log_metrics(l1_result.metrics)

                l2_result = self._run_l2_verification(candidate)
                state.verification_results.append(l2_result)
                self._update_best_pef(l2_result)
                latest_verification = l2_result
                logger.info(f"  L2 Verification: {l2_result.status}")
                self._log_metrics(l2_result.metrics)

                if self._l3_available() and l2_result.status in {"pass", "partial"}:
                    try:
                        l3_result = self._run_l3_verification(candidate)
                    except Exception as exc:  # noqa: BLE001
                        logger.info(f"  L3 Verification skipped: {exc}")
                        l3_result = None
                    if l3_result is not None:
                        state.verification_results.append(l3_result)
                        logger.info(f"  L3 Verification: {l3_result.status}")
                        self._log_metrics(l3_result.metrics)
                        latest_verification = l3_result

            state.phase = "critiquing"
            decision = self.critic.decide(
                candidate,
                screen_result=screen_result,
                verification_result=latest_verification,
            )
            state.critic_decisions.append(decision)
            logger.info(f"  Critic: {decision.decision} — {decision.reason}")
            logger.info(f"  Next action: {decision.next_action}")

            state.phase = "memorizing"
            memory_record = self._create_memory(
                round_id=round_id,
                candidate=candidate,
                verification_result=latest_verification,
                decision=decision,
            )
            state.memory_records.append(memory_record)
            self.memory.add(memory_record, task_id=self.task.task_id)

            candidate_score = self._score_candidate(decision, latest_verification)
            if candidate_score > round_best_score:
                round_best_score = candidate_score
                round_best_candidate = candidate
            if candidate_score > self.best_score:
                self.best_score = candidate_score
                self.best_candidate = candidate

            if (
                latest_verification is not None
                and latest_verification.tier in {"L2", "L3"}
                and latest_verification.status == "pass"
                and decision.decision == "accept"
            ):
                state.best_candidate_id = candidate.candidate_id
                state.phase = "completed"
                state.budget_used = len(state.candidates)
                return state

        state.best_candidate_id = round_best_candidate.candidate_id if round_best_candidate else None
        state.phase = "completed"
        state.budget_used = len(state.candidates)
        return state

    def _run_l1_verification(
        self,
        candidate: CandidateDesignFamily,
        screen_result,
    ) -> VerificationResult:
        """Run L1 verification and mechanism-baseline comparison."""
        structure = candidate.structure
        electrical = candidate.electrical
        epsilon = electrical.epsilon if electrical.epsilon is not None else screen_result.tr_frequency
        if epsilon is None:
            epsilon = 1.0

        t0 = time.time()
        harv = compute_harvesting_metrics(
            alpha=structure.alpha,
            beta=structure.beta,
            delta=structure.delta,
            n_cells=structure.N,
            kappa_sq=electrical.kappa2,
            epsilon=epsilon,
            n_points=5000,
            excitation_type=(
                "acceleration"
                if self.task.excitation.type == "base_acceleration"
                else "displacement"
            ),
            excitation_amplitude=self.task.excitation.amplitude,
        )
        mechanism_baseline = compute_harvesting_metrics(
            alpha=structure.alpha,
            beta=structure.beta,
            delta=1.0,
            n_cells=structure.N,
            kappa_sq=electrical.kappa2,
            epsilon=epsilon,
            n_points=5000,
            excitation_type=(
                "acceleration"
                if self.task.excitation.type == "base_acceleration"
                else "displacement"
            ),
            excitation_amplitude=self.task.excitation.amplitude,
        )
        runtime = time.time() - t0

        output_cmp = build_output_comparison(
            self.task.harvesting_requirements,
            normalized=True,
            tr_voltage_peak=harv.voltage_tr,
            mechanism_voltage_peak=mechanism_baseline.voltage_pb1,
            tr_power=harv.power_tr,
            mechanism_power=mechanism_baseline.power_pb1,
            tr_current_peak=harv.current_tr,
            mechanism_current_peak=mechanism_baseline.current_pb1,
        )

        eta_status = "pass" if harv.eta_tr >= 0.5 else ("warn" if harv.eta_tr >= 0.3 else "fail")
        transmission_status = "pass" if harv.transmission_tr_dB < 0 else "fail"
        mechanism_status = ratio_status(output_cmp.mechanism_ratio)
        primary_status = threshold_status(output_cmp.tr_value, None, normalized=True)
        pef_status = "pass" if harv.pef >= 100 else ("warn" if harv.pef >= 50 else "fail")

        status = _combine_statuses(
            primary_status,
            mechanism_status,
            eta_status,
            transmission_status,
        )

        metrics = [
            MetricValue(label="TR Exists", value="Yes", status="pass"),
            MetricValue(label="Omega_TR", value=harv.omega_tr, unit="Ω"),
            MetricValue(
                label=output_cmp.label,
                value=output_cmp.tr_value,
                unit=output_cmp.unit,
                status=primary_status,
            ),
            MetricValue(
                label="MechanismRatio",
                value=output_cmp.mechanism_ratio,
                unit="x",
                status=mechanism_status,
            ),
            MetricValue(label="PEF", value=harv.pef, unit="x", status=pef_status),
            MetricValue(label="P(TR)", value=harv.power_tr, unit="arb."),
            MetricValue(label="V(TR)", value=harv.voltage_tr, unit="arb."),
            MetricValue(label="I(TR)", value=harv.current_tr, unit="arb."),
            MetricValue(
                label="I_rectified(TR)",
                value=harv.rectified_current_tr,
                unit="arb.",
                status="pass",
            ),
            MetricValue(label="eta", value=harv.eta_tr, status=eta_status),
            MetricValue(
                label="T(Omega_TR)",
                value=harv.transmission_tr_dB,
                unit="dB",
                status=transmission_status,
            ),
        ]

        log_lines = [
            f"[L1] Candidate {candidate.candidate_id}",
            f"[L1] Ω_TR={harv.omega_tr:.6f}",
            f"[L1] Primary output={output_cmp.tr_value:.6f} {output_cmp.unit}",
            f"[L1] Mechanism ratio={output_cmp.mechanism_ratio:.4f}",
            f"[L1] PEF={harv.pef:.2f}",
            f"[L1] eta={harv.eta_tr:.4f}",
            f"[L1] T(Ω_TR)={harv.transmission_tr_dB:.2f} dB",
        ]

        return VerificationResult(
            candidate_id=candidate.candidate_id,
            tier="L1",
            status=status,
            metrics=metrics,
            details=(
                f"L1 complete. Primary output={output_cmp.tr_value:.6f} {output_cmp.unit}, "
                f"mechanism ratio={output_cmp.mechanism_ratio:.4f}, "
                f"PEF={harv.pef:.2f}, eta={harv.eta_tr:.4f}, "
                f"T(Ω_TR)={harv.transmission_tr_dB:.2f} dB."
            ),
            log="\n".join(log_lines),
            runtime_seconds=runtime,
        )

    def _run_l2_verification(self, candidate: CandidateDesignFamily) -> VerificationResult:
        """Run L2 verification with mechanism and engineering baselines."""
        design = self.translator.translate(candidate)
        excitation_type, excitation_amplitude = self._physical_excitation_for_l2()
        f_low, f_high = self.task.frequency_target.band_of_interest
        f_min = max(1.0, f_low * 0.2)
        f_max = max(f_high * 2.0, 3000.0)
        selected_load, load_notes = self._select_l2_load(
            design=design,
            excitation_type=excitation_type,
            excitation_amplitude=excitation_amplitude,
            f_min=f_min,
            f_max=f_max,
        )

        t0 = time.time()
        metrics = compute_beam_harvesting_metrics(
            design.mat_A,
            design.mat_B,
            design.geom,
            design.piezo,
            design.L_A,
            design.L_B,
            design.n_cells,
            selected_load,
            f_min=f_min,
            f_max=f_max,
            n_points_bandgap=500,
            n_points_sweep=240,
            target_band=self.task.frequency_target.band_of_interest,
            excitation_type=excitation_type,
            excitation_amplitude=excitation_amplitude,
            boundary_mass_factor=design.boundary_mass_factor,
        )
        baselines = compute_dual_baseline(
            design.mat_A,
            design.mat_B,
            design.geom,
            design.piezo,
            design.L_A,
            design.L_B,
            design.n_cells,
            selected_load,
            boundary_mass_factor=design.boundary_mass_factor,
            f_max=f_max,
            n_points=240,
            target_band=self.task.frequency_target.band_of_interest,
            excitation_type=excitation_type,
            excitation_amplitude=excitation_amplitude,
        )
        runtime = time.time() - t0

        output_cmp = build_output_comparison(
            self.task.harvesting_requirements,
            normalized=False,
            tr_voltage_peak=baselines.voltage_tr,
            mechanism_voltage_peak=baselines.voltage_pb1,
            tr_power=baselines.power_tr,
            mechanism_power=baselines.power_pb1,
            tr_current_peak=baselines.current_tr,
            mechanism_current_peak=baselines.current_pb1,
            engineering_voltage_peak=baselines.voltage_conventional,
            engineering_power=baselines.power_conventional,
            engineering_current_peak=baselines.current_conventional,
        )

        primary_status = threshold_status(
            output_cmp.tr_value,
            self.task.harvesting_requirements.minimum_output,
            normalized=False,
        )
        mechanism_status = ratio_status(output_cmp.mechanism_ratio)
        engineering_status = ratio_status(output_cmp.engineering_ratio)
        transmission_status = "pass" if metrics.transmission_tr_dB < 0 else "fail"

        mass_lock_error = _relative_error(baselines.total_mass_tr, baselines.total_mass_conv)
        length_lock_error = _relative_error(baselines.total_length_tr, baselines.total_length_conv)
        piezo_lock_error = _relative_error(baselines.piezo_volume_tr, baselines.piezo_volume_conv)
        lock_status = "pass" if max(mass_lock_error, length_lock_error, piezo_lock_error) < 1e-6 else "warn"

        status = _combine_statuses(
            primary_status,
            mechanism_status,
            engineering_status,
            transmission_status,
        )

        metrics_out = [
            MetricValue(label="f_TR", value=metrics.f_tr, unit="Hz"),
            MetricValue(label="R_load", value=selected_load, unit="Ohm"),
            MetricValue(
                label=output_cmp.label,
                value=output_cmp.tr_value,
                unit=output_cmp.unit,
                status=primary_status,
            ),
            MetricValue(
                label="MechanismRatio",
                value=output_cmp.mechanism_ratio,
                unit="x",
                status=mechanism_status,
            ),
            MetricValue(
                label="EngineeringRatio",
                value=output_cmp.engineering_ratio or 0.0,
                unit="x",
                status=engineering_status,
            ),
            MetricValue(label="PEF", value=baselines.pef_mechanism, unit="x"),
            MetricValue(label="CEF", value=baselines.cef_mechanism, unit="x"),
            MetricValue(label="P(TR)", value=metrics.power_tr, unit="W"),
            MetricValue(label="V(TR)", value=metrics.voltage_tr, unit="V"),
            MetricValue(label="I(TR)", value=metrics.current_tr, unit="A"),
            MetricValue(
                label="I_rectified(TR)",
                value=metrics.rectified_current_tr,
                unit="A",
            ),
            MetricValue(
                label="T(f_TR)",
                value=metrics.transmission_tr_dB,
                unit="dB",
                status=transmission_status,
            ),
            MetricValue(label="MassLockError", value=mass_lock_error, unit="", status=lock_status),
            MetricValue(label="LengthLockError", value=length_lock_error, unit="", status=lock_status),
            MetricValue(label="PiezoLockError", value=piezo_lock_error, unit="", status=lock_status),
        ]

        assumption_text = " ".join((*design.assumptions, *load_notes))
        return VerificationResult(
            candidate_id=candidate.candidate_id,
            tier="L2",
            status=status,
            metrics=metrics_out,
            details=(
                f"L2 beam verification complete. Primary output={output_cmp.tr_value:.6g} {output_cmp.unit}, "
                f"mechanism ratio={output_cmp.mechanism_ratio:.4f}, "
                f"engineering ratio={(output_cmp.engineering_ratio or 0.0):.4f}, "
                f"T(f_TR)={metrics.transmission_tr_dB:.2f} dB, "
                f"R_load={selected_load:.3g} Ohm. "
                f"Assumptions: {assumption_text}"
            ),
            log="\n".join(
                [
                    f"[L2] Candidate {candidate.candidate_id}",
                    f"[L2] f_TR={metrics.f_tr:.3f} Hz",
                    f"[L2] R_load={selected_load:.3g} Ohm",
                    f"[L2] Mechanism ratio={output_cmp.mechanism_ratio:.4f}",
                    f"[L2] Engineering ratio={(output_cmp.engineering_ratio or 0.0):.4f}",
                    f"[L2] P(TR)={metrics.power_tr:.6e} W",
                    f"[L2] I(TR)={metrics.current_tr:.6e} A",
                    f"[L2] T(f_TR)={metrics.transmission_tr_dB:.2f} dB",
                    f"[L2] Translator assumptions: {assumption_text}",
                ]
            ),
            runtime_seconds=runtime,
        )

    def _l3_available(self) -> bool:
        """Check whether the COMSOL Python bridge can be used."""
        return (
            importlib.util.find_spec("mph") is not None
            and self.task.excitation.type == "base_acceleration"
        )

    def _run_l3_verification(self, candidate: CandidateDesignFamily) -> VerificationResult | None:
        """Run the optional COMSOL-backed L3 verification."""
        from veh_scientist.analysis import primary_output_value
        from veh_scientist.verifiers.l3_comsol.periodic_beam_comsol import (
            PeriodicBeamCOMSOLConfig,
            build_and_run_periodic_beam,
        )

        design = self.translator.translate(candidate)
        excitation_type, excitation_amplitude = self._physical_excitation_for_l2()
        if excitation_type != "acceleration":
            return None

        f_low, f_high = self.task.frequency_target.band_of_interest
        f_min = max(1.0, f_low * 0.2)
        f_max = max(f_high * 2.0, 3000.0)
        config = PeriodicBeamCOMSOLConfig(
            n_cells=min(design.n_cells, 5),
            L_A=design.L_A,
            L_B=design.L_B,
            beam_width=design.geom.b,
            beam_height=design.geom.h,
            piezo_thickness=design.piezo.h,
            E_A=design.mat_A.E,
            nu_A=design.mat_A.nu,
            rho_A=design.mat_A.rho,
            E_B=design.mat_B.E,
            nu_B=design.mat_B.nu,
            rho_B=design.mat_B.rho,
            piezo_E=design.piezo.E,
            piezo_rho=design.piezo.rho,
            load_resistance_ohm=design.R_load,
            a_exc=excitation_amplitude,
            f_min=f_min,
            f_max=f_max,
            n_freq=80,
            n_eigs=20,
        )

        t0 = time.time()
        result = build_and_run_periodic_beam(
            config,
            save_path=str(self.output_dir / f"{candidate.candidate_id}_periodic_beam.mph"),
            cores=1,
        )
        runtime = time.time() - t0

        freqs = np.asarray(result["frequency_hz"], dtype=float)
        voltage = np.asarray(result["voltage_v"], dtype=float)
        power = np.asarray(result["power_w"], dtype=float)
        max_disp = np.asarray(result["max_disp_m"], dtype=float)
        if freqs.size == 0:
            return VerificationResult(
                candidate_id=candidate.candidate_id,
                tier="L3",
                status="fail",
                details="COMSOL returned an empty response.",
                log="[L3] No frequency samples were returned by COMSOL.",
                runtime_seconds=runtime,
            )

        band_mask = (freqs >= f_low) & (freqs <= f_high)
        if np.any(band_mask) and float(np.max(power[band_mask])) > 0:
            best_index = int(np.argmax(power * band_mask.astype(float)))
        else:
            best_index = int(np.argmax(power))

        f_tr = float(freqs[best_index])
        voltage_tr = float(abs(voltage[best_index]))
        power_tr = float(power[best_index])
        current_tr = float(voltage_tr / max(config.load_resistance_ohm, 1e-30))
        primary_output = primary_output_value(
            self.task.harvesting_requirements,
            voltage_peak=voltage_tr,
            power=power_tr,
            current_peak=current_tr,
        )
        primary_status = threshold_status(
            primary_output,
            self.task.harvesting_requirements.minimum_output,
            normalized=False,
        )
        band_status = "pass" if f_low <= f_tr <= f_high else "warn"
        status = _combine_statuses(primary_status, band_status)

        metrics_out = [
            MetricValue(label="f_TR", value=f_tr, unit="Hz", status=band_status),
            MetricValue(
                label="PrimaryOutput(TR)",
                value=primary_output,
                unit=self.task.harvesting_requirements.minimum_output_unit,
                status=primary_status,
            ),
            MetricValue(label="P(TR)", value=power_tr, unit="W"),
            MetricValue(label="V(TR)", value=voltage_tr, unit="V"),
            MetricValue(label="I(TR)", value=current_tr, unit="A"),
            MetricValue(
                label="PeakDisp(TR)",
                value=float(max_disp[best_index]) if max_disp.size > best_index else 0.0,
                unit="m",
                status="pass",
            ),
        ]
        return VerificationResult(
            candidate_id=candidate.candidate_id,
            tier="L3",
            status=status,
            metrics=metrics_out,
            details=(
                f"L3 COMSOL verification complete. f_TR={f_tr:.3f} Hz, "
                f"primary output={primary_output:.6g} {self.task.harvesting_requirements.minimum_output_unit}, "
                f"P(TR)={power_tr:.6e} W."
            ),
            log="\n".join(
                [
                    f"[L3] Candidate {candidate.candidate_id}",
                    f"[L3] f_TR={f_tr:.3f} Hz",
                    f"[L3] P(TR)={power_tr:.6e} W",
                    f"[L3] V(TR)={voltage_tr:.6e} V",
                    f"[L3] I(TR)={current_tr:.6e} A",
                ]
            ),
            runtime_seconds=runtime,
        )

    def _create_memory(
        self,
        round_id: int,
        candidate: CandidateDesignFamily,
        verification_result: VerificationResult | None,
        decision: CriticDecision,
    ) -> MemoryRecord:
        """Create a structured memory record from one candidate evaluation."""
        if decision.decision == "accept":
            category = "motif"
            observation = f"{candidate.candidate_id} accepted for {self.task.harvesting_requirements.target_output}"
        elif decision.decision in {"revise", "switch_family"}:
            category = "strategy"
            observation = decision.reason
        else:
            category = "failure"
            observation = decision.reason

        if verification_result is not None:
            observation = f"{observation} [{verification_result.tier}:{verification_result.status}]"

        return MemoryRecord(
            round_id=round_id,
            category=category,
            observation=observation,
            interpretation=decision.reason,
            next_step=decision.next_action,
            tags=[
                f"round_{round_id}",
                f"source_{candidate.source}",
                f"delta_{candidate.structure.delta:.2f}",
                decision.decision,
            ],
            source_candidate_id=candidate.candidate_id,
        )

    def _suggest_next_params(
        self,
        current: dict[str, Any],
        round_state: RoundState,
    ) -> dict[str, Any]:
        """Suggest seed parameters for the next round."""
        params = dict(current)
        if not round_state.best_candidate_id:
            return params

        best_candidate = next(
            (c for c in round_state.candidates if c.candidate_id == round_state.best_candidate_id),
            None,
        )
        if best_candidate is None:
            return params

        params.update(
            {
                "alpha": best_candidate.structure.alpha,
                "beta": best_candidate.structure.beta,
                "delta": best_candidate.structure.delta,
                "N": best_candidate.structure.N,
                "kappa2": best_candidate.electrical.kappa2,
                "epsilon": best_candidate.electrical.epsilon,
            }
        )

        decision = next(
            (d for d in reversed(round_state.critic_decisions) if d.candidate_id == best_candidate.candidate_id),
            None,
        )
        if decision is None:
            return params

        reason_lower = decision.reason.lower()
        action_lower = decision.next_action.lower()
        if decision.decision == "revise":
            if "suppression" in reason_lower or "gap edge" in action_lower:
                params["delta"] = 1.0 + 0.7 * (params["delta"] - 1.0)
                params["kappa2"] = max(params["kappa2"] * 0.85, 0.01)
            if "localization" in reason_lower or "increase n" in action_lower:
                params["delta"] = min(params["delta"] * 1.2, 3.0)
                params["N"] = min(params["N"] + 4, 30)
            if "engineering baseline" in reason_lower or "current" in action_lower:
                params["kappa2"] = min(params["kappa2"] * 1.3, 0.2)
                params["beta"] = min(max(params["beta"] * 0.9, 0.2), 4.0)
        elif decision.decision in {"switch_family", "abandon"}:
            params["alpha"] = 0.75 if params["alpha"] == 1.0 else 1.0
            params["beta"] = 0.35 if params["beta"] >= 0.5 else 0.8
            params["delta"] = 2.0 if params["delta"] <= 1.5 else 0.6
            params["N"] = 12
            params["kappa2"] = 0.04

        return params

    def _physical_excitation_for_l2(self) -> tuple[str, float]:
        """Convert task excitation to the physical units expected by L2."""
        exc = self.task.excitation
        if exc.type == "base_acceleration":
            amplitude = exc.amplitude
            if exc.amplitude_unit.lower() == "g":
                amplitude *= 9.81
            return "acceleration", amplitude

        amplitude = exc.amplitude
        if exc.amplitude_unit.lower() == "mm":
            amplitude /= 1000.0
        return "displacement", amplitude

    def _select_l2_load(
        self,
        *,
        design,
        excitation_type: str,
        excitation_amplitude: float,
        f_min: float,
        f_max: float,
    ) -> tuple[float, tuple[str, ...]]:
        """Select the L2 resistive load when the task leaves it open."""
        fixed_load = self.task.harvesting_requirements.load_value
        if fixed_load is not None:
            return float(fixed_load), (
                f"Used fixed task load R={float(fixed_load):.3g} Ohm without L2 load sweep.",
            )

        best_load = float(design.R_load)
        best_score = float("-inf")

        for trial_load in self._candidate_l2_loads(best_load):
            trial = compute_beam_harvesting_metrics(
                design.mat_A,
                design.mat_B,
                design.geom,
                design.piezo,
                design.L_A,
                design.L_B,
                design.n_cells,
                trial_load,
                f_min=f_min,
                f_max=f_max,
                n_points_bandgap=240,
                n_points_sweep=160,
                target_band=self.task.frequency_target.band_of_interest,
                excitation_type=excitation_type,
                excitation_amplitude=excitation_amplitude,
                boundary_mass_factor=design.boundary_mass_factor,
            )
            trial_output = primary_output_value(
                self.task.harvesting_requirements,
                voltage_peak=trial.voltage_tr,
                power=trial.power_tr,
                current_peak=trial.current_tr,
            )
            mechanism_output = primary_output_value(
                self.task.harvesting_requirements,
                voltage_peak=trial.voltage_pb1,
                power=trial.power_pb1,
                current_peak=trial.current_pb1,
            )
            mechanism_ratio = 0.0
            if mechanism_output > 0:
                mechanism_ratio = trial_output / mechanism_output

            score = trial_output * max(mechanism_ratio, 0.05)
            if trial.f_tr <= 0 or trial_output <= 0:
                score = float("-inf")
            elif trial.transmission_tr_dB > 0:
                score *= 0.1

            if score > best_score:
                best_score = score
                best_load = trial_load

        if best_score == float("-inf"):
            return float(design.R_load), (
                f"L2 load sweep found no viable TR response; fell back to heuristic R={float(design.R_load):.3g} Ohm.",
            )

        return best_load, (
            f"Auto-selected R={best_load:.3g} Ohm from an L2 load sweep for the {self.task.harvesting_requirements.target_output} objective.",
        )

    def _candidate_l2_loads(self, seed_load: float) -> list[float]:
        """Candidate loads used for open-load L2 verification."""
        target_output = self.task.harvesting_requirements.target_output
        if target_output == "current":
            loads = [3.0e1, 1.0e2, 3.0e2, 1.0e3, 3.0e3, 1.0e4, 3.0e4]
        elif target_output == "voltage":
            loads = [1.0e4, 3.0e4, 1.0e5, 3.0e5, 1.0e6, 3.0e6, 1.0e7]
        else:
            loads = [1.0e3, 3.0e3, 1.0e4, 3.0e4, 1.0e5, 3.0e5, 1.0e6]

        loads.append(float(seed_load))
        unique_loads = {round(load, 12) for load in loads if load > 0}
        return sorted(unique_loads)

    @staticmethod
    def _log_metrics(metrics: list[MetricValue]) -> None:
        for metric in metrics:
            value = metric.value
            if isinstance(value, float):
                value = _format_metric_scalar(value)
            logger.info(f"    {metric.label}: {value} [{metric.status}]")

    def _update_best_pef(self, verification_result: VerificationResult) -> None:
        """Track the best PEF observed across all verification tiers."""
        pef = self._extract_metric_value(verification_result.metrics, "PEF")
        if pef is not None:
            self.best_pef = max(self.best_pef, pef)

    @staticmethod
    def _score_candidate(
        decision: CriticDecision,
        verification_result: VerificationResult | None,
    ) -> float:
        """Rank candidates by baseline ratios, suppression, and critic outcome."""
        score = 0.0
        if verification_result is None:
            return score

        mechanism_ratio = _extract_metric_value_from_list(verification_result.metrics, "MechanismRatio") or 0.0
        engineering_ratio = _extract_metric_value_from_list(verification_result.metrics, "EngineeringRatio") or 0.0
        eta = _extract_metric_value_from_list(verification_result.metrics, "eta") or 0.0
        transmission = _extract_metric_value_from_list(verification_result.metrics, "T(Omega_TR)")
        if transmission is None:
            transmission = _extract_metric_value_from_list(verification_result.metrics, "T(f_TR)") or 0.0

        score += 10.0 * mechanism_ratio
        score += 20.0 * engineering_ratio
        score += 5.0 * eta
        score -= 3.0 * max(transmission, 0.0)

        if verification_result.status == "pass":
            score += 20.0
        elif verification_result.status == "partial":
            score += 5.0

        if decision.decision == "accept":
            score += 30.0
        elif decision.decision == "switch_family":
            score -= 10.0
        elif decision.decision == "abandon":
            score -= 20.0

        return score

    def _extract_metric_value(self, metrics: list[MetricValue], label: str) -> float | None:
        return _extract_metric_value_from_list(metrics, label)

    def _save_report(self) -> None:
        """Save a JSON report of all rounds."""
        report_path = self.output_dir / "report.json"
        report = {
            "task_id": self.task.task_id,
            "total_rounds": len(self.rounds),
            "best_candidate": asdict(self.best_candidate) if self.best_candidate else None,
            "best_pef": self.best_pef,
            "rounds": [
                {
                    "round_id": round_state.round_id,
                    "phase": round_state.phase,
                    "best_candidate_id": round_state.best_candidate_id,
                    "candidates": [asdict(candidate) for candidate in round_state.candidates],
                    "screen_results": [
                        {
                            "candidate_id": result.candidate_id,
                            "verdict": result.verdict,
                            "tr_frequency": result.tr_frequency,
                            "eta": result.eta,
                        }
                        for result in round_state.screen_results
                    ],
                    "verification_results": [
                        {
                            "candidate_id": result.candidate_id,
                            "tier": result.tier,
                            "status": result.status,
                            "metrics": [asdict(metric) for metric in result.metrics],
                        }
                        for result in round_state.verification_results
                    ],
                    "critic_decisions": [asdict(decision) for decision in round_state.critic_decisions],
                    "memory_records": [asdict(record) for record in round_state.memory_records],
                }
                for round_state in self.rounds
            ],
        }
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Report saved to {report_path}")


def _combine_statuses(*statuses: str) -> str:
    if all(status == "pass" for status in statuses):
        return "pass"
    if any(status == "fail" for status in statuses):
        return "fail"
    return "partial"


def _relative_error(lhs: float, rhs: float) -> float:
    denom = max(abs(lhs), 1e-30)
    return abs(lhs - rhs) / denom


def _extract_metric_value_from_list(metrics: list[MetricValue], label: str) -> float | None:
    metric = next((item for item in metrics if item.label == label), None)
    if metric is None:
        return None
    if isinstance(metric.value, (int, float)):
        return float(metric.value)
    try:
        return float(str(metric.value).replace("x", "").strip())
    except ValueError:
        return None


def _format_metric_scalar(value: float) -> str:
    if value == 0:
        return "0"
    abs_value = abs(value)
    if abs_value < 1e-4 or abs_value >= 1e4:
        return f"{value:.6e}"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="VEH Scientist — objective-aligned research loop"
    )
    parser.add_argument("--task", type=str, required=True, help="Path to task card YAML file")
    parser.add_argument("--rounds", type=int, default=3, help="Maximum number of rounds")
    parser.add_argument("--output", type=str, default="results/runs", help="Output directory")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
        stream=sys.stdout,
    )

    task = parse_task_card(args.task)
    issues = validate_task_card(task)
    if issues:
        logger.error("Task card validation failed:")
        for issue in issues:
            logger.error(f"  - {issue}")
        sys.exit(1)

    loop = ResearchLoop(task=task, max_rounds=args.rounds, output_dir=args.output)
    rounds = loop.run()

    print(f"\n{'=' * 60}")
    print("  RESEARCH COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Rounds executed: {len(rounds)}")
    print(f"  Best PEF: {loop.best_pef:.2f}")
    if loop.best_candidate:
        print(f"  Best candidate: {loop.best_candidate.candidate_id}")
    print(f"  Report: {loop.output_dir / 'report.json'}")


if __name__ == "__main__":
    main()
