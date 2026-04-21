from __future__ import annotations

from pathlib import Path

from veh_scientist.discover.discussion import append_human_note, build_discussion_bundle
from veh_scientist.discover.publication import build_publication_bundle
from veh_scientist.discover.utils import write_json
from veh_scientist.interfaces import ExperimentArtifact
from veh_scientist.taskcard import parse_discover_task_card
from veh_scientist.discover import DiscoveryRunner


def test_discussion_and_publication_helpers_materialize_outputs(tmp_path: Path) -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    runner = DiscoveryRunner(task)
    program = runner.plan()
    program.output_dir = str((tmp_path / task.task_id).resolve())

    figure_path = tmp_path / "beam_band_structure.png"
    figure_path.write_bytes(b"png")
    report_path = tmp_path / "appendix_package.md"
    report_path.write_text("appendix", encoding="utf-8")
    program.artifacts.extend(
        [
            ExperimentArtifact(label="Beam band structure", artifact_type="figure", path=str(figure_path.resolve()), description="fig", generated_by="test"),
            ExperimentArtifact(label="Appendix package", artifact_type="report", path=str(report_path.resolve()), description="report", generated_by="test"),
        ]
    )

    publication = build_publication_bundle(tmp_path / "publication", task, program)
    assert (tmp_path / "publication" / "publication_bundle.json").exists()
    assert publication["reproducibility"]["n_artifacts"] >= 1

    discussion = build_discussion_bundle(tmp_path / "discussion", task, program)
    assert (tmp_path / "discussion" / "discussion_bundle.json").exists()
    assert len(discussion["generated_messages"]) >= 5

    state_path = tmp_path / task.task_id / "program_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    program.discussion_bundle = discussion
    write_json(state_path, program)
    result = append_human_note(state_path, author="tester", topic="decision", content="Keep TR2 as the baseline.")
    assert result["n_human_messages"] == 1
    assert (state_path.parent / "12_discussion" / "discussion_bundle.json").exists()
