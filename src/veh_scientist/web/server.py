"""Local dashboard server for executable discovery replay."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from veh_scientist.discover.discussion import append_human_note
from veh_scientist.discover.report import write_report_bundle
from veh_scientist.discover.runner import DiscoveryRunner
from veh_scientist.discover.smoke import run_regression_smoke
from veh_scientist.discover.utils import load_program_state, repo_root, resolve_path, to_jsonable
from veh_scientist.taskcard import parse_discover_task_card


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "VEHScienceDashboard/0.4"

    def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(to_jsonable(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, body: bytes, content_type: str, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _resolve_program_path(self, parsed_query: dict[str, list[str]]) -> Path:
        output_dir = parsed_query.get("output_dir", [self.server.default_output_dir])[0]
        task_id = parsed_query.get("task_id", [""])[0]
        if not task_id:
            task_card = parsed_query.get("task_card", [self.server.default_task_card])[0]
            task = parse_discover_task_card(resolve_path(task_card, base_dir=self.server.repo_root))
            task_id = task.task_id
        return Path(output_dir) / task_id / "program_state.json"

    def _load_program_from_query(self, parsed_query: dict[str, list[str]]):
        path = self._resolve_program_path(parsed_query)
        if not path.exists():
            return None, path
        return load_program_state(path), path

    def _run_list(self, output_dir: str | Path) -> list[dict[str, Any]]:
        root = Path(output_dir)
        if not root.exists():
            return []
        runs: list[dict[str, Any]] = []
        for candidate in sorted(root.glob("*/program_state.json"), key=lambda path: path.stat().st_mtime, reverse=True):
            try:
                program = load_program_state(candidate)
                runs.append(
                    {
                        "task_id": program.task_id,
                        "stage": program.stage,
                        "updated_at": program.updated_at,
                        "output_dir": str(Path(program.output_dir).resolve()) if program.output_dir else str(candidate.parent.resolve()),
                        "best_gap_anchor": program.summary_metrics.get("best_gap_anchor"),
                        "best_gap_calibrated_hz": program.summary_metrics.get("best_gap_calibrated_hz"),
                        "smoke_pass": program.summary_metrics.get("smoke_pass"),
                        "calibration_source": program.summary_metrics.get("calibration_source"),
                        "negative_memory_records": program.summary_metrics.get("negative_memory_records"),
                        "publication_main_figures": program.summary_metrics.get("publication_main_figures"),
                    }
                )
            except Exception:
                runs.append(
                    {
                        "task_id": candidate.parent.name,
                        "stage": "unknown",
                        "updated_at": "",
                        "output_dir": str(candidate.parent.resolve()),
                    }
                )
        return runs

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            return self._serve_static(self.server.frontend_root / "index.html")
        if parsed.path.startswith("/frontend/"):
            rel = parsed.path[len("/frontend/") :]
            return self._serve_static(self.server.frontend_root / rel)
        if parsed.path == "/api/health":
            return self._json({"ok": True, "repo_root": str(self.server.repo_root)})
        if parsed.path == "/api/defaults":
            task = parse_discover_task_card(resolve_path(self.server.default_task_card, base_dir=self.server.repo_root))
            return self._json(
                {
                    "ok": True,
                    "default_task_card": self.server.default_task_card,
                    "default_output_dir": self.server.default_output_dir,
                    "task": task,
                }
            )
        if parsed.path == "/api/runs":
            params = parse_qs(parsed.query)
            output_dir = params.get("output_dir", [self.server.default_output_dir])[0]
            return self._json({"ok": True, "runs": self._run_list(output_dir)})
        if parsed.path == "/api/program":
            params = parse_qs(parsed.query)
            path = self._resolve_program_path(params)
            if not path.exists():
                return self._json({"ok": False, "error": f"Program state not found: {path}"}, status=HTTPStatus.NOT_FOUND)
            return self._serve_static(path)
        if parsed.path in {
            "/api/smoke",
            "/api/calibration",
            "/api/appendix",
            "/api/mechanisms",
            "/api/library",
            "/api/memory",
            "/api/publication",
            "/api/discussion",
        }:
            params = parse_qs(parsed.query)
            program, path = self._load_program_from_query(params)
            if program is None:
                return self._json({"ok": False, "error": f"Program state not found: {path}"}, status=HTTPStatus.NOT_FOUND)
            if parsed.path == "/api/smoke":
                return self._json({"ok": True, "smoke_summary": program.smoke_summary})
            if parsed.path == "/api/calibration":
                return self._json({"ok": True, "calibration_summary": program.calibration_summary})
            if parsed.path == "/api/appendix":
                return self._json({"ok": True, "appendix_summary": program.appendix_summary})
            if parsed.path == "/api/mechanisms":
                return self._json({"ok": True, "mechanism_portfolio": program.mechanism_portfolio})
            if parsed.path == "/api/library":
                return self._json({"ok": True, "solver_library": program.solver_library})
            if parsed.path == "/api/memory":
                return self._json({"ok": True, "negative_memory": program.negative_memory})
            if parsed.path == "/api/publication":
                return self._json({"ok": True, "publication_bundle": program.publication_bundle})
            return self._json({"ok": True, "discussion_bundle": program.discussion_bundle, "collaboration_log": program.collaboration_log})
        if parsed.path == "/artifact":
            params = parse_qs(parsed.query)
            requested = params.get("path", [""])[0]
            if not requested:
                return self._json({"ok": False, "error": "Missing artifact path."}, status=HTTPStatus.BAD_REQUEST)
            return self._serve_static(Path(unquote(requested)), must_be_safe=True)
        return self._json({"ok": False, "error": f"Unknown route: {parsed.path}"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._read_json_body()
        if parsed.path == "/api/run_replay":
            task_card = payload.get("task_card", self.server.default_task_card)
            output_dir = payload.get("output_dir", self.server.default_output_dir)
            try:
                task_path = resolve_path(task_card, base_dir=self.server.repo_root)
                task = parse_discover_task_card(task_path)
                runner = DiscoveryRunner(task, task_card_path=task_path)
                program = runner.execute(output_dir=output_dir)
                return self._json({"ok": True, "program": program, "summary": runner.summary()})
            except Exception as exc:  # noqa: BLE001
                return self._json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        if parsed.path == "/api/rebuild_report":
            task_card = payload.get("task_card", self.server.default_task_card)
            output_dir = payload.get("output_dir", self.server.default_output_dir)
            task_path = resolve_path(task_card, base_dir=self.server.repo_root)
            task = parse_discover_task_card(task_path)
            task_id = payload.get("task_id", task.task_id)
            program_path = Path(output_dir) / task_id / "program_state.json"
            if not program_path.exists():
                return self._json({"ok": False, "error": f"Program state not found: {program_path}"}, status=HTTPStatus.NOT_FOUND)
            program = load_program_state(program_path)
            report_dir = Path(output_dir) / task_id / "10_reporting"
            bundle = write_report_bundle(report_dir, task, program)
            return self._json({"ok": True, "bundle": bundle})
        if parsed.path == "/api/run_smoke":
            task_card = payload.get("task_card", self.server.default_task_card)
            output_dir = payload.get("output_dir", self.server.default_output_dir)
            task_path = resolve_path(task_card, base_dir=self.server.repo_root)
            task = parse_discover_task_card(task_path)
            task_id = payload.get("task_id", task.task_id)
            program_path = Path(output_dir) / task_id / "program_state.json"
            if not program_path.exists():
                return self._json({"ok": False, "error": f"Program state not found: {program_path}"}, status=HTTPStatus.NOT_FOUND)
            program = load_program_state(program_path)
            smoke_dir = Path(output_dir) / task_id / "13_smoke"
            smoke_summary = run_regression_smoke(task, program, smoke_dir)
            return self._json({"ok": True, "smoke_summary": smoke_summary})
        if parsed.path == "/api/discussion_note":
            output_dir = payload.get("output_dir", self.server.default_output_dir)
            task_card = payload.get("task_card", self.server.default_task_card)
            task_path = resolve_path(task_card, base_dir=self.server.repo_root)
            task = parse_discover_task_card(task_path)
            task_id = payload.get("task_id", task.task_id)
            program_path = Path(output_dir) / task_id / "program_state.json"
            if not program_path.exists():
                return self._json({"ok": False, "error": f"Program state not found: {program_path}"}, status=HTTPStatus.NOT_FOUND)
            author = str(payload.get("author", "human"))
            topic = str(payload.get("topic", "note"))
            content = str(payload.get("content", "")).strip()
            references = payload.get("references", [])
            if not content:
                return self._json({"ok": False, "error": "content must not be empty"}, status=HTTPStatus.BAD_REQUEST)
            result = append_human_note(program_path, author=author, topic=topic, content=content, references=references)
            return self._json({"ok": True, "result": result})
        return self._json({"ok": False, "error": f"Unknown route: {parsed.path}"}, status=HTTPStatus.NOT_FOUND)

    def _serve_static(self, path: Path, must_be_safe: bool = False) -> None:
        candidate = path if path.is_absolute() else (self.server.repo_root / path)
        candidate = candidate.resolve()
        if must_be_safe and not self.server.is_safe_path(candidate):
            return self._json({"ok": False, "error": f"Access denied: {candidate}"}, status=HTTPStatus.FORBIDDEN)
        if not candidate.exists():
            return self._json({"ok": False, "error": f"File not found: {candidate}"}, status=HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        body = candidate.read_bytes()
        return self._text(body, ctype)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return None


class DashboardHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], default_task_card: str, default_output_dir: str):
        self.repo_root = repo_root()
        self.frontend_root = self.repo_root / "frontend"
        self.default_task_card = default_task_card
        self.default_output_dir = default_output_dir
        super().__init__(server_address, DashboardHandler)

    def is_safe_path(self, path: Path) -> bool:
        allowed_roots = [self.repo_root.resolve(), Path(self.default_output_dir).resolve()]
        if Path("/mnt/data").exists():
            allowed_roots.append(Path("/mnt/data").resolve())
        try:
            return any(path.is_relative_to(root) for root in allowed_roots)
        except AttributeError:
            return any(str(path).startswith(str(root)) for root in allowed_roots)



def serve_dashboard(
    host: str = "127.0.0.1",
    port: int = 8000,
    default_task_card: str = "configs/tasks/tr_discover_replay.yaml",
    default_output_dir: str = "results/discovery",
) -> None:
    server = DashboardHTTPServer((host, port), default_task_card=default_task_card, default_output_dir=default_output_dir)
    print(f"Dashboard serving on http://{host}:{port}")
    server.serve_forever()
