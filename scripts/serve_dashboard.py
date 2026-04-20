"""Serve the local discovery replay dashboard."""

from __future__ import annotations

import argparse

from veh_scientist.web.server import serve_dashboard


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--task-card", default="configs/tasks/tr_discover_replay.yaml")
    parser.add_argument("--output-dir", default="results/discovery")
    args = parser.parse_args()
    serve_dashboard(
        host=args.host,
        port=args.port,
        default_task_card=args.task_card,
        default_output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
