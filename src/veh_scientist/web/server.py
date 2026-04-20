"""Simple HTTP server for the VEH Scientist dashboard."""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from veh_scientist.agents import AgentConfig, AgentConfigStore, AgentRuntime, get_slot_definition
from veh_scientist.agents.providers import ProviderError, test_connection
from veh_scientist.web.dashboard import run_dashboard_session


REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"


class DashboardSession:
    """In-memory session state for human-in-the-loop dashboard interactions."""

    def __init__(
        self,
        task_path: Path,
        rounds: int,
        output_dir: Path,
        config_store: AgentConfigStore,
    ) -> None:
        self.task_path = task_path
        self.rounds = rounds
        self.output_dir = output_dir
        self.config_store = config_store
        self.is_running = True
        self.task_title_override: str | None = None
        self.guidance_entries: list[dict] = []
        self._payload: dict | None = None
        self._dirty = True

    def get_payload(
        self,
        task_path: Path | None = None,
        rounds: int | None = None,
    ) -> dict:
        changed = False
        if task_path is not None and task_path != self.task_path:
            self.task_path = task_path
            self.task_title_override = None
            self.guidance_entries = []
            changed = True
        if rounds is not None and rounds != self.rounds:
            self.rounds = rounds
            changed = True
        if self._payload is None or changed or (self._dirty and self.is_running):
            self._payload = run_dashboard_session(
                task_source=self.task_path,
                rounds=self.rounds,
                output_dir=self.output_dir,
                guidance_entries=self.guidance_entries,
                task_title_override=self.task_title_override,
                agent_runtime=AgentRuntime(self.config_store),
            )
            self._dirty = False
        return self._decorate_payload()

    def append_user_message(
        self,
        content: str,
        round_id: int | None = None,
        set_as_task: bool = False,
    ) -> dict:
        normalized = content.strip()
        if not normalized:
            return self.get_payload()

        effective_round = round_id
        if effective_round is None:
            payload = self.get_payload()
            effective_round = self._resolve_round_id(payload, round_id)
        if set_as_task:
            self.task_title_override = normalized

        self.guidance_entries.append(
            {
                "content": normalized,
                "roundId": int(effective_round) if effective_round is not None else None,
                "setAsTask": bool(set_as_task),
            }
        )
        self._dirty = True

        if self.is_running or self._payload is None:
            return self.get_payload()

        user_message = {
            "agent": "User",
            "type": "normal",
            "threaded": True,
            "content": normalized,
        }
        system_message = {
            "agent": "Coordinator",
            "type": "system",
            "content": (
                "Captured user guidance and folded it into the current exploration context."
                if not set_as_task
                else f"Updated the working task to: {normalized}"
            ),
        }
        payload = self._decorate_payload()
        self._append_message_to_payload(payload, int(effective_round), user_message)
        self._append_message_to_payload(payload, int(effective_round), system_message)
        return payload

    def set_running(self, is_running: bool, round_id: int | None = None) -> dict:
        payload = self.get_payload()
        if self.is_running == is_running:
            return payload

        self.is_running = is_running
        target_round = self._resolve_round_id(payload, round_id)
        if is_running and self._dirty:
            return self.get_payload()
        if self._payload is not None:
            self._append_message(
                target_round,
                {
                    "agent": "Coordinator",
                    "type": "system",
                    "content": "Discussion resumed by user." if is_running else "Discussion paused by user.",
                },
            )
        return self._decorate_payload()

    def _decorate_payload(self) -> dict:
        if self._payload is None:
            raise RuntimeError("Dashboard payload not initialized")
        payload = copy.deepcopy(self._payload)
        payload["isRunning"] = self.is_running
        if self.task_title_override:
            payload["taskTitle"] = self.task_title_override
        return payload

    def _resolve_round_id(self, payload: dict, round_id: int | None) -> int:
        rounds = payload.get("rounds", [])
        if not rounds:
            return 1
        if round_id is None:
            return int(rounds[-1]["round"])
        return int(round_id)

    def _append_message(self, round_id: int, message: dict) -> None:
        if self._payload is None:
            raise RuntimeError("Dashboard payload not initialized")
        self._append_message_to_payload(self._payload, round_id, message)

    @staticmethod
    def _append_message_to_payload(payload: dict, round_id: int, message: dict) -> None:
        for collection_name in ("rounds", "multiLlmRounds"):
            for round_item in payload.get(collection_name, []):
                if int(round_item["round"]) == int(round_id):
                    round_item.setdefault("messages", []).append(copy.deepcopy(message))
                    break


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    """Serve static frontend assets and a small JSON API."""

    task_path = REPO_ROOT / "configs/tasks/tr_baseline.yaml"
    max_rounds = 3
    output_dir = REPO_ROOT / "results/runs"
    session: DashboardSession | None = None
    config_store = AgentConfigStore()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            self._send_json({"status": "ok"})
            return

        if parsed.path == "/api/session":
            self._handle_session_request(parsed)
            return
        if parsed.path == "/api/config":
            self._handle_config_request(parsed)
            return

        if parsed.path == "/":
            self.path = "/index.html"
        else:
            self.path = parsed.path
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/session/message":
            self._handle_message_post()
            return
        if parsed.path == "/api/session/control":
            self._handle_control_post()
            return
        if parsed.path == "/api/config/test":
            self._handle_config_test_post()
            return
        if parsed.path == "/api/config/save":
            self._handle_config_save_post()
            return

        self._send_json(
            {"error": f"Unsupported POST endpoint: {parsed.path}"},
            status=HTTPStatus.NOT_FOUND,
        )

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Keep server output concise.
        super().log_message(format, *args)

    def guess_type(self, path: str) -> str:
        mime_type, _ = mimetypes.guess_type(path)
        return mime_type or "application/octet-stream"

    def _handle_session_request(self, parsed) -> None:
        try:
            query = parse_qs(parsed.query)
            task_path = self._resolve_task_path(query.get("task", [str(self.task_path)])[0])
            rounds = int(query.get("rounds", [str(self.max_rounds)])[0])
            payload = self._get_session().get_payload(task_path=task_path, rounds=rounds)
            self._send_json(payload)
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                {
                    "error": str(exc),
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _handle_config_request(self, parsed) -> None:
        query = parse_qs(parsed.query)
        mode = query.get("mode", ["role"])[0]
        slot_id = query.get("slotId", [None])[0]
        if slot_id:
            self._send_json(
                {
                    "mode": mode,
                    "slot": self.config_store.export_slot(slot_id),
                    "slots": self.config_store.list_for_mode(mode),
                }
            )
            return
        self._send_json(
            {
                "mode": mode,
                "slots": self.config_store.list_for_mode(mode),
            }
        )

    def _handle_message_post(self) -> None:
        try:
            body = self._read_json_body()
            payload = self._get_session().append_user_message(
                content=body.get("content", ""),
                round_id=body.get("roundId"),
                set_as_task=bool(body.get("setAsTask")),
            )
            self._send_json(payload)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_control_post(self) -> None:
        try:
            body = self._read_json_body()
            action = body.get("action", "").lower()
            if action not in {"start", "pause"}:
                raise ValueError("Action must be 'start' or 'pause'")
            payload = self._get_session().set_running(
                is_running=(action == "start"),
                round_id=body.get("roundId"),
            )
            self._send_json(payload)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_config_test_post(self) -> None:
        try:
            body = self._read_json_body()
            slot_id = str(body.get("slotId", "")).strip()
            existing = self.config_store.get(slot_id) if slot_id else AgentConfig()
            config = AgentConfig(
                provider=body.get("provider", "openai"),
                base_url=body.get("baseUrl", ""),
                api_key=body.get("apiKey", "") or existing.api_key,
                model_name=body.get("modelName", ""),
                enabled=True,
            )
            response = test_connection(config)
            self._send_json({"ok": True, "message": response or "connection ok"})
        except ProviderError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_config_save_post(self) -> None:
        try:
            body = self._read_json_body()
            slot_id = str(body.get("slotId", "")).strip()
            slot = get_slot_definition(slot_id)
            existing = self.config_store.get(slot_id)
            config = AgentConfig(
                provider=body.get("provider", "openai"),
                base_url=body.get("baseUrl", ""),
                api_key=body.get("apiKey", "") or existing.api_key,
                model_name=body.get("modelName", ""),
                enabled=bool(body.get("enabled", True)),
            )
            if body.get("applyToMode"):
                touched = self.config_store.set_for_mode(slot.mode, config)
            else:
                self.config_store.set(slot_id, config)
                touched = [slot_id]

            if self.session is not None:
                self.session._dirty = True

            self._send_json(
                {
                    "ok": True,
                    "mode": slot.mode,
                    "savedSlots": touched,
                    "slot": self.config_store.export_slot(slot_id),
                    "slots": self.config_store.list_for_mode(slot.mode),
                }
            )
        except Exception as exc:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _resolve_task_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = (REPO_ROOT / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if REPO_ROOT not in candidate.parents and candidate != REPO_ROOT:
            raise ValueError("Task path must stay inside the workspace")
        if not candidate.exists():
            raise FileNotFoundError(f"Task file not found: {candidate}")
        return candidate

    def _get_session(self) -> DashboardSession:
        if self.session is None:
            self.__class__.session = DashboardSession(
                task_path=Path(self.task_path),
                rounds=self.max_rounds,
                output_dir=Path(self.output_dir),
                config_store=self.config_store,
            )
        return self.session

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_server(
    host: str,
    port: int,
    task_path: str | Path,
    rounds: int,
    output_dir: str | Path,
) -> ThreadingHTTPServer:
    DashboardRequestHandler.task_path = Path(task_path)
    DashboardRequestHandler.max_rounds = rounds
    DashboardRequestHandler.output_dir = Path(output_dir)
    DashboardRequestHandler.config_store = AgentConfigStore()
    DashboardRequestHandler.session = DashboardSession(
        task_path=Path(task_path),
        rounds=rounds,
        output_dir=Path(output_dir),
        config_store=DashboardRequestHandler.config_store,
    )
    return ThreadingHTTPServer((host, port), DashboardRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the VEH Scientist dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--task", default="configs/tasks/tr_baseline.yaml")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output", default="results/runs")
    args = parser.parse_args()

    server = build_server(
        host=args.host,
        port=args.port,
        task_path=args.task,
        rounds=args.rounds,
        output_dir=args.output,
    )
    print(f"Serving dashboard at http://{args.host}:{args.port}")
    print(f"Task: {args.task}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
