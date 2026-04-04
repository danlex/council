"""Bridge for CLI agents (subprocess) and API agents (OpenRouter)."""

from __future__ import annotations

import json
import subprocess
import time
import re
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Callable

from council.config import AgentConfig, CouncilConfig


@dataclass
class AgentResponse:
    agent_name: str
    display_name: str
    response: str
    elapsed_seconds: float
    success: bool
    error: str | None = None


class Bridge:
    """Unified bridge for CLI and OpenRouter agents."""

    def __init__(self, config: CouncilConfig):
        self.config = config
        self.session_prefix = config.session_prefix

    def query_agent(
        self,
        agent: AgentConfig,
        prompt: str,
        run_id: str,
        on_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse:
        if agent.type == "openrouter":
            return self._query_openrouter(agent, prompt, run_id, on_chunk)
        else:
            return self._query_cli(agent, prompt, run_id, on_chunk)

    # ─── CLI Agent ──────────────────────────────────────────────────────

    def _query_cli(
        self,
        agent: AgentConfig,
        prompt: str,
        run_id: str,
        on_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse:
        start = time.time()
        try:
            args = [a.replace("{prompt}", prompt) if "{prompt}" in a else a for a in agent.args]
            use_stdin = not any("{prompt}" in a for a in agent.args)
            cmd = [agent.command] + args

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if use_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            if use_stdin:
                proc.stdin.write(prompt)
                proc.stdin.close()

            chunks = []
            for line in proc.stdout:
                chunks.append(line)
                if on_chunk:
                    on_chunk(line)

            proc.wait(timeout=agent.timeout)
            elapsed = time.time() - start

            output = "".join(chunks).strip()
            stderr = proc.stderr.read().strip()

            if proc.returncode != 0 and not output:
                return AgentResponse(
                    agent_name=agent.name,
                    display_name=agent.display_name,
                    response="",
                    elapsed_seconds=elapsed,
                    success=False,
                    error=stderr or f"Exit code {proc.returncode}",
                )

            output = _strip_ansi(output)
            output = _strip_cli_metadata(output, agent.name)

            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response=output,
                elapsed_seconds=elapsed,
                success=bool(output),
                error=None if output else "Empty response",
            )

        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            elapsed = time.time() - start
            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response="",
                elapsed_seconds=elapsed,
                success=False,
                error=f"Timed out after {agent.timeout}s",
            )
        except FileNotFoundError:
            elapsed = time.time() - start
            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response="",
                elapsed_seconds=elapsed,
                success=False,
                error=f"Command not found: {agent.command}. Is it installed?",
            )
        except Exception as e:
            elapsed = time.time() - start
            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response="",
                elapsed_seconds=elapsed,
                success=False,
                error=str(e),
            )

    # ─── OpenRouter API ─────────────────────────────────────────────────

    def _query_openrouter(
        self,
        agent: AgentConfig,
        prompt: str,
        run_id: str,
        on_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse:
        api_key = self.config.openrouter_api_key
        if not api_key:
            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response="",
                elapsed_seconds=0,
                success=False,
                error="OPENROUTER_API_KEY not set. Add it to .env",
            )

        start = time.time()
        try:
            url = f"{self.config.openrouter_base_url}/chat/completions"
            payload = json.dumps({
                "model": agent.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 16384,
            }).encode()

            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/danlex/council",
                    "X-Title": "Council of LLM CLIs",
                },
            )

            with urllib.request.urlopen(req, timeout=agent.timeout) as resp:
                body = json.loads(resp.read().decode())

            elapsed = time.time() - start

            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if on_chunk and content:
                on_chunk(content)

            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response=content.strip(),
                elapsed_seconds=elapsed,
                success=bool(content.strip()),
                error=None if content.strip() else "Empty response from API",
            )

        except urllib.error.HTTPError as e:
            elapsed = time.time() - start
            error_body = ""
            try:
                error_body = e.read().decode()[:200]
            except Exception:
                pass
            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response="",
                elapsed_seconds=elapsed,
                success=False,
                error=f"HTTP {e.code}: {error_body}",
            )
        except Exception as e:
            elapsed = time.time() - start
            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response="",
                elapsed_seconds=elapsed,
                success=False,
                error=str(e),
            )

    # ─── Parallel (tmux for CLI, threaded for API) ──────────────────────

    def query_agents_parallel(
        self,
        agents: list[AgentConfig],
        prompt: str,
        run_id: str,
        on_chunk: Callable[[str, str], None] | None = None,
    ) -> list[AgentResponse]:
        """Run all agents in parallel using threads."""
        import concurrent.futures

        results = []

        def run_agent(agent):
            def chunk_cb(chunk):
                if on_chunk:
                    on_chunk(agent.name, chunk)
            return self.query_agent(agent, prompt, run_id, on_chunk=chunk_cb)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents)) as pool:
            futures = {pool.submit(run_agent, a): a for a in agents}
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        return results


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def _strip_cli_metadata(text: str, agent_name: str) -> str:
    """Strip CLI-specific metadata headers from output."""
    if agent_name == "codex":
        lines = text.split("\n")
        codex_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "codex":
                codex_idx = i
        if codex_idx is not None:
            response_lines = []
            for line in lines[codex_idx + 1:]:
                if line.strip() == "tokens used":
                    break
                response_lines.append(line)
            return "\n".join(response_lines).strip()
        if "--------" in text:
            parts = text.split("--------")
            if len(parts) >= 3:
                return parts[-1].strip()
    return text
