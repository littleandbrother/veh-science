"""Persistent agent-slot configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from veh_scientist.agents.definitions import get_slot_definition, list_slot_definitions


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / ".veh_scientist" / "agent_configs.json"


@dataclass
class AgentConfig:
    """Connection info for one slot."""

    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""
    enabled: bool = False

    def normalized(self) -> "AgentConfig":
        return AgentConfig(
            provider=(self.provider or "openai").strip().lower(),
            base_url=(self.base_url or "").strip(),
            api_key=(self.api_key or "").strip(),
            model_name=(self.model_name or "").strip(),
            enabled=bool(self.enabled and self.base_url.strip() and self.api_key.strip() and self.model_name.strip()),
        )

    def has_credentials(self) -> bool:
        cfg = self.normalized()
        return bool(cfg.base_url and cfg.api_key and cfg.model_name)

    def masked(self) -> dict[str, object]:
        cfg = self.normalized()
        api_key = cfg.api_key
        masked_key = ""
        if api_key:
            if len(api_key) <= 8:
                masked_key = "*" * len(api_key)
            else:
                masked_key = f"{api_key[:4]}{'*' * max(len(api_key) - 8, 4)}{api_key[-4:]}"
        return {
            "provider": cfg.provider,
            "baseUrl": cfg.base_url,
            "apiKeyMasked": masked_key,
            "modelName": cfg.model_name,
            "enabled": cfg.enabled,
            "hasCredentials": cfg.has_credentials(),
        }

    def fingerprint(self) -> tuple[str, str, str, str]:
        cfg = self.normalized()
        return (cfg.provider, cfg.base_url, cfg.api_key, cfg.model_name)


class AgentConfigStore:
    """JSON-backed config store shared by the dashboard server."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CONFIG_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._configs = self._load()

    def _load(self) -> dict[str, AgentConfig]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        loaded: dict[str, AgentConfig] = {}
        for slot_id, payload in raw.items():
            if slot_id not in {slot.slot_id for slot in list_slot_definitions()}:
                continue
            loaded[slot_id] = AgentConfig(
                provider=str(payload.get("provider", "openai")),
                base_url=str(payload.get("base_url", "")),
                api_key=str(payload.get("api_key", "")),
                model_name=str(payload.get("model_name", "")),
                enabled=bool(payload.get("enabled", False)),
            ).normalized()
        return loaded

    def save(self) -> None:
        payload = {
            slot_id: {
                "provider": cfg.provider,
                "base_url": cfg.base_url,
                "api_key": cfg.api_key,
                "model_name": cfg.model_name,
                "enabled": cfg.enabled,
            }
            for slot_id, cfg in sorted(self._configs.items())
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, slot_id: str) -> AgentConfig:
        get_slot_definition(slot_id)
        return self._configs.get(slot_id, AgentConfig())

    def set(self, slot_id: str, config: AgentConfig) -> AgentConfig:
        get_slot_definition(slot_id)
        normalized = config.normalized()
        self._configs[slot_id] = normalized
        self.save()
        return normalized

    def set_for_mode(self, mode: str, config: AgentConfig) -> list[str]:
        normalized = config.normalized()
        touched: list[str] = []
        for slot in list_slot_definitions(mode):
            self._configs[slot.slot_id] = normalized
            touched.append(slot.slot_id)
        self.save()
        return touched

    def list_for_mode(self, mode: str) -> list[dict[str, object]]:
        return [
            {
                "slotId": slot.slot_id,
                "mode": slot.mode,
                "agentName": slot.agent_name,
                "label": slot.label,
                "purpose": slot.purpose,
                "promptBrief": slot.prompt_brief,
                "config": self.get(slot.slot_id).masked(),
            }
            for slot in list_slot_definitions(mode)
        ]

    def export_slot(self, slot_id: str) -> dict[str, object]:
        slot = get_slot_definition(slot_id)
        return {
            "slotId": slot.slot_id,
            "mode": slot.mode,
            "agentName": slot.agent_name,
            "label": slot.label,
            "purpose": slot.purpose,
            "promptBrief": slot.prompt_brief,
            "config": self.get(slot_id).masked(),
        }

    def snapshot(self) -> dict[str, AgentConfig]:
        return {slot_id: AgentConfig(**asdict(config)) for slot_id, config in self._configs.items()}
