"""Interactive council session — the only entry point."""

from __future__ import annotations

from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown
from rich.rule import Rule

from council.config import load_config, CouncilConfig
from council.bridge import Bridge
from council.pipeline import CouncilPipeline
from council.memory import init_memory, load_memory, save_correction, list_memories
from council.display import (
    console,
    print_banner,
    print_memory_status,
    get_agent_color,
)
from council.prompts import CLARIFY_SYSTEM


def run():
    """Main interactive session."""
    config = load_config()
    active = config.active_agents

    print_banner()

    if not active:
        console.print("[bold red]No active agents found.[/bold red]")
        console.print("Install CLI agents: claude (Claude Code), codex (Codex CLI), gemini (Gemini CLI)")
        console.print("Then edit ~/.config/council/config.yaml to enable them.")
        return

    # Show active agents
    agent_list = "  ".join(
        f"[{get_agent_color(a.name)}]{a.display_name}[/{get_agent_color(a.name)}]"
        for a in active
    )
    console.print(f"  Council: {agent_list}")
    console.print(f"  Chairman: [{get_agent_color(config.chairman)}]{config.chairman_agent.display_name}[/{get_agent_color(config.chairman)}]")

    # Show memory status
    init_memory()
    memories = list_memories()
    if memories:
        console.print(f"  Memory: {len(memories)} entries loaded")
    console.print()

    bridge = Bridge(config=config)
    pipeline = CouncilPipeline(config=config, bridge=bridge)

    # ═══════════════════════════════════════════
    # MAIN LOOP
    # ═══════════════════════════════════════════
    while True:
        try:
            console.print(Rule(style="dim"))
            question = Prompt.ask("\n[bold]What do you want the council to investigate?[/bold]\n")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Council adjourned.[/dim]")
            break

        if not question.strip():
            continue

        if question.strip().lower() in ("quit", "exit", "q"):
            console.print("[dim]Council adjourned.[/dim]")
            break

        if question.strip().lower() == "memory":
            _show_memory()
            continue

        if question.strip().lower() == "models":
            _show_models(config)
            continue

        if question.strip().lower() == "help":
            console.print("  [dim]Commands: memory, models, help, quit[/dim]")
            console.print("  [dim]Prefix with ! to skip clarification (e.g. !What is X?)[/dim]")
            console.print()
            continue

        # ─── Clarification Phase ────────────────
        skip_clarify = question.strip().startswith("!")
        if skip_clarify:
            question = question.strip()[1:].strip()
            brief = question
        else:
            brief = _clarify(question, config, bridge)
            if brief is None:
                continue  # User cancelled

        # ─── Council Deliberation ───────────────
        console.print()
        console.print(Rule("Council is working", style="bold cyan"))
        console.print()

        result = pipeline.run(
            question=brief,
            verbose=False,
            use_parallel=len(active) > 1,
        )

        # ─── Post-session feedback ──────────────
        console.print()
        try:
            feedback = Prompt.ask(
                "[dim]Any corrections or feedback? (enter to skip)[/dim]",
                default="",
            )
            if feedback.strip():
                path = save_correction(feedback, brief)
                console.print(f"  [dim]Feedback saved: {path}[/dim]")
        except (KeyboardInterrupt, EOFError):
            pass


