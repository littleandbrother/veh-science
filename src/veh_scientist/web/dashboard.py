"""Dashboard payload builders for the VEH Scientist cockpit."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from veh_scientist.agents import AgentRuntime
from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    CriticDecision,
    MemoryRecord,
    MetricValue,
    RoundState,
    TaskCard,
    VerificationResult,
)
from veh_scientist.taskcard.parser import parse_task_card
from veh_scientist.taskcard.validator import validate_task_card
from veh_scientist.coordinator.loop import ResearchLoop
from veh_scientist.agents.runtime import RoundAgentContext


DEFAULT_MOTIFS = [
    "TR Boundary Localization",
    "Impedance-Matched Electrical Load",
    "Bandgap Screening First",
    "Memory-Grounded Revision",
]


def run_dashboard_session(
    task_source: str | Path,
    rounds: int = 3,
    output_dir: str | Path = "results/runs",
    *,
    guidance_entries: list[dict[str, Any]] | None = None,
    task_title_override: str | None = None,
    agent_runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    """Run the research loop and convert the result to dashboard payload."""

    task = parse_task_card(task_source)
    issues = validate_task_card(task)
    if issues:
        raise ValueError("Task card validation failed: " + "; ".join(issues))

    runtime = agent_runtime or AgentRuntime()
    guidance_entries = guidance_entries or []
    loop = ResearchLoop(
        task=task,
        max_rounds=rounds,
        output_dir=output_dir,
        guidance_notes=[entry.get("content", "").strip() for entry in guidance_entries if entry.get("content")],
    )
    round_states = loop.run()
    return build_dashboard_payload(
        task=task,
        rounds=round_states,
        best_candidate_id=loop.best_candidate.candidate_id if loop.best_candidate else None,
        best_pef=loop.best_pef,
        guidance_entries=guidance_entries,
        task_title_override=task_title_override,
        agent_runtime=runtime,
    )


def build_dashboard_payload(
    task: TaskCard,
    rounds: list[RoundState],
    best_candidate_id: str | None,
    best_pef: float,
    *,
    guidance_entries: list[dict[str, Any]] | None = None,
    task_title_override: str | None = None,
    agent_runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    """Convert round states to the existing frontend dashboard shape."""

    runtime = agent_runtime or AgentRuntime()
    guidance_entries = guidance_entries or []
    contexts: list[RoundAgentContext] = []
    ui_rounds: list[dict[str, Any]] = []

    for round_state in rounds:
        context = _build_round_context(task, round_state, guidance_entries)
        contexts.append(context)
        ui_rounds.append(
            _round_to_frontend_payload(
                context=context,
                best_candidate_id=best_candidate_id,
                runtime=runtime,
                guidance_entries=guidance_entries,
            )
        )

    multi_rounds = [
        _multi_round_payload(base_round, context, runtime, guidance_entries)
        for base_round, context in zip(ui_rounds, contexts, strict=False)
    ]

    motifs = sorted(
        {
            *DEFAULT_MOTIFS,
            *(f"delta={r.candidates[0].structure.delta:.2f}" for r in rounds if r.candidates),
            *(f"N={r.candidates[0].structure.N}" for r in rounds if r.candidates),
            *{
                _motif_from_guidance(entry.get("content", ""))
                for entry in guidance_entries
                if entry.get("content")
            },
        }
        - {""}
    )

    return {
        "taskId": task.task_id,
        "taskTitle": task_title_override or task.description or task.task_id,
        "bestCandidateId": best_candidate_id,
        "bestPef": round(best_pef, 4),
        "isRunning": True,
        "rounds": ui_rounds,
        "multiLlmRounds": multi_rounds,
        "motifs": motifs,
    }


def _build_round_context(
    task: TaskCard,
    round_state: RoundState,
    guidance_entries: list[dict[str, Any]],
) -> RoundAgentContext:
    candidate = _select_round_candidate(round_state)
    screen = (
        next((s for s in round_state.screen_results if candidate and s.candidate_id == candidate.candidate_id), None)
        if candidate
        else None
    )
    verifications = {
        verification.tier: verification
        for verification in round_state.verification_results
        if candidate is None or verification.candidate_id == candidate.candidate_id
    }
    decision = (
        next((d for d in reversed(round_state.critic_decisions) if candidate and d.candidate_id == candidate.candidate_id), None)
        if candidate
        else None
    )
    memory = (
        next((m for m in reversed(round_state.memory_records) if candidate and m.source_candidate_id == candidate.candidate_id), None)
        if candidate
        else None
    )
    applicable_guidance = tuple(
        entry["content"].strip()
        for entry in guidance_entries
        if entry.get("content")
        and int(entry.get("roundId") or round_state.round_id) <= round_state.round_id
    )
    return RoundAgentContext(
        task=task,
        round_state=round_state,
        candidate=candidate,
        screen=screen,
        decision=decision,
        memory=memory,
        verifications=verifications,
        guidance_notes=applicable_guidance,
    )


def _round_to_frontend_payload(
    *,
    context: RoundAgentContext,
    best_candidate_id: str | None,
    runtime: AgentRuntime,
    guidance_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate = context.candidate
    verification_by_tier = {
        tier: _verification_to_frontend(verification)
        for tier, verification in context.verifications.items()
    }
    best_label = best_candidate_id or (candidate.candidate_id if candidate else "None")
    if best_label != (candidate.candidate_id if candidate else None) and best_candidate_id is None:
        best_label = "None"

    messages = _build_guidance_messages(context.round_state.round_id, guidance_entries)
    messages.extend(runtime.build_role_messages(context))

    return {
        "round": context.round_state.round_id,
        "status": _status_to_frontend(context.round_state),
        "budgetStr": _budget_to_frontend(context.round_state),
        "bestCandidate": best_label or "None",
        "messages": messages,
        "proposal": _build_proposal(candidate, context.screen, context.decision),
        "verification": {
            "python": verification_by_tier.get("L1", {"status": "missing"}),
            "matlab": verification_by_tier.get("L2", {"status": "missing"}),
            "comsol": verification_by_tier.get("L3", {"status": "missing"}),
        },
        "memory": _memory_to_frontend(context.memory, context.round_state.round_id),
    }


def _multi_round_payload(
    base_round: dict[str, Any],
    context: RoundAgentContext,
    runtime: AgentRuntime,
    guidance_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = copy.deepcopy(base_round)
    payload["messages"] = _build_guidance_messages(context.round_state.round_id, guidance_entries)
    payload["messages"].extend(runtime.build_multi_llm_messages(context))
    return payload


def _build_guidance_messages(round_id: int, guidance_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in guidance_entries:
        entry_round = int(entry.get("roundId") or round_id)
        if entry_round != round_id:
            continue
        content = str(entry.get("content", "")).strip()
        if not content:
            continue
        messages.append(
            {
                "agent": "User",
                "type": "normal",
                "threaded": True,
                "content": content,
            }
        )
    return messages


def _select_round_candidate(round_state: RoundState) -> CandidateDesignFamily | None:
    if not round_state.candidates:
        return None
    if round_state.best_candidate_id:
        selected = next(
            (candidate for candidate in round_state.candidates if candidate.candidate_id == round_state.best_candidate_id),
            None,
        )
        if selected is not None:
            return selected
    return round_state.candidates[0]


def _status_to_frontend(round_state: RoundState) -> str:
    if round_state.phase == "verifying":
        return "Verifying"
    if round_state.phase == "discussing":
        return "Discussing"
    return "Completed"


def _budget_to_frontend(round_state: RoundState) -> str:
    used = round_state.budget_used or max(
        len(round_state.messages),
        len(round_state.critic_decisions) + len(round_state.verification_results) + 1,
    )
    return f"{min(used, round_state.budget_total)} / {round_state.budget_total}"


def _build_proposal(
    candidate: CandidateDesignFamily | None,
    screen: MechanismScreenResult | None,
    decision: CriticDecision | None,
) -> dict[str, Any] | None:
    if candidate is None:
        return None

    pros: list[str] = []
    cons: list[str] = []

    if screen is not None:
        if screen.tr_frequency is not None:
            pros.append(f"TR found at {screen.tr_frequency:.4g} Hz")
        if screen.eta is not None:
            pros.append(f"Boundary localization eta={screen.eta:.4g}")
        cons.extend(screen.revision_hints)

    if decision is not None and decision.reason:
        cons.append(decision.reason)
    if not pros:
        pros.append("Candidate generated successfully")
    if not cons:
        cons.append("No major issues recorded in this round")

    return {
        "title": candidate.candidate_id,
        "params": [
            {"name": "alpha", "val": f"{candidate.structure.alpha:.4g}"},
            {"name": "beta", "val": f"{candidate.structure.beta:.4g}"},
            {"name": "delta", "val": f"{candidate.structure.delta:.4g}"},
            {"name": "N", "val": str(candidate.structure.N)},
            {"name": "kappa²", "val": f"{candidate.electrical.kappa2:.4g}"},
        ],
        "pros": pros[:4],
        "cons": cons[:4],
    }


def _verification_to_frontend(verification: VerificationResult) -> dict[str, Any]:
    return {
        "status": verification.status,
        "metrics": [_metric_to_frontend(metric) for metric in verification.metrics],
        "details": verification.details,
        "log": verification.log,
    }


def _metric_to_frontend(metric: MetricValue) -> dict[str, str]:
    value = metric.value
    if isinstance(value, float):
        rendered = f"{value:.4g}"
    else:
        rendered = str(value)
    if metric.unit:
        rendered = f"{rendered} {metric.unit}"
    return {
        "label": metric.label,
        "val": rendered,
        "cls": {
            "pass": "v-pass",
            "warn": "v-warn",
            "fail": "v-fail",
        }[metric.status],
    }


def _memory_to_frontend(memory: MemoryRecord | None, round_id: int) -> dict[str, str] | None:
    if memory is None:
        return None

    return {
        "id": f"M{round_id}",
        "rawId": memory.memory_id,
        "observation": memory.observation,
        "interpretation": memory.interpretation,
        "failureType": memory.category.title(),
        "nextStep": memory.next_step,
    }


def _motif_from_guidance(content: str) -> str:
    lowered = content.lower()
    if "tuning layer" in lowered:
        return "User: Tuning Layer"
    if "defect" in lowered:
        return "User: Near-Boundary Defect"
    if "current" in lowered:
        return "User: Current Objective"
    if "voltage" in lowered:
        return "User: Voltage Objective"
    if "suppression" in lowered:
        return "User: Suppression-First"
    return ""
