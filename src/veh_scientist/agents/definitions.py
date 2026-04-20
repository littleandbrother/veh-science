"""Static agent slot definitions used by the cockpit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSlotDefinition:
    """Static description of one configurable agent slot."""

    slot_id: str
    mode: str
    agent_name: str
    label: str
    purpose: str
    prompt_brief: str


ROLE_SLOT_DEFINITIONS = (
    AgentSlotDefinition(
        slot_id="mechanism",
        mode="role",
        agent_name="Mechanism",
        label="Mechanism Agent",
        purpose="Explain the screening physics and TR / bandgap logic.",
        prompt_brief="Focus on bandgaps, localization, suppression, and why a candidate passes or fails the mechanism gates.",
    ),
    AgentSlotDefinition(
        slot_id="structure",
        mode="role",
        agent_name="Structure",
        label="Structure Agent",
        purpose="Summarize candidate geometry and structural tuning decisions.",
        prompt_brief="Focus on alpha, beta, delta, N, and how the proposed structure should be revised.",
    ),
    AgentSlotDefinition(
        slot_id="critic",
        mode="role",
        agent_name="Critic",
        label="Critic Agent",
        purpose="Judge risk, baseline gaps, and next action.",
        prompt_brief="Focus on the main technical risk, decision rationale, and the most valuable next action.",
    ),
    AgentSlotDefinition(
        slot_id="paper",
        mode="role",
        agent_name="Paper",
        label="Paper Agent",
        purpose="Produce a concise literature-style framing note.",
        prompt_brief="Frame the round like a short literature note: mechanism intuition, known tradeoff, and what evidence is still missing.",
    ),
    AgentSlotDefinition(
        slot_id="verifier",
        mode="role",
        agent_name="Verifier Planner",
        label="Verifier Planner",
        purpose="Interpret verification outputs and escalation path.",
        prompt_brief="Focus on L1/L2/L3 evidence, what has been verified, and whether higher fidelity is still needed.",
    ),
)


LLM_SLOT_DEFINITIONS = (
    AgentSlotDefinition(
        slot_id="gpt_scientist",
        mode="llm",
        agent_name="GPT-Scientist",
        label="GPT-Scientist",
        purpose="Provide a concise round-level synthesis.",
        prompt_brief="Give a balanced synthesis of the round and a practical next move.",
    ),
    AgentSlotDefinition(
        slot_id="claude_scientist",
        mode="llm",
        agent_name="Claude-Scientist",
        label="Claude-Scientist",
        purpose="Stress-test assumptions and edge cases.",
        prompt_brief="Focus on hidden assumptions, edge cases, and missing evidence.",
    ),
    AgentSlotDefinition(
        slot_id="qwen_scientist",
        mode="llm",
        agent_name="Qwen-Scientist",
        label="Qwen-Scientist",
        purpose="Summarize with implementation-oriented tradeoffs.",
        prompt_brief="Focus on engineering feasibility, implementation cost, and concrete parameter moves.",
    ),
    AgentSlotDefinition(
        slot_id="gemini_scientist",
        mode="llm",
        agent_name="Gemini-Scientist",
        label="Gemini-Scientist",
        purpose="Summarize evidence and experimental next steps.",
        prompt_brief="Focus on evidence quality, missing experiments, and what to validate next.",
    ),
    AgentSlotDefinition(
        slot_id="grok_scientist",
        mode="llm",
        agent_name="Grok-Scientist",
        label="Grok-Scientist",
        purpose="Highlight contrarian possibilities and failure modes.",
        prompt_brief="Focus on alternative interpretations and ways the current conclusion could be wrong.",
    ),
    AgentSlotDefinition(
        slot_id="deepseek_scientist",
        mode="llm",
        agent_name="Deepseek-Scientist",
        label="Deepseek-Scientist",
        purpose="Offer parameter-search style guidance.",
        prompt_brief="Focus on parameter search direction, ranking, and the highest-yield next candidate.",
    ),
)


ALL_SLOT_DEFINITIONS = {slot.slot_id: slot for slot in (*ROLE_SLOT_DEFINITIONS, *LLM_SLOT_DEFINITIONS)}


def get_slot_definition(slot_id: str) -> AgentSlotDefinition:
    """Return one slot definition or raise a descriptive error."""

    try:
        return ALL_SLOT_DEFINITIONS[slot_id]
    except KeyError as exc:
        raise KeyError(f"Unknown agent slot: {slot_id}") from exc


def list_slot_definitions(mode: str | None = None) -> list[AgentSlotDefinition]:
    """List slot definitions, optionally filtered by mode."""

    slots = list(ALL_SLOT_DEFINITIONS.values())
    if mode is None:
        return slots
    return [slot for slot in slots if slot.mode == mode]
