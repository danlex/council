"""Tests for council.bridge."""

import json
import subprocess
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from council.bridge import (
    Bridge,
    AgentResponse,
    _strip_ansi,
    _strip_cli_metadata,
    _is_retryable,
)
from council.config import AgentConfig, CouncilConfig


def _cli_agent(**kwargs):
    defaults = dict(
        name="test", enabled=True, display_name="Test CLI",
        type="cli", command="echo", args=["hello"],
    )
    defaults.update(kwargs)
    return AgentConfig(**defaults)


def _api_agent(**kwargs):
    defaults = dict(
        name="gpt", enabled=True, display_name="GPT",
        type="openrouter", model="openai/gpt-4.1", timeout=30,
    )
    defaults.update(kwargs)
    return AgentConfig(**defaults)


def _config(**kwargs):
    defaults = dict(
        agents={"test": _cli_agent()},
        openrouter_base_url="https://openrouter.ai/api/v1",
    )
    defaults.update(kwargs)
    return CouncilConfig(**defaults)


# ─── Strip helpers ──────────────────────────────────────────────────────

class TestStripAnsi:
    def test_strips_color_codes(self):
        assert _strip_ansi("\x1b[31mred\x1b[0m") == "red"

    def test_strips_bold(self):
        assert _strip_ansi("\x1b[1mbold\x1b[0m") == "bold"

    def test_no_ansi_unchanged(self):
        assert _strip_ansi("plain text") == "plain text"

    def test_empty_string(self):
        assert _strip_ansi("") == ""


class TestStripCliMetadata:
    def test_codex_full_output(self):
        raw = (
            "Reading additional input from stdin...\n"
            "OpenAI Codex v0.118.0 (research preview)\n"
            "--------\n"
            "workdir: /tmp\n"
            "model: gpt-5.4\n"
            "--------\n"
            "user\n"
            "What is 2+2?\n"
            "codex\n"
            "4\n"
            "tokens used\n"
            "1234\n"
            "4"
        )
        result = _strip_cli_metadata(raw, "codex")
        assert result == "4"

    def test_codex_multiline_response(self):
        raw = (
            "codex\n"
            "Line one\n"
            "Line two\n"
            "Line three\n"
            "tokens used\n"
            "500"
        )
        result = _strip_cli_metadata(raw, "codex")
        assert "Line one" in result
        assert "Line two" in result
        assert "Line three" in result
        assert "tokens used" not in result

    def test_codex_fallback_dashes(self):
        raw = "header--------middle--------actual response here"
        result = _strip_cli_metadata(raw, "codex")
        assert result == "actual response here"

    def test_non_codex_unchanged(self):
        text = "Just a normal response"
        assert _strip_cli_metadata(text, "claude") == text
        assert _strip_cli_metadata(text, "gpt") == text

    def test_empty_input(self):
        assert _strip_cli_metadata("", "codex") == ""


# ─── CLI Bridge ─────────────────────────────────────────────────────────

class TestBridgeCli:
    def test_query_cli_success(self):
        agent = _cli_agent(command="echo", args=["hello world"])
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "ignored", "test1")
        assert resp.success
        assert "hello world" in resp.response

    def test_query_cli_command_not_found(self):
        agent = _cli_agent(command="nonexistent_command_12345")
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "test", "test2")
        assert not resp.success
        assert "not found" in resp.error.lower()

    def test_query_cli_prompt_placeholder(self):
        agent = _cli_agent(command="echo", args=["{prompt}"])
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "hello from placeholder", "test3")
        assert resp.success
        assert "hello from placeholder" in resp.response

    def test_query_cli_empty_response(self):
        # Command that produces no stdout
        agent = _cli_agent(command="true", args=[], timeout=5)
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "", "test4")
        assert not resp.success
        assert "empty" in resp.error.lower()

    def test_query_cli_nonzero_exit(self):
        agent = _cli_agent(command="false", args=[], timeout=5)
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "", "test4b")
        assert not resp.success

    def test_query_cli_streaming_callback(self):
        agent = _cli_agent(command="echo", args=["line1\nline2"])
        cfg = _config()
        bridge = Bridge(config=cfg)
        chunks = []
        resp = bridge.query_agent(agent, "", "test5", on_chunk=chunks.append)
        assert resp.success
        assert len(chunks) > 0


# ─── OpenRouter Bridge ──────────────────────────────────────────────────

