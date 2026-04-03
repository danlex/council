"""Configuration management for the council CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


CONFIG_DIR = Path.home() / ".config" / "council"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

SOUL_FILE = Path("SOUL.md")

DEFAULT_CONFIG = {
    "agents": {
        "claude": {
            "enabled": True,
            "command": "claude",
            "args": ["-p", "--max-turns", "10", "--output-format", "text"],
            "display_name": "Claude Code",
            "timeout": 300,
        },
        "codex": {
            "enabled": True,
            "command": "codex",
            "args": ["exec", "--skip-git-repo-check"],
            "display_name": "Codex CLI",
            "timeout": 300,
        },
        "gemini": {
            "enabled": True,
            "command": "gemini",
            "args": ["-p"],
            "display_name": "Gemini CLI",
            "timeout": 300,
        },
    },
    "chairman": "claude",
    "soul_file": "SOUL.md",
    "review": {
        "anonymize": True,
        "rubric": ["accuracy", "reasoning", "completeness", "nuance"],
    },
    "synthesis": {
        "preserve_dissent": True,
        "show_confidence": True,
    },
    "tmux": {
        "session_prefix": "council",
    },
}


@dataclass
class AgentConfig:
    name: str
    enabled: bool
    command: str
    args: list[str]
    display_name: str
    timeout: int = 120


@dataclass
class CouncilConfig:
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    chairman: str = "claude"
    anonymize: bool = True
    rubric: list[str] = field(default_factory=lambda: ["accuracy", "reasoning", "completeness", "nuance"])
    preserve_dissent: bool = True
    show_confidence: bool = True
    session_prefix: str = "council"
    soul_file: str = "SOUL.md"

    @property
    def active_agents(self) -> list[AgentConfig]:
        return [a for a in self.agents.values() if a.enabled]

    @property
    def chairman_agent(self) -> AgentConfig:
        if self.chairman in self.agents:
            return self.agents[self.chairman]
        active = self.active_agents
        if active:
            return active[0]
        raise ValueError("No active agents configured")

    @property
    def soul(self) -> str:
        """Load the shared soul/memory file that all agents receive."""
        path = Path(self.soul_file)
        if path.exists():
            return path.read_text().strip()
        return ""


def load_config(config_path: Path | None = None) -> CouncilConfig:
    """Load config from YAML file, falling back to defaults."""
    raw = dict(DEFAULT_CONFIG)

    path = config_path or CONFIG_FILE
    if path.exists():
        with open(path) as f:
            user_config = yaml.safe_load(f) or {}
        _deep_merge(raw, user_config)

    agents = {}
    for name, agent_raw in raw.get("agents", {}).items():
        agents[name] = AgentConfig(
            name=name,
            enabled=agent_raw.get("enabled", False),
            command=agent_raw.get("command", name),
            args=agent_raw.get("args", []),
            display_name=agent_raw.get("display_name", name),
            timeout=agent_raw.get("timeout", 120),
        )

    review = raw.get("review", {})
    synthesis = raw.get("synthesis", {})
    tmux = raw.get("tmux", {})

    return CouncilConfig(
        agents=agents,
        chairman=raw.get("chairman", "claude"),
        anonymize=review.get("anonymize", True),
        rubric=review.get("rubric", ["accuracy", "reasoning", "completeness", "nuance"]),
        preserve_dissent=synthesis.get("preserve_dissent", True),
        show_confidence=synthesis.get("show_confidence", True),
        session_prefix=tmux.get("session_prefix", "council"),
        soul_file=raw.get("soul_file", "SOUL.md"),
    )


def save_default_config():
    """Write default config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
    return CONFIG_FILE


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
