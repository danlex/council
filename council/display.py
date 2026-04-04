"""Rich terminal display with live streaming feedback."""

from __future__ import annotations

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich import box

from council.bridge import AgentResponse
from council.config import AgentConfig


console = Console()

STAGE_COLORS = {1: "cyan", 2: "yellow", 3: "green"}
STAGE_ICONS = {1: "[1/3]", 2: "[2/3]", 3: "[3/3]"}
STAGE_NAMES = {
    1: "Independent Responses",
    2: "Anonymized Peer Review",
    3: "Chairman Synthesis",
}
AGENT_COLORS = {
    "claude": "magenta",
    "gpt": "bright_green",
    "codex": "bright_green",
    "gemini": "blue",
    "glm": "red",
    "minimax": "bright_yellow",
    "deepseek": "bright_cyan",
}


def get_agent_color(agent_name: str) -> str:
    return AGENT_COLORS.get(agent_name, "white")


def print_banner():
    console.print()
    console.print(Text("  COUNCIL  ", style="bold white on dark_red"), end="")
    console.print(Text("  of LLM CLIs", style="bold"))
    console.print(Text("  Multi-agent consensus without confirmation bias", style="dim"))
    console.print()


def print_question(question: str):
    console.print(Panel(
        question,
        title="[bold]Question[/bold]",
        border_style="bright_white",
        padding=(1, 2),
    ))
    console.print()


def print_memory_status(memory_count: int):
    if memory_count > 0:
        console.print(f"  [dim]Shared memory: {memory_count} entries loaded[/dim]")
        console.print()


def print_stage_header(stage: int, agents: list[AgentConfig]):
    color = STAGE_COLORS.get(stage, "white")
    icon = STAGE_ICONS.get(stage, "")
    name = STAGE_NAMES.get(stage, "")
    agent_names = ", ".join(
        f"[{get_agent_color(a.name)}]{a.display_name}[/{get_agent_color(a.name)}]"
        for a in agents
    )
    console.print(Rule(f"{icon} Stage {stage}: {name}", style=color))
    console.print(f"  Agents: {agent_names}")
    console.print()


class StreamingDisplay:
    """Live-updating display for streaming agent responses."""

    def __init__(self):
        self.agent_buffers: dict[str, str] = {}
        self.agent_status: dict[str, str] = {}  # "streaming", "done", "failed"
        self.agent_times: dict[str, float] = {}
        self.agent_colors: dict[str, str] = {}
        self.agent_display_names: dict[str, str] = {}
        self.live: Live | None = None

    def start(self, agents: list[AgentConfig]):
        """Begin live display for a set of agents."""
        for a in agents:
            self.agent_buffers[a.name] = ""
            self.agent_status[a.name] = "streaming"
            self.agent_times[a.name] = 0
            self.agent_colors[a.name] = get_agent_color(a.name)
            self.agent_display_names[a.name] = a.display_name
        self.live = Live(self._render(), console=console, refresh_per_second=4)
        self.live.start()

    def update_chunk(self, agent_name: str, chunk: str):
        """Append new content from an agent."""
        if agent_name in self.agent_buffers:
            self.agent_buffers[agent_name] += chunk
            if self.live:
                self.live.update(self._render())

    def mark_done(self, agent_name: str, elapsed: float, success: bool = True):
        """Mark an agent as completed."""
        self.agent_status[agent_name] = "done" if success else "failed"
        self.agent_times[agent_name] = elapsed
        if self.live:
            self.live.update(self._render())

    def stop(self):
        """Stop the live display."""
        if self.live:
            self.live.stop()
            self.live = None

    def _render(self):
        """Render the current state of all agents."""
        panels = []
        for name in self.agent_buffers:
            color = self.agent_colors.get(name, "white")
            display_name = self.agent_display_names.get(name, name)
            status = self.agent_status.get(name, "streaming")
            elapsed = self.agent_times.get(name, 0)
            content = self.agent_buffers.get(name, "")

            # Truncate display to last 20 lines for readability
            lines = content.split("\n")
            if len(lines) > 20:
                display_content = "...\n" + "\n".join(lines[-20:])
            else:
                display_content = content

            if status == "streaming":
                title = f"[bold {color}]{display_name}[/bold {color}] [dim]streaming...[/dim]"
                border = color
            elif status == "done":
                title = f"[bold {color}]{display_name}[/bold {color}] [green]done[/green] ({elapsed:.1f}s)"
                border = "green"
            else:
                title = f"[bold {color}]{display_name}[/bold {color}] [red]failed[/red]"
                border = "red"

            panel = Panel(
                Text(display_content or "Waiting for response..."),
                title=title,
                border_style=border,
                height=min(25, max(5, len(lines) + 3)),
                padding=(0, 1),
            )
            panels.append(panel)

        return Group(*panels)


