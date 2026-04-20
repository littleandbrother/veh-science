"""Rebuild the discovery report bundle from an existing program_state.json."""

from __future__ import annotations

import argparse
import json

from veh_scientist.discover.report import write_report_bundle
from veh_scientist.discover.utils import load_program_state, resolve_path, to_jsonable
from veh_scientist.taskcard import parse_discover_task_card


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-card", default="configs/tasks/tr_discover_replay.yaml")
    parser.add_argument("--output-dir", default="results/discovery")
    parser.add_argument("--task-id", default=None)
    args = parser.parse_args()

    task_path = resolve_path(args.task_card)
    task = parse_discover_task_card(task_path)
    task_id = args.task_id or task.task_id
    program = load_program_state(f"{args.output_dir}/{task_id}/program_state.json")
    bundle = write_report_bundle(f"{args.output_dir}/{task_id}/08_reporting", task, program)
    print(json.dumps(to_jsonable(bundle), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
