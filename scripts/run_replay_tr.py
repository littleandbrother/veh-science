"""Plan or execute the TR discovery replay workflow from a discover task card."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from veh_scientist.discover import DiscoveryRunner
from veh_scientist.discover.utils import to_jsonable
from veh_scientist.taskcard import parse_discover_task_card, validate_discover_task_card


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task_card",
        nargs="?",
        default="configs/tasks/tr_discover_replay.yaml",
        help="Path to a discover/replay task card.",
    )
    parser.add_argument(
        "--output-dir",
        default="results/discovery",
        help="Root directory for generated replay artifacts.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Only materialize the replay program without executing solver stages.",
    )
    args = parser.parse_args()

    task = parse_discover_task_card(args.task_card)
    issues = validate_discover_task_card(task)
    if issues:
        for issue in issues:
            print(f"[invalid] {issue}")
        return 1

    runner = DiscoveryRunner(task, task_card_path=args.task_card)
    program = runner.plan() if args.plan_only else runner.execute(output_dir=args.output_dir)
    print(json.dumps(to_jsonable(program), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
