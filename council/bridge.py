"""Tmux bridge for spawning and controlling CLI agents with streaming output."""

from __future__ import annotations

import subprocess
import shlex
import time
import re
import os
from dataclasses import dataclass
from typing import Callable

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
    """Controls CLI agents via subprocess/tmux with streaming support."""

    def __init__(self, session_prefix: str = "council"):
        self.session_prefix = session_prefix
        self._verify_tmux()

    def _verify_tmux(self):
        try:
            subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError("tmux is required but not found. Install with: brew install tmux")

    def query_agent(
        self,
        agent: AgentConfig,
        prompt: str,
        run_id: str,
        on_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse:
        """Send a prompt to a CLI agent with streaming output.

        Args:
            agent: Agent configuration
            prompt: The prompt to send
            run_id: Unique run identifier
            on_chunk: Callback for each chunk of streaming output
        """
        start = time.time()
        try:
            # If any arg contains {prompt}, substitute it; otherwise pipe via stdin
            args = [a.replace("{prompt}", prompt) if "{prompt}" in a else a for a in agent.args]
            use_stdin = not any("{prompt}" in a for a in agent.args)
            cmd = [agent.command] + args

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if use_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Send prompt via stdin if needed
            if use_stdin:
                proc.stdin.write(prompt)
                proc.stdin.close()

            # Stream stdout line by line
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

    def query_agents_parallel_tmux(
        self,
        agents: list[AgentConfig],
        prompt: str,
        run_id: str,
        on_chunk: Callable[[str, str], None] | None = None,
    ) -> list[AgentResponse]:
        """Run multiple agents in parallel using tmux sessions.

        Args:
            agents: List of agent configs
            prompt: The prompt to send
            run_id: Unique run identifier
            on_chunk: Callback(agent_name, new_content) for live updates
        """
        sessions = {}

        for agent in agents:
            session = f"{self.session_prefix}-{run_id}-{agent.name}"
            prompt_file = f"/tmp/council-{run_id}-{agent.name}-prompt.txt"
            output_file = f"/tmp/council-{run_id}-{agent.name}-out.txt"

            with open(prompt_file, "w") as f:
                f.write(prompt)

            # Substitute {prompt} placeholder with the prompt file content inline
            has_placeholder = any("{prompt}" in a for a in agent.args)
            if has_placeholder:
                # Read prompt into a variable and substitute into args
                resolved_args = []
                for a in agent.args:
                    if "{prompt}" in a:
                        resolved_args.append(f'"$(cat {shlex.quote(prompt_file)})"')
                    else:
                        resolved_args.append(shlex.quote(a))
                cmd_parts = [shlex.quote(agent.command)] + resolved_args
                shell_cmd = (
                    f"{' '.join(cmd_parts)} "
                    f"> {shlex.quote(output_file)} 2>&1; "
                    f"echo '___COUNCIL_DONE___' >> {shlex.quote(output_file)}"
                )
            else:
                cmd_parts = [shlex.quote(agent.command)] + [shlex.quote(a) for a in agent.args]
                shell_cmd = (
                    f"cat {shlex.quote(prompt_file)} | {' '.join(cmd_parts)} "
                    f"> {shlex.quote(output_file)} 2>&1; "
                    f"echo '___COUNCIL_DONE___' >> {shlex.quote(output_file)}"
                )

            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session, shell_cmd],
                capture_output=True,
            )
            sessions[agent.name] = {
                "session": session,
                "agent": agent,
                "start": time.time(),
                "output_file": output_file,
                "prompt_file": prompt_file,
                "last_size": 0,
            }

        results = []
        pending = dict(sessions)

        while pending:
            for name, info in list(pending.items()):
                agent = info["agent"]
                elapsed = time.time() - info["start"]

                # Stream new content
                try:
                    with open(info["output_file"]) as f:
                        content = f.read()
                    if len(content) > info["last_size"] and on_chunk:
                        new_content = content[info["last_size"]:]
                        clean = new_content.replace("___COUNCIL_DONE___", "")
                        if clean.strip():
                            on_chunk(name, clean)
                        info["last_size"] = len(content)
                except FileNotFoundError:
                    content = ""

                # Check completion
                done = "___COUNCIL_DONE___" in content
                if not done:
                    check = subprocess.run(
                        ["tmux", "has-session", "-t", info["session"]],
                        capture_output=True,
                    )
                    done = check.returncode != 0

                if done:
                    try:
                        with open(info["output_file"]) as f:
                            content = f.read()
                        content = content.replace("___COUNCIL_DONE___", "").strip()
                        content = _strip_ansi(content)
                        content = _strip_cli_metadata(content, name)
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
                time.sleep(0.5)

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


def _cleanup_file(path: str):
    try:
        os.unlink(path)
    except OSError:
        pass
