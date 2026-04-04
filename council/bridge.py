"""Bridge for CLI agents (subprocess) and API agents (OpenRouter)."""

from __future__ import annotations

import json
import subprocess
import time
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Callable

from council.config import AgentConfig, CouncilConfig

MAX_RETRIES = 2
RETRY_BACKOFF = [1, 3]  # seconds
RETRYABLE_CODES = {429, 500, 502, 503, 504}


@dataclass
class AgentResponse:
    agent_name: str
    display_name: str
    response: str
    elapsed_seconds: float
    success: bool
    error: str | None = None
    # Cost tracking
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class Bridge:
    """Unified bridge for CLI and OpenRouter agents."""

    def __init__(self, config: CouncilConfig):
        self.config = config

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

    # ─── OpenRouter API with SSE streaming + retry ──────────────────────

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

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                time.sleep(RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)])

            result = self._openrouter_request(agent, prompt, api_key, on_chunk)
            if result.success:
                return result

            last_error = result.error
            # Only retry on transient errors
            if not _is_retryable(result.error):
                return result

        return AgentResponse(
            agent_name=agent.name,
            display_name=agent.display_name,
            response="",
            elapsed_seconds=result.elapsed_seconds if result else 0,
            success=False,
            error=f"Failed after {MAX_RETRIES + 1} attempts: {last_error}",
        )

    def _openrouter_request(
        self,
        agent: AgentConfig,
        prompt: str,
        api_key: str,
        on_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse:
        start = time.time()
        try:
            url = f"{self.config.openrouter_base_url}/chat/completions"
            messages = _split_prompt_messages(prompt)
            payload = json.dumps({
                "model": agent.model,
                "messages": messages,
                "max_tokens": 16384,
                "stream": True,
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

            content_parts = []
            prompt_tokens = 0
            completion_tokens = 0
            cost_usd = 0.0

            with urllib.request.urlopen(req, timeout=agent.timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue

                    data = line[6:]  # Strip "data: " prefix
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    # Extract streaming content delta
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            content_parts.append(text)
                            if on_chunk:
                                on_chunk(text)

                    # Extract usage from final chunk
                    usage = chunk.get("usage")
                    if usage:
                        prompt_tokens = usage.get("prompt_tokens", 0)
                        completion_tokens = usage.get("completion_tokens", 0)
                        cost_usd = usage.get("cost", 0.0)

            elapsed = time.time() - start
            content = "".join(content_parts).strip()

            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response=content,
                elapsed_seconds=elapsed,
                success=bool(content),
                error=None if content else "Empty response from API",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
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

    # ─── Parallel execution ─────────────────────────────────────────────

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


def _is_retryable(error: str | None) -> bool:
    """Check if an error is transient and worth retrying."""
    if not error:
        return False
    for code in RETRYABLE_CODES:
        if f"HTTP {code}" in error:
            return True
    if "timed out" in error.lower() or "timeout" in error.lower():
        return True
    return False


def _split_prompt_messages(prompt: str) -> list[dict]:
    """Split a council prompt into system + user messages for API calls.

    If the prompt contains '## Your Brief' or '## Brief', everything before
    it becomes the system message and everything from the brief onward
    becomes the user message. This ensures SOUL.md and memory are set as
    system-level instructions.
    """
    for marker in ("## Your Brief", "## Brief"):
        if marker in prompt:
            idx = prompt.index(marker)
            system = prompt[:idx].strip()
            user = prompt[idx:].strip()
            if system and user:
                return [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
    # Fallback: everything as user message
    return [{"role": "user", "content": prompt}]


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
