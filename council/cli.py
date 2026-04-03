"""CLI entry point for the council tool."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from council.config import load_config, save_default_config, CONFIG_FILE, AgentConfig
from council.bridge import TmuxBridge
from council.pipeline import CouncilPipeline
from council.display import (
    console,
    print_banner,
    print_question,
    print_stage_start,
    print_agent_done,
    print_stage_done,
    print_final_result,
)

app = typer.Typer(
    name="council",
    help="Council of LLM CLIs — query multiple AI agents and synthesize bias-free answers.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command()
def ask(
    question: str = typer.Argument(
        ...,
        help="The question to ask the council",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Show individual responses and peer reviews",
    ),
    chairman: Optional[str] = typer.Option(
        None, "--chairman", "-c",
        help="Override which agent acts as chairman (e.g., claude, codex, gemini)",
    ),
    agents: Optional[str] = typer.Option(
        None, "--agents", "-a",
        help="Comma-separated list of agents to use (e.g., claude,codex,gemini)",
    ),
    parallel: bool = typer.Option(
        False, "--parallel", "-p",
        help="Use tmux for true parallel execution",
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config",
        help="Path to config YAML file",
    ),
):
    """Ask the council a question. Queries multiple AI CLIs and synthesizes their answers."""
    config = load_config(config_file)

    # Override agents if specified
    if agents:
        agent_names = [a.strip() for a in agents.split(",")]
        for name, agent in config.agents.items():
            agent.enabled = name in agent_names
        # Also enable any specified agents that might be disabled
        for name in agent_names:
            if name in config.agents:
                config.agents[name].enabled = True

    # Override chairman if specified
    if chairman:
        config.chairman = chairman

    active = config.active_agents
    if not active:
        console.print("[bold red]No active agents.[/bold red] Configure agents with: council config --init")
        raise typer.Exit(1)

    print_banner()
    print_question(question)

    bridge = TmuxBridge(session_prefix=config.session_prefix)
    pipeline = CouncilPipeline(config=config, bridge=bridge)

    result = pipeline.run(
        question=question,
        on_stage_start=print_stage_start,
        on_agent_done=print_agent_done,
        on_stage_done=print_stage_done,
        use_tmux_parallel=parallel,
    )

    print_final_result(result, verbose=verbose)


@app.command()
def config(
    init: bool = typer.Option(
        False, "--init",
        help="Create default config file",
    ),
    show: bool = typer.Option(
        False, "--show",
        help="Show current config",
    ),
    path: bool = typer.Option(
        False, "--path",
        help="Print config file path",
    ),
):
    """Manage council configuration."""
    if init:
        config_path = save_default_config()
        console.print(f"[green]Config created at:[/green] {config_path}")
        console.print("[dim]Edit this file to enable/configure agents.[/dim]")
    elif show:
        cfg = load_config()
        console.print(f"[bold]Config file:[/bold] {CONFIG_FILE}")
        console.print(f"[bold]Chairman:[/bold] {cfg.chairman}")
        console.print(f"[bold]Active agents:[/bold]")
        for agent in cfg.active_agents:
            console.print(f"  - {agent.display_name} ({agent.name}): {agent.command} {' '.join(agent.args)}")
        if not cfg.active_agents:
            console.print("  [dim]None enabled. Run: council config --init[/dim]")
    elif path:
        console.print(str(CONFIG_FILE))
    else:
        config(init=False, show=True, path=False)


@app.command()
def models():
    """List available and configured agents."""
    cfg = load_config()
    from rich.table import Table
    from rich import box

    table = Table(title="Council Agents", box=box.ROUNDED)
    table.add_column("Name", style="bold")
    table.add_column("Display Name")
    table.add_column("Command")
    table.add_column("Status", justify="center")
    table.add_column("Role", justify="center")

    for name, agent in cfg.agents.items():
        status = "[green]enabled[/green]" if agent.enabled else "[dim]disabled[/dim]"
        role = "[bold yellow]chairman[/bold yellow]" if name == cfg.chairman else ""
        from council.display import get_agent_color
        color = get_agent_color(name)
        table.add_row(
            f"[{color}]{name}[/{color}]",
            agent.display_name,
            f"{agent.command} {' '.join(agent.args)}",
            status,
            role,
        )

    console.print(table)


@app.command()
def quick(
    question: str = typer.Argument(
        ...,
        help="The question to ask",
    ),
):
    """Quick mode: ask all agents independently (no review/synthesis). Fastest option."""
    config = load_config()
    active = config.active_agents

    if not active:
        console.print("[bold red]No active agents.[/bold red]")
        raise typer.Exit(1)

    print_banner()
    print_question(question)

    from council.prompts import build_stage1_prompt
    prompt = build_stage1_prompt(question)

    bridge = TmuxBridge(session_prefix=config.session_prefix)

    from council.display import print_verbose_responses
    responses = []
    for agent in active:
        console.print(f"  [dim]Querying {agent.display_name}...[/dim]")
        resp = bridge.query_agent(agent, prompt, "quick")
        print_agent_done(1, resp)
        responses.append(resp)

    console.print()
    print_verbose_responses(responses)


if __name__ == "__main__":
    app()
