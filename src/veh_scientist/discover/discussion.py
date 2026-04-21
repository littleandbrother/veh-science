"""Discussion bundle and human-in-the-loop collaboration utilities."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from veh_scientist.discover.utils import load_program_state, now_iso, write_json, write_text
from veh_scientist.interfaces import CollaborationMessage, DiscoverTaskCard, DiscoveryProgramState


ROLE_DESCRIPTIONS = {
    "planner": "Own the next-step research plan and gap-prioritization logic.",
    "theorist": "Challenge derivations, asymptotics, and mechanism assumptions.",
    "numerics": "Audit solver fidelity, calibration, and uncertainty propagation.",
    "skeptic": "Search for failure modes, confounders, and over-claims.",
    "reviewer": "Act like a demanding external reviewer focused on evidence.",
    "editor": "Turn the technical record into a publishable story and figure order.",
    "human": "Manual collaborator who can add notes, decisions, or corrections.",
}



def _role_prompt(role: str, task: DiscoverTaskCard, program: DiscoveryProgramState) -> str:
    best_gap = (program.gap_candidates or [None])[0]
    best_text = "no ranked gap yet"
    if best_gap is not None:
        best_frequency = best_gap.calibrated_frequency_hz or best_gap.anchored_frequency_hz or best_gap.raw_frequency_hz
        best_text = f"gap {best_gap.band_index} near {best_frequency:.3f} Hz"
    return (
        f"Role: {role}. "
        f"Research question: {task.research_question or task.description}. "
        f"Current best candidate: {best_text}. "
        f"Calibration source: {(program.calibration_summary or {}).get('source', '')}. "
        f"Use the report, appendix, negative-result memory, solver library, publication bundle, and discussion ledger as the review context."
    )



def build_discussion_bundle(
    output_dir: str | Path,
    task: DiscoverTaskCard,
    program: DiscoveryProgramState,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    memory = program.negative_memory or {}
    primary_mechanism = (program.mechanism_portfolio or {}).get("recommended_path", {}).get("primary", task.mechanism_focus)
    best_gap = (program.gap_candidates or [None])[0]
    best_gap_text = "no gap ranked"
    if best_gap is not None:
        best_frequency = best_gap.calibrated_frequency_hz or best_gap.anchored_frequency_hz or best_gap.raw_frequency_hz
        best_gap_text = f"gap {best_gap.band_index} @ {best_frequency:.3f} Hz"

    generated_messages = [
        CollaborationMessage(
            role="planner",
            author="system",
            topic="next-step plan",
            content=f"Primary mechanism remains {primary_mechanism}. Keep {best_gap_text} as the calibrated baseline, then compare against defect/interface alternatives using the solver library and negative-result memory.",
            references=("mechanism_portfolio.json", "mechanism_solver_library.json", "negative_result_memory.json"),
        ),
        CollaborationMessage(
            role="theorist",
            author="system",
            topic="theory risk",
            content=f"Appendix checks passed={bool((program.appendix_summary or {}).get('all_checks_pass'))}. The next theory checkpoint is whether mechanism comparisons preserve interpretable design rules rather than mixing unrelated localization routes.",
            references=("appendix_package.md", "derivation_traces.json"),
        ),
        CollaborationMessage(
            role="numerics",
            author="system",
            topic="numerics risk",
            content=f"Calibration source={(program.calibration_summary or {}).get('source', '')}, confidence={(program.calibration_summary or {}).get('confidence', 0.0):.3f}. Focus on uncertainty propagation and extrapolation penalties before trusting off-anchor candidates.",
            references=("calibration_summary.json", "candidate_uncertainty.csv", "uncertainty_model.json"),
        ),
        CollaborationMessage(
            role="skeptic",
            author="system",
            topic="failure modes",
            content=f"Negative memory currently lists {memory.get('summary', {}).get('n_records', 0)} records. Challenge any claim that ignores parameter no-go zones, unsuitable gaps, or provisional/live L3 refutations.",
            references=("negative_result_memory.json",),
        ),
        CollaborationMessage(
            role="reviewer",
            author="system",
            topic="reviewer concerns",
            content="Ask whether each headline claim in the paper has a figure, an appendix derivation, and a reproducibility pointer. If any one is missing, the claim is not submission-ready.",
            references=("publication_bundle.json", "reviewer_artifact_manifest.json"),
        ),
        CollaborationMessage(
            role="editor",
            author="system",
            topic="paper story",
            content="Tell the story as: mechanism gap → derivation backbone → L1 evidence → L2/L3 calibration → uncertainty-aware ranking → why TR beats alternatives under the stated target band.",
            references=("discovery_report.md", "main_figures.json", "ablation_tables.md"),
        ),
    ]
    prompts = [
        {
            "role": role,
            "description": description,
            "prompt": _role_prompt(role, task, program),
        }
        for role, description in ROLE_DESCRIPTIONS.items()
        if role != "human"
    ]
    bundle = {
        "task_id": task.task_id,
        "primary_mechanism": primary_mechanism,
        "best_gap": best_gap_text,
        "generated_messages": [asdict(message) for message in generated_messages],
        "human_messages": [asdict(message) for message in program.collaboration_log],
        "prompt_pack": prompts,
        "roles": ROLE_DESCRIPTIONS,
        "updated_at": now_iso(),
    }
    write_json(output_dir / "discussion_bundle.json", bundle)
    write_json(output_dir / "multi_llm_prompt_pack.json", prompts)
    lines = ["# Discussion bundle", ""]
    for message in generated_messages:
        lines.append(f"- **{message.role}** ({message.topic}): {message.content}")
    if program.collaboration_log:
        lines.extend(["", "## Human notes", ""])
        for message in program.collaboration_log:
            lines.append(f"- **{message.author or 'human'}** ({message.topic}): {message.content}")
    lines.extend(["", "## Prompt pack", ""])
    for prompt in prompts:
        lines.append(f"- **{prompt['role']}**: {prompt['prompt']}")
    write_text(output_dir / "discussion_bundle.md", "\n".join(lines))
    write_text(output_dir / "multi_llm_prompt_pack.md", "\n".join([f"- **{prompt['role']}**: {prompt['prompt']}" for prompt in prompts]))
    return bundle



def append_human_note(
    program_state_path: str | Path,
    author: str,
    topic: str,
    content: str,
    references: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    program_state_path = Path(program_state_path)
    program = load_program_state(program_state_path)
    message = CollaborationMessage(
        role="human",
        author=author,
        topic=topic,
        content=content,
        references=tuple(str(item) for item in references),
    )
    program.collaboration_log.append(message)
    program.updated_at = now_iso()

    discussion_dir = program_state_path.parent / "12_discussion"
    discussion_dir.mkdir(parents=True, exist_ok=True)
    bundle = dict(program.discussion_bundle or {})
    human_messages = list(bundle.get("human_messages", []))
    human_messages.append(asdict(message))
    bundle["human_messages"] = human_messages
    bundle["updated_at"] = now_iso()
    program.discussion_bundle = bundle

    write_json(program_state_path, program)
    write_json(discussion_dir / "human_notes.json", human_messages)
    write_json(discussion_dir / "discussion_bundle.json", bundle)
    return {"message": asdict(message), "n_human_messages": len(human_messages)}