class TestBridgeOpenRouter:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        agent = _api_agent()
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "test", "test1")
        assert not resp.success
        assert "OPENROUTER_API_KEY" in resp.error

    @patch("council.bridge.urllib.request.urlopen")
    def test_openrouter_success(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        # Simulate SSE streaming response
        sse_lines = [
            b'data: {"choices":[{"delta":{"content":"Hello "}}]}\n',
            b'\n',
            b'data: {"choices":[{"delta":{"content":"from GPT"}}]}\n',
            b'\n',
            b'data: {"usage":{"prompt_tokens":10,"completion_tokens":5,"cost":0.001}}\n',
            b'\n',
            b'data: [DONE]\n',
        ]
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.__iter__ = lambda s: iter(sse_lines)
        mock_urlopen.return_value = mock_response

        agent = _api_agent()
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "Say hello", "test2")
        assert resp.success
        assert resp.response == "Hello from GPT"
        assert resp.agent_name == "gpt"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.cost_usd == 0.001

    @patch("council.bridge.urllib.request.urlopen")
    def test_openrouter_empty_response(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        sse_lines = [
            b'data: {"choices":[{"delta":{}}]}\n',
            b'\n',
            b'data: [DONE]\n',
        ]
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.__iter__ = lambda s: iter(sse_lines)
        mock_urlopen.return_value = mock_response

        agent = _api_agent()
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "Say hello", "test3")
        assert not resp.success
        assert "empty" in resp.error.lower()

    @patch("council.bridge.urllib.request.urlopen")
    def test_openrouter_http_error(self, mock_urlopen, monkeypatch):
        import urllib.error
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        error = urllib.error.HTTPError(
            "http://test", 429, "Rate limited", {}, None
        )
        mock_urlopen.side_effect = error

        agent = _api_agent()
        cfg = _config()
        bridge = Bridge(config=cfg)
        resp = bridge.query_agent(agent, "test", "test4")
        assert not resp.success
        assert "429" in resp.error

    @patch("council.bridge.urllib.request.urlopen")
    def test_openrouter_callback(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        sse_lines = [
            b'data: {"choices":[{"delta":{"content":"Chunk1"}}]}\n',
            b'\n',
            b'data: {"choices":[{"delta":{"content":"Chunk2"}}]}\n',
            b'\n',
            b'data: [DONE]\n',
        ]
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.__iter__ = lambda s: iter(sse_lines)
        mock_urlopen.return_value = mock_response

        agent = _api_agent()
        cfg = _config()
        bridge = Bridge(config=cfg)
        chunks = []
        resp = bridge.query_agent(agent, "test", "test5", on_chunk=chunks.append)
        assert resp.success
        assert chunks == ["Chunk1", "Chunk2"]


# ─── Parallel ───────────────────────────────────────────────────────────

class TestBridgeParallel:
    def test_parallel_multiple_agents(self):
        agents = [
            _cli_agent(name="a", display_name="A", command="echo", args=["response_a"]),
            _cli_agent(name="b", display_name="B", command="echo", args=["response_b"]),
        ]
        cfg = _config()
        bridge = Bridge(config=cfg)
        results = bridge.query_agents_parallel(agents, "ignored", "par1")
        assert len(results) == 2
        assert all(r.success for r in results)
        names = {r.agent_name for r in results}
        assert names == {"a", "b"}

    def test_parallel_with_failure(self):
        agents = [
            _cli_agent(name="ok", display_name="OK", command="echo", args=["works"]),
            _cli_agent(name="bad", display_name="Bad", command="nonexistent_cmd"),
        ]
        cfg = _config()
        bridge = Bridge(config=cfg)
        results = bridge.query_agents_parallel(agents, "test", "par2")
        assert len(results) == 2
        ok = [r for r in results if r.agent_name == "ok"][0]
        bad = [r for r in results if r.agent_name == "bad"][0]
        assert ok.success
        assert not bad.success

    def test_parallel_chunk_callback(self):
        agents = [
            _cli_agent(name="x", display_name="X", command="echo", args=["chunk_test"]),
        ]
        cfg = _config()
        bridge = Bridge(config=cfg)
        chunks = []
        results = bridge.query_agents_parallel(
            agents, "test", "par3",
            on_chunk=lambda name, chunk: chunks.append((name, chunk)),
        )
        assert len(results) == 1
        assert results[0].success
        assert any(name == "x" for name, _ in chunks)


# ─── Retry logic ────────────────────────────────────────────────────────

class TestRetryable:
    def test_429_is_retryable(self):
        assert _is_retryable("HTTP 429: Rate limited")

    def test_500_is_retryable(self):
        assert _is_retryable("HTTP 500: Internal Server Error")

    def test_502_is_retryable(self):
        assert _is_retryable("HTTP 502: Bad Gateway")

    def test_timeout_is_retryable(self):
        assert _is_retryable("Timed out after 30s")

    def test_400_is_not_retryable(self):
        assert not _is_retryable("HTTP 400: Bad Request")

    def test_empty_error_not_retryable(self):
        assert not _is_retryable("")

    def test_none_not_retryable(self):
        assert not _is_retryable(None)

    def test_auth_error_not_retryable(self):
        assert not _is_retryable("HTTP 401: Unauthorized")


# ─── Cost tracking ──────────────────────────────────────────────────────

class TestCostTracking:
    def test_response_has_cost_fields(self):
        r = AgentResponse(
            agent_name="test", display_name="Test",
            response="hi", elapsed_seconds=1.0, success=True,
        )
        assert r.prompt_tokens == 0
        assert r.completion_tokens == 0
        assert r.cost_usd == 0.0

    def test_response_cost_fields_set(self):
        r = AgentResponse(
            agent_name="test", display_name="Test",
            response="hi", elapsed_seconds=1.0, success=True,
            prompt_tokens=100, completion_tokens=50, cost_usd=0.0023,
        )
        assert r.prompt_tokens == 100
        assert r.completion_tokens == 50
        assert r.cost_usd == 0.0023
