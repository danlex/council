"""Tmux bridge for spawning and controlling CLI agents."""

from __future__ import annotations

import subprocess
import time
import re
from dataclasses import dataclass

from council.config import AgentConfig


@dataclass
class AgentResponse:
    agent_name: str
    display_name: str
    response: str
    elapsed_seconds: float
    success: bool
    error: str | None = None


class TmuxBridge:
    """Controls CLI agents via tmux sessions for parallel execution."""

    def __init__(self, session_prefix: str = "council"):
        self.session_prefix = session_prefix
        self._verify_tmux()

    def _verify_tmux(self):
        try:
            subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError("tmux is required but not found. Install with: brew install tmux")

    def _session_name(self, agent_name: str, run_id: str) -> str:
        return f"{self.session_prefix}-{run_id}-{agent_name}"

    def query_agent(self, agent: AgentConfig, prompt: str, run_id: str) -> AgentResponse:
        """Send a prompt to a CLI agent and capture its response.

        Uses the CLI's non-interactive/pipe mode directly via subprocess,
        which is simpler and more reliable than tmux send-keys for
        single-shot queries.
        """
        start = time.time()
        try:
            cmd = [agent.command] + agent.args
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=agent.timeout,
            )
            elapsed = time.time() - start
            output = result.stdout.strip()

            if result.returncode != 0 and not output:
                return AgentResponse(
                    agent_name=agent.name,
                    display_name=agent.display_name,
                    response="",
                    elapsed_seconds=elapsed,
                    success=False,
                    error=result.stderr.strip() or f"Exit code {result.returncode}",
                )

            # Clean ANSI escape codes and CLI metadata from output
            output = _strip_ansi(output)
            output = _strip_cli_metadata(output, agent.name)

            return AgentResponse(
                agent_name=agent.name,
                display_name=agent.display_name,
                response=output,
                elapsed_seconds=elapsed,
                success=bool(output),
                error=None if output else "Empty response after cleaning",
            )

        except subprocess.TimeoutExpired:
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

    def query_agents_parallel_tmux(
        self, agents: list[AgentConfig], prompt: str, run_id: str
    ) -> list[AgentResponse]:
        """Run multiple agents in parallel using tmux sessions.

        Spawns each agent in a separate tmux session, waits for all to
        complete, then collects results.
        """
        sessions = {}

        # Launch all agents in parallel tmux sessions
        for agent in agents:
            session = self._session_name(agent.name, run_id)
            cmd_parts = [agent.command] + agent.args
            # Write prompt to a temp file to avoid shell escaping issues
            prompt_file = f"/tmp/council-{run_id}-{agent.name}-prompt.txt"
            with open(prompt_file, "w") as f:
                f.write(prompt)

            # Build the tmux command that pipes the prompt into the CLI
            shell_cmd = f"cat {prompt_file} | {' '.join(cmd_parts)} > /tmp/council-{run_id}-{agent.name}-out.txt 2>&1; echo '___COUNCIL_DONE___' >> /tmp/council-{run_id}-{agent.name}-out.txt"

            # Create detached tmux session
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session, shell_cmd],
                capture_output=True,
            )
            sessions[agent.name] = {
                "session": session,
                "agent": agent,
                "start": time.time(),
                "output_file": f"/tmp/council-{run_id}-{agent.name}-out.txt",
                "prompt_file": prompt_file,
            }

        # Poll for completion
        results = []
        pending = dict(sessions)
        while pending:
            for name, info in list(pending.items()):
                agent = info["agent"]
                elapsed = time.time() - info["start"]

                # Check if tmux session still exists
                check = subprocess.run(
                    ["tmux", "has-session", "-t", info["session"]],
                    capture_output=True,
                )
                session_done = check.returncode != 0

                # Also check for done marker
                try:
                    with open(info["output_file"]) as f:
                        content = f.read()
                    if "___COUNCIL_DONE___" in content:
                        session_done = True
                except FileNotFoundError:
                    content = ""

                if session_done:
                    try:
                        with open(info["output_file"]) as f:
                            content = f.read()
                        content = content.replace("___COUNCIL_DONE___", "").strip()
                        content = _strip_ansi(content)
                        results.append(AgentResponse(
                            agent_name=name,
                            display_name=agent.display_name,
                            response=content,
                            elapsed_seconds=elapsed,
                            success=bool(content),
                            error=None if content else "Empty response",
                        ))
                    except Exception as e:
                        results.append(AgentResponse(
                            agent_name=name,
                            display_name=agent.display_name,
                            response="",
                            elapsed_seconds=elapsed,
                            success=False,
                            error=str(e),
                        ))
                    # Cleanup
                    subprocess.run(["tmux", "kill-session", "-t", info["session"]], capture_output=True)
                    _cleanup_file(info["output_file"])
                    _cleanup_file(info["prompt_file"])
                    del pending[name]

                elif elapsed > agent.timeout:
                    subprocess.run(["tmux", "kill-session", "-t", info["session"]], capture_output=True)
                    results.append(AgentResponse(
                        agent_name=name,
                        display_name=agent.display_name,
                        response="",
                        elapsed_seconds=elapsed,
                        success=False,
                        error=f"Timed out after {agent.timeout}s",
                    ))
                    _cleanup_file(info["output_file"])
                    _cleanup_file(info["prompt_file"])
                    del pending[name]

            if pending:
                time.sleep(1)

        return results


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def _strip_cli_metadata(text: str, agent_name: str) -> str:
    """Strip CLI-specific metadata headers from output.

    Codex CLI prepends metadata like:
        Reading additional input from stdin...
        OpenAI Codex v0.118.0 (research preview)
        --------
        workdir: ...
        model: ...
        ...
        --------
        user
        <prompt>
        codex
        <actual response>
        tokens used
        123
    """
    if agent_name == "codex":
        # Find the response after the "codex\n" marker
        lines = text.split("\n")
        # Find the last "codex" marker line (the response follows it)
        codex_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "codex":
                codex_idx = i
        if codex_idx is not None:
            # Response is between "codex" and "tokens used"
            response_lines = []
            for line in lines[codex_idx + 1:]:
                if line.strip() == "tokens used":
                    break
                response_lines.append(line)
            return "\n".join(response_lines).strip()
        # Fallback: try to strip the header block
        if "--------" in text:
            parts = text.split("--------")
            if len(parts) >= 3:
                return parts[-1].strip()
    return text


def _cleanup_file(path: str):
    """Remove a temporary file if it exists."""
    import os
    try:
        os.unlink(path)
    except OSError:
        pass
