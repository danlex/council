"""Rich terminal display for council pipeline progress and results."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich import box

from council.bridge import AgentResponse
from council.config import AgentConfig
from council.pipeline import CouncilResult


console = Console()

STAGE_COLORS = {1: "cyan", 2: "yellow", 3: "green"}
STAGE_ICONS = {1: "[1/3]", 2: "[2/3]", 3: "[3/3]"}
AGENT_COLORS = {
    "claude": "magenta",
    "codex": "bright_green",
    "gemini": "blue",
    "glm": "red",
    "minimax": "bright_yellow",
    "deepseek": "bright_cyan",
}


def get_agent_color(agent_name: str) -> str:
    return AGENT_COLORS.get(agent_name, "white")


def print_banner():
    banner = Text()
    banner.append("  COUNCIL  ", style="bold white on dark_red")
    banner.append("  of LLM CLIs", style="bold")
    console.print()
    console.print(banner)
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


def print_stage_start(stage: int, name: str, agents: list[AgentConfig]):
    color = STAGE_COLORS.get(stage, "white")
    icon = STAGE_ICONS.get(stage, "")
    agent_names = ", ".join(a.display_name for a in agents)
    console.print(Rule(
        f"{icon} Stage {stage}: {name}",
        style=color,
    ))
    console.print(f"  [dim]Agents: {agent_names}[/dim]")
    console.print()


def print_agent_done(stage: int, response: AgentResponse):
    color = get_agent_color(response.agent_name)
    if response.success:
        status = f"[bold {color}]{response.display_name}[/bold {color}] [green]done[/green] ({response.elapsed_seconds:.1f}s)"
    else:
        status = f"[bold {color}]{response.display_name}[/bold {color}] [red]failed[/red]: {response.error}"
    console.print(f"  {status}")


def print_stage_done(stage: int, responses: list[AgentResponse]):
    success = sum(1 for r in responses if r.success)
    total = len(responses)
    color = STAGE_COLORS.get(stage, "white")
    console.print(f"  [{color}]{success}/{total} agents completed successfully[/{color}]")
    console.print()


def print_verbose_responses(responses: list[AgentResponse]):
    """Show individual responses in detail."""
    for resp in responses:
        if not resp.success:
            continue
        color = get_agent_color(resp.agent_name)
        console.print(Panel(
            Markdown(resp.response),
            title=f"[bold {color}]{resp.display_name}[/bold {color}]",
            subtitle=f"[dim]{resp.elapsed_seconds:.1f}s[/dim]",
            border_style=color,
            padding=(1, 2),
        ))
        console.print()


def print_final_result(result: CouncilResult, verbose: bool = False):
    """Display the final council result."""
    if verbose and result.stage1_responses:
        console.print(Rule("Individual Responses", style="dim"))
        console.print()
        print_verbose_responses(result.stage1_responses)

    if verbose and result.stage2_reviews:
        console.print(Rule("Peer Reviews", style="dim"))
        console.print()
        print_verbose_responses(result.stage2_reviews)

    # Final synthesis
    console.print(Rule("[3/3] Council Synthesis", style="green"))
    console.print()

    if result.stage3_synthesis and result.stage3_synthesis.success:
        chairman_name = result.stage3_synthesis.display_name
        chairman_color = get_agent_color(result.stage3_synthesis.agent_name)
        console.print(Panel(
            Markdown(result.final_answer),
            title=f"[bold green]Council Answer[/bold green] [dim](Chairman: {chairman_name})[/dim]",
            border_style="green",
            padding=(1, 2),
        ))
    elif result.final_answer:
        console.print(Panel(
            Markdown(result.final_answer),
            title="[bold yellow]Fallback Answer (single agent)[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        ))
    else:
        console.print("[bold red]Council failed to produce an answer.[/bold red]")
        for err in result.errors:
            console.print(f"  [red]- {err}[/red]")

    # Stats
    console.print()
    _print_stats(result)


def _print_stats(result: CouncilResult):
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("Agent", style="bold")
    table.add_column("Stage 1", justify="center")
    table.add_column("Stage 2", justify="center")
    table.add_column("Stage 3", justify="center")
    table.add_column("Total Time", justify="right")

    all_agents = set()
    s1 = {r.agent_name: r for r in result.stage1_responses}
    s2 = {r.agent_name: r for r in result.stage2_reviews}
    s3 = {result.stage3_synthesis.agent_name: result.stage3_synthesis} if result.stage3_synthesis else {}
    all_agents = set(list(s1.keys()) + list(s2.keys()) + list(s3.keys()))

    for name in sorted(all_agents):
        color = get_agent_color(name)
        r1 = s1.get(name)
        r2 = s2.get(name)
        r3 = s3.get(name)

        def status(r):
            if r is None:
                return "[dim]-[/dim]"
            return f"[green]{r.elapsed_seconds:.1f}s[/green]" if r.success else f"[red]fail[/red]"

        total = sum(r.elapsed_seconds for r in [r1, r2, r3] if r)
        display = r1.display_name if r1 else (r2.display_name if r2 else name)
        table.add_row(
            f"[{color}]{display}[/{color}]",
            status(r1),
            status(r2),
            status(r3),
            f"[bold]{total:.1f}s[/bold]",
        )

    console.print(table)