def _clarify(question: str, config: CouncilConfig, bridge: Bridge) -> str | None:
    """Clarification phase: the lead agent helps refine the question.

    Returns the refined brief, or None if cancelled.
    """
    soul = config.soul
    memory = load_memory()
    chairman = config.chairman_agent

    agent_list = ", ".join(a.display_name for a in config.active_agents)
    memory_section = f"## Council Memory\n{memory}" if memory else ""
    system = CLARIFY_SYSTEM.format(
        agent_list=agent_list,
        soul=soul,
        memory_section=memory_section,
    )

    clarify_prompt = (
        f"{system}\n\n---\n\n"
        f"The user says:\n\n{question}\n\n"
        f"Ask 1-3 brief clarifying questions to understand exactly what they want. "
        f"Be concise. If the request is already clear, just confirm and produce the brief."
    )

    console.print()
    console.print(f"  [dim]Consulting {chairman.display_name} to clarify scope...[/dim]")

    resp = bridge.query_agent(chairman, clarify_prompt, "clarify")

    if not resp.success:
        console.print(f"  [red]Clarification failed: {resp.error}[/red]")
        console.print("  [yellow]Proceeding with original question.[/yellow]")
        return question

    console.print()
    console.print(Panel(
        Markdown(resp.response),
        title=f"[bold]{chairman.display_name}[/bold]",
        border_style=get_agent_color(chairman.name),
        padding=(1, 2),
    ))

    # Conversation loop for clarification
    conversation = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
        {"role": "assistant", "content": resp.response},
    ]

    while True:
        try:
            console.print()
            user_input = Prompt.ask("[bold]Your response[/bold] [dim](or 'go' to start, 'cancel' to abort)[/dim]")
        except (KeyboardInterrupt, EOFError):
            return None

        if not user_input.strip():
            continue

        if user_input.strip().lower() == "cancel":
            console.print("[dim]Cancelled.[/dim]")
            return None

        if user_input.strip().lower() in ("go", "yes", "ok", "start", "confirm", "y"):
            # Ask the agent to produce the final brief
            brief_prompt = (
                f"{system}\n\n"
                + "\n".join(
                    f"{'User' if m['role'] == 'user' else 'Agent'}: {m['content']}"
                    for m in conversation if m['role'] != 'system'
                )
                + f"\nUser: {user_input}\n\n"
                + "Now produce a CLEAR, CONCISE BRIEF for the council. "
                + "Format: one paragraph describing the task, constraints, and expected output. "
                + "No preamble — just the brief itself."
            )

            console.print(f"  [dim]Generating brief...[/dim]")
            brief_resp = bridge.query_agent(chairman, brief_prompt, "brief")

            if brief_resp.success:
                brief = brief_resp.response
            else:
                brief = question

            console.print()
            console.print(Panel(
                brief,
                title="[bold green]Council Brief[/bold green]",
                border_style="green",
                padding=(1, 2),
            ))
            return brief

        # Continue conversation
        conversation.append({"role": "user", "content": user_input})

        follow_up_prompt = (
            f"{system}\n\n"
            + "\n".join(
                f"{'User' if m['role'] == 'user' else 'Agent'}: {m['content']}"
                for m in conversation if m['role'] != 'system'
            )
            + "\n\nContinue the clarification. Be concise."
        )

        console.print(f"  [dim]Thinking...[/dim]")
        follow_resp = bridge.query_agent(chairman, follow_up_prompt, "clarify")

        if follow_resp.success:
            conversation.append({"role": "assistant", "content": follow_resp.response})
            console.print()
            console.print(Panel(
                Markdown(follow_resp.response),
                title=f"[bold]{chairman.display_name}[/bold]",
                border_style=get_agent_color(chairman.name),
                padding=(1, 2),
            ))
        else:
            console.print(f"  [red]{follow_resp.error}[/red]")


def _show_memory():
    memories = list_memories()
    if not memories:
        console.print("  [dim]No memories yet. Memories are saved after each council session.[/dim]")
        return
    console.print(f"\n  [bold]Council Memory ({len(memories)} entries)[/bold]\n")
    for m in memories[:20]:
        console.print(f"  [{m['category']}] {m['name']} [dim]({m['modified'][:10]})[/dim]")
    console.print()


def _show_models(config: CouncilConfig):
    console.print()
    for name, agent in config.agents.items():
        color = get_agent_color(name)
        status = "[green]on[/green]" if agent.enabled else "[dim]off[/dim]"
        role = " [yellow](chairman)[/yellow]" if name == config.chairman else ""
        if agent.type == "openrouter":
            via = f"[dim]via OpenRouter ({agent.model})[/dim]"
        else:
            via = f"[dim]via CLI ({agent.command})[/dim]"
        console.print(f"  [{color}]{agent.display_name}[/{color}] {status}{role} {via}")
    console.print()


if __name__ == "__main__":
    run()
