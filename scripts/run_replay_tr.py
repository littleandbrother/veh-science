"""Plan the TR discovery replay workflow from a discover task card."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from veh_scientist.discover import DiscoveryRunner
from veh_scientist.taskcard import parse_discover_task_card, validate_discover_task_card


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task_card",
        nargs="?",
        default="configs/tasks/tr_discover_replay.yaml",
        help="Path to a discover/replay task card.",
    )
    args = parser.parse_args()

    task = parse_discover_task_card(args.task_card)
    issues = validate_discover_task_card(task)
    if issues:
        for issue in issues:
            print(f"[invalid] {issue}")
        return 1

    runner = DiscoveryRunner(task)
    program = runner.plan()
    print(json.dumps(asdict(program), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
