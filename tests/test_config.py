"""Tests for council.config."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from council.config import (
    AgentConfig,
    CouncilConfig,
    load_config,
    save_default_config,
    _deep_merge,
    DEFAULT_CONFIG,
)


class TestAgentConfig:
    def test_defaults(self):
        a = AgentConfig(name="test", enabled=True, display_name="Test")
        assert a.type == "cli"
        assert a.timeout == 300
        assert a.command == ""
        assert a.args == []
        assert a.model == ""

    def test_cli_agent(self):
        a = AgentConfig(
            name="claude", enabled=True, display_name="Claude Code",
            type="cli", command="claude", args=["-p"],
        )
        assert a.type == "cli"
        assert a.command == "claude"

    def test_openrouter_agent(self):
        a = AgentConfig(
            name="gpt", enabled=True, display_name="GPT-4.1",
            type="openrouter", model="openai/gpt-4.1",
        )
        assert a.type == "openrouter"
        assert a.model == "openai/gpt-4.1"


class TestCouncilConfig:
    def _make_config(self, **kwargs):
        agents = kwargs.pop("agents", {
            "a": AgentConfig(name="a", enabled=True, display_name="Agent A"),
            "b": AgentConfig(name="b", enabled=True, display_name="Agent B"),
            "c": AgentConfig(name="c", enabled=False, display_name="Agent C"),
        })
        return CouncilConfig(agents=agents, **kwargs)

    def test_active_agents(self):
        cfg = self._make_config()
        active = cfg.active_agents
        assert len(active) == 2
        assert all(a.enabled for a in active)

    def test_active_agents_none_enabled(self):
        agents = {"x": AgentConfig(name="x", enabled=False, display_name="X")}
        cfg = CouncilConfig(agents=agents)
        assert cfg.active_agents == []

    def test_chairman_agent_enabled(self):
        cfg = self._make_config(chairman="a")
        assert cfg.chairman_agent.name == "a"

    def test_chairman_agent_disabled_falls_back(self):
        cfg = self._make_config(chairman="c")  # c is disabled
        chairman = cfg.chairman_agent
        assert chairman.enabled
        assert chairman.name in ("a", "b")

    def test_chairman_agent_missing_falls_back(self):
        cfg = self._make_config(chairman="nonexistent")
        chairman = cfg.chairman_agent
        assert chairman.enabled

    def test_chairman_agent_no_active_raises(self):
        agents = {"x": AgentConfig(name="x", enabled=False, display_name="X")}
        cfg = CouncilConfig(agents=agents, chairman="x")
        with pytest.raises(ValueError, match="No active agents"):
            cfg.chairman_agent

    def test_soul_missing_file(self):
        cfg = self._make_config(soul_file="/nonexistent/SOUL.md")
        assert cfg.soul == ""

    def test_soul_reads_file(self, tmp_path):
        soul_file = tmp_path / "SOUL.md"
        soul_file.write_text("Be honest.\n")
        cfg = self._make_config(soul_file=str(soul_file))
        assert cfg.soul == "Be honest."

    def test_openrouter_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-123")
        cfg = self._make_config()
        assert cfg.openrouter_api_key == "sk-test-123"

    def test_openrouter_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = self._make_config()
        assert cfg.openrouter_api_key == ""


class TestLoadConfig:
    def test_load_defaults(self, tmp_path):
        cfg = load_config(config_path=tmp_path / "nonexistent.yaml")
        assert "claude" in cfg.agents
        assert "gpt" in cfg.agents
        assert "gemini" in cfg.agents
        assert cfg.chairman == "claude"

    def test_load_from_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "chairman": "gpt",
            "agents": {
                "claude": {"enabled": False},
            },
        }))
        cfg = load_config(config_path=config_file)
        assert cfg.chairman == "gpt"
        assert cfg.agents["claude"].enabled is False
        # gpt and gemini should still exist from defaults
        assert cfg.agents["gpt"].enabled is True

    def test_load_custom_agent(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "agents": {
                "deepseek": {
                    "enabled": True,
                    "type": "openrouter",
                    "model": "deepseek/deepseek-r1",
                    "display_name": "DeepSeek R1",
                    "timeout": 60,
                },
            },
        }))
        cfg = load_config(config_path=config_file)
        assert "deepseek" in cfg.agents
        ds = cfg.agents["deepseek"]
        assert ds.type == "openrouter"
        assert ds.model == "deepseek/deepseek-r1"
        assert ds.timeout == 60


class TestDeepMerge:
    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        result = _deep_merge(base, {"b": 3})
        assert result == {"a": 1, "b": 3}

    def test_nested_merge(self):
        base = {"x": {"a": 1, "b": 2}}
        result = _deep_merge(base, {"x": {"b": 3}})
        assert result == {"x": {"a": 1, "b": 3}}

    def test_new_keys(self):
        base = {"a": 1}
        result = _deep_merge(base, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_nested_new_key(self):
        base = {"x": {"a": 1}}
        result = _deep_merge(base, {"x": {"c": 3}})
        assert result == {"x": {"a": 1, "c": 3}}


class TestSaveDefaultConfig:
    def test_creates_file(self, tmp_path, monkeypatch):
        import council.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "config.yaml")
        path = save_default_config()
        assert path.exists()
        content = yaml.safe_load(path.read_text())
        assert "agents" in content
        assert "chairman" in content
