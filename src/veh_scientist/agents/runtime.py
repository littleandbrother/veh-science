"""Agent-message runtime for role and multi-LLM dashboard views."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from veh_scientist.agents.config import AgentConfigStore
from veh_scientist.agents.definitions import (
    AgentSlotDefinition,
    ROLE_SLOT_DEFINITIONS,
    LLM_SLOT_DEFINITIONS,
)
from veh_scientist.agents.providers import ProviderError, generate_text
from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    CriticDecision,
    MemoryRecord,
    MetricValue,
    MechanismScreenResult,
    RoundState,
    TaskCard,
    VerificationResult,
)


@dataclass(frozen=True)
class RoundAgentContext:
    """Compact round context used for prompt generation."""

    task: TaskCard
    round_state: RoundState
    candidate: CandidateDesignFamily | None
    screen: MechanismScreenResult | None
    decision: CriticDecision | None
    memory: MemoryRecord | None
    verifications: dict[str, VerificationResult]
    guidance_notes: tuple[str, ...]


class AgentRuntime:
    """Generate UI messages either locally or through configured remote slots."""

    def __init__(self, config_store: AgentConfigStore | None = None) -> None:
        self.config_store = config_store or AgentConfigStore()

    def build_role_messages(self, context: RoundAgentContext) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [self._coordinator_message(context)]
        remote_outputs = self._generate_slot_group_outputs(ROLE_SLOT_DEFINITIONS, context)
        for slot in ROLE_SLOT_DEFINITIONS:
            content = remote_outputs.get(slot.slot_id) or self._fallback_role_message(slot, context)
            messages.append(
                {
                    "agent": slot.agent_name,
                    "type": "normal",
                    "content": content,
                }
            )
        if context.memory is not None:
            messages.append(
                {
                    "agent": "Coordinator",
                    "type": "system",
                    "content": f"Memory recorded as {context.memory.memory_id}: {context.memory.observation}",
                    "refs": [{"type": "memory", "text": context.memory.memory_id}],
                }
            )
        return messages

    def build_multi_llm_messages(self, context: RoundAgentContext) -> list[dict[str, Any]]:
        remote_outputs = self._generate_slot_group_outputs(LLM_SLOT_DEFINITIONS, context)
        messages: list[dict[str, Any]] = []
        for slot in LLM_SLOT_DEFINITIONS:
            content = remote_outputs.get(slot.slot_id) or self._fallback_llm_message(slot, context)
            messages.append(
                {
                    "agent": slot.agent_name,
                    "type": "normal",
                    "content": content,
                }
            )
        return messages

    def _generate_slot_group_outputs(
        self,
        slots: tuple[AgentSlotDefinition, ...],
        context: RoundAgentContext,
    ) -> dict[str, str]:
        grouped: dict[tuple[str, str, str, str], list[AgentSlotDefinition]] = {}
        for slot in slots:
            config = self.config_store.get(slot.slot_id)
            if not config.normalized().enabled:
                continue
            grouped.setdefault(config.fingerprint(), []).append(slot)

        outputs: dict[str, str] = {}
        for fingerprint, slot_group in grouped.items():
            config = self.config_store.get(slot_group[0].slot_id)
            try:
                batch_outputs = self._generate_batch(slot_group, config=config, context=context)
            except ProviderError:
                continue
            outputs.update(batch_outputs)
        return outputs

    def _generate_batch(
        self,
        slot_group: list[AgentSlotDefinition],
        *,
        config,
        context: RoundAgentContext,
    ) -> dict[str, str]:
        system_prompt = (
            "You are generating short dashboard utterances for a scientific design cockpit. "
            "Return valid JSON only. Each value must be 1-3 concise sentences, technically grounded, and specific to the provided context."
        )
        slot_instructions = "\n".join(
            f"- {slot.slot_id}: {slot.prompt_brief} Agent label: {slot.agent_name}."
            for slot in slot_group
        )
        user_prompt = (
            f"{self._context_header(context)}\n\n"
            f"Slots to fill:\n{slot_instructions}\n\n"
            "Return a JSON object whose keys are the slot ids and whose values are the agent messages."
        )
        raw = generate_text(
            config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=60.0,
            max_tokens=1400,
        )
        parsed = _parse_json_object(raw)
        return {
            slot.slot_id: str(parsed[slot.slot_id]).strip()
            for slot in slot_group
            if slot.slot_id in parsed and str(parsed[slot.slot_id]).strip()
        }

    def _context_header(self, context: RoundAgentContext) -> str:
        candidate = context.candidate
        screen = context.screen
        decision = context.decision
        verifications = "\n".join(
            f"- {tier}: {self._verification_line(result)}"
            for tier, result in sorted(context.verifications.items())
        ) or "- none"
        guidance = "\n".join(f"- {note}" for note in context.guidance_notes[-5:]) or "- none"
        candidate_line = "No candidate selected."
        if candidate is not None:
            candidate_line = (
                f"{candidate.candidate_id}: alpha={candidate.structure.alpha}, "
                f"beta={candidate.structure.beta}, delta={candidate.structure.delta}, "
                f"N={candidate.structure.N}, kappa2={candidate.electrical.kappa2}."
            )
        screen_line = "No screening result."
        if screen is not None:
            failed_gates = [f"G{gate.gate_id}" for gate in screen.gates if not gate.passed]
            gate_text = ", ".join(failed_gates) if failed_gates else "none"
            screen_line = (
                f"Screen verdict={screen.verdict}; TR={_fmt_optional(screen.tr_frequency)} Hz; "
                f"eta={_fmt_optional(screen.eta)}; failed gates={gate_text}."
            )
        decision_line = "No critic decision."
        if decision is not None:
            decision_line = f"Decision={decision.decision}; reason={decision.reason}; next={decision.next_action}"
        return (
            f"Task: {context.task.description or context.task.task_id}\n"
            f"Round: {context.round_state.round_id}\n"
            f"Target output: {context.task.harvesting_requirements.target_output}\n"
            f"Target band: {context.task.frequency_target.band_of_interest[0]:.1f}-{context.task.frequency_target.band_of_interest[1]:.1f} Hz\n"
            f"Candidate: {candidate_line}\n"
            f"Screening: {screen_line}\n"
            f"Verification:\n{verifications}\n"
            f"Critic: {decision_line}\n"
            f"Recent user guidance:\n{guidance}"
        )

    def _coordinator_message(self, context: RoundAgentContext) -> dict[str, Any]:
        guidance_suffix = ""
        if context.guidance_notes:
            guidance_suffix = f" Latest guidance: {context.guidance_notes[-1]}"
        return {
            "agent": "Coordinator",
            "type": "system",
            "content": (
                f"Round {context.round_state.round_id} executed from the real research loop."
                f" Candidate count: {len(context.round_state.candidates)}."
                f"{guidance_suffix}"
            ).strip(),
        }

    def _fallback_role_message(self, slot: AgentSlotDefinition, context: RoundAgentContext) -> str:
        candidate = context.candidate
        screen = context.screen
        decision = context.decision
        if slot.slot_id == "structure":
            if candidate is None:
                return "No candidate was selected in this round."
            return (
                f"Selected {candidate.candidate_id} with alpha={candidate.structure.alpha}, "
                f"beta={candidate.structure.beta}, delta={candidate.structure.delta}, "
                f"N={candidate.structure.N}, and kappa2={candidate.electrical.kappa2}. "
                f"Assumptions: {'; '.join(candidate.assumptions) if candidate.assumptions else 'none'}"
            )
        if slot.slot_id == "mechanism":
            if screen is None:
                return "Mechanism screening has not produced any result yet."
            gate_summary = ", ".join(
                f"G{gate.gate_id}={'pass' if gate.passed else 'revise'}"
                for gate in screen.gates
            )
            return (
                f"Mechanism verdict is {screen.verdict}. Gate summary: {gate_summary}. "
                f"TR={_fmt_optional(screen.tr_frequency)} Hz, eta={_fmt_optional(screen.eta)}."
            )
        if slot.slot_id == "verifier":
            if not context.verifications:
                return "No verification tier has run yet."
            return " ".join(
                self._verification_line(result)
                for _, result in sorted(context.verifications.items())
            )
        if slot.slot_id == "critic":
            if decision is None:
                return "No critic decision is available."
            return f"Decision is {decision.decision}. {decision.reason} Next: {decision.next_action}"
        if slot.slot_id == "paper":
            mechanism_hint = "TR-enabled localization can improve harvesting only if suppression margin survives."
            if candidate is not None and candidate.assumptions:
                mechanism_hint = candidate.assumptions[0]
            return (
                f"Literature-style note: {mechanism_hint} "
                "The main uncertainty remains whether the localized mode keeps engineering-level output gains."
            )
        return slot.purpose

    def _fallback_llm_message(self, slot: AgentSlotDefinition, context: RoundAgentContext) -> str:
        candidate = context.candidate
        candidate_label = candidate.candidate_id if candidate is not None else "no candidate"
        decision = context.decision.decision if context.decision is not None else "no decision"
        if slot.slot_id == "claude_scientist":
            return (
                f"The current round centers on {candidate_label}. The main unresolved issue is whether the evidence is strong enough beyond screening to justify {decision}."
            )
        if slot.slot_id == "grok_scientist":
            return (
                f"A contrarian read: {candidate_label} may simply be sitting on a fragile TR configuration. I would challenge the suppression margin and gap-depth assumptions first."
            )
        if slot.slot_id == "deepseek_scientist":
            return (
                f"Search direction: rank delta, N, and kappa2 as the next tuning knobs for {candidate_label}. Push the parameter that most directly improves the failing metric."
            )
        if slot.slot_id == "gemini_scientist":
            return (
                f"Evidence summary for {candidate_label}: screening plus verification suggest {decision}. The next step should close the highest-fidelity evidence gap."
            )
        if slot.slot_id == "qwen_scientist":
            return (
                f"Implementation view: {candidate_label} is useful only if the parameter move is fabricable and keeps baseline advantages. Prioritize the smallest structural change that addresses the failing gate."
            )
        return (
            f"Round synthesis: {candidate_label} currently leads this round, with critic outcome {decision}. The next move should stay aligned with the requested output objective."
        )

    @staticmethod
    def _verification_line(result: VerificationResult) -> str:
        metric_summary = ", ".join(
            f"{metric.label}={_fmt_metric(metric)}"
            for metric in result.metrics[:4]
        )
        return f"{result.tier} {result.status}. {result.details or metric_summary}".strip()


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError("Provider did not return valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("Provider returned JSON but not an object.")
    return parsed


def _fmt_metric(metric: MetricValue) -> str:
    if isinstance(metric.value, float):
        rendered = f"{metric.value:.4g}"
    else:
        rendered = str(metric.value)
    if metric.unit:
        rendered = f"{rendered} {metric.unit}"
    return rendered


def _fmt_optional(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4g}"