def print_agent_result(response: AgentResponse, show_content: bool = False):
    """Print a single agent's result."""
    color = get_agent_color(response.agent_name)
    if response.success:
        console.print(
            f"  [{color}]{response.display_name}[/{color}] "
            f"[green]done[/green] ({response.elapsed_seconds:.1f}s, "
            f"{len(response.response)} chars)"
        )
    else:
        console.print(
            f"  [{color}]{response.display_name}[/{color}] "
            f"[red]failed[/red]: {response.error}"
        )

    if show_content and response.success:
        console.print(Panel(
            Markdown(response.response),
            border_style=color,
            padding=(1, 2),
        ))
        console.print()


def print_stage_summary(stage: int, responses: list[AgentResponse]):
    success = sum(1 for r in responses if r.success)
    total = len(responses)
    color = STAGE_COLORS.get(stage, "white")
    total_time = sum(r.elapsed_seconds for r in responses)
    console.print(
        f"  [{color}]{success}/{total} agents completed[/{color}] "
        f"[dim]({total_time:.1f}s total)[/dim]"
    )
    console.print()


def print_final_result(synthesis_response: AgentResponse | None, fallback: str = ""):
    """Display the final council synthesis."""
    console.print(Rule("[3/3] Council Synthesis", style="green"))
    console.print()

    answer = ""
    if synthesis_response and synthesis_response.success:
        answer = synthesis_response.response
        chairman = synthesis_response.display_name
        console.print(Panel(
            Markdown(answer),
            title=f"[bold green]Council Answer[/bold green] [dim](Chairman: {chairman})[/dim]",
            border_style="green",
            padding=(1, 2),
        ))
    elif fallback:
        answer = fallback
        console.print(Panel(
            Markdown(fallback),
            title="[bold yellow]Single Agent Answer[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        ))
    else:
        console.print("[bold red]Council failed to produce an answer.[/bold red]")
    console.print()
    return answer


def print_memory_saved(path):
    console.print(f"  [dim]Memory saved: {path}[/dim]")


def print_stats(stage1, stage2, stage3):
    """Print timing statistics table."""
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("Agent", style="bold")
    table.add_column("Stage 1", justify="center")
    table.add_column("Stage 2", justify="center")
    table.add_column("Stage 3", justify="center")
    table.add_column("Total", justify="right")

    s1 = {r.agent_name: r for r in (stage1 or [])}
    s2 = {r.agent_name: r for r in (stage2 or [])}
    s3 = {stage3.agent_name: stage3} if stage3 else {}

    all_names = set(list(s1.keys()) + list(s2.keys()) + list(s3.keys()))

    for name in sorted(all_names):
        color = get_agent_color(name)
        r1, r2, r3 = s1.get(name), s2.get(name), s3.get(name)

        def fmt(r):
            if r is None: return "[dim]-[/dim]"
            return f"[green]{r.elapsed_seconds:.1f}s[/green]" if r.success else "[red]fail[/red]"

        total = sum(r.elapsed_seconds for r in [r1, r2, r3] if r)
        dn = r1.display_name if r1 else (r2.display_name if r2 else name)
        table.add_row(f"[{color}]{dn}[/{color}]", fmt(r1), fmt(r2), fmt(r3), f"[bold]{total:.1f}s[/bold]")

    console.print(table)
