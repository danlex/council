"""Evaluation framework: prove (or disprove) the council outperforms single models.

Runs benchmark questions through:
  1. Each agent individually (baseline)
  2. The full council pipeline (council)

Then uses a separate judge to score each answer on:
  - Accuracy: factual correctness
  - Completeness: coverage of key points
  - Bias detection: identifies where single models have blind spots
  - Nuance: handles uncertainty and disagreement honestly

Usage:
  ./c → eval           (from REPL)
  python -m council.eval  (from terminal)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from council.config import load_config, CouncilConfig, AgentConfig
from council.bridge import Bridge, AgentResponse
from council.memory import init_memory, load_memory, MEMORY_DIR
from council.prompts import build_stage1_prompt, build_stage2_prompt, build_stage3_prompt
from council.display import console, get_agent_color

# ─── Benchmark Questions ────────────────────────────────────────────────

BENCHMARK = [
    {
        "id": "factual_contested",
        "question": "Is nuclear energy a good solution to climate change?",
        "category": "contested",
        "key_points": [
            "Low carbon emissions during operation",
            "High upfront costs and long build times",
            "Nuclear waste storage challenges",
            "Safety concerns (Chernobyl, Fukushima)",
            "Reliable baseload power unlike solar/wind",
            "Uranium supply limits vs thorium potential",
            "Public perception and political feasibility",
        ],
        "expected_bias": "Models often lean pro-nuclear or anti-nuclear based on training data. A good answer presents BOTH sides with evidence.",
    },
    {
        "id": "reasoning_tradeoff",
        "question": "Should a 5-person startup use microservices or a monolith?",
        "category": "reasoning",
        "key_points": [
            "Monolith is simpler for small teams",
            "Microservices add operational complexity",
            "Monolith can be modularized later",
            "Microservices allow independent deployment",
            "Team size matters more than architecture",
            "Database boundaries are the real question",
        ],
        "expected_bias": "Models trained on tech blogs often over-recommend microservices. The correct answer for a 5-person startup is almost certainly monolith-first.",
    },
    {
        "id": "factual_hard",
        "question": "What are the actual, measured differences in developer productivity between statically and dynamically typed languages?",
        "category": "factual",
        "key_points": [
            "Limited rigorous empirical studies exist",
            "Hanenberg et al. (2014) found mixed results",
            "Type systems help more with large codebases",
            "IDE support may matter more than type system",
            "Most comparisons confound language with ecosystem",
            "Should acknowledge lack of definitive evidence",
        ],
        "expected_bias": "Models tend to confidently claim static typing is better, but the empirical evidence is surprisingly weak. Honest uncertainty is the correct answer.",
    },
    {
        "id": "values_tension",
        "question": "Should AI companies open-source their most capable models?",
        "category": "values",
        "key_points": [
            "Safety vs access tension",
            "Democratization argument",
            "Misuse risks increase with capability",
            "Open-source enables safety research",
            "Competitive dynamics and moats",
            "Differential access creates power imbalances",
            "Historical precedent (encryption, nuclear)",
        ],
        "expected_bias": "Different models have different institutional biases — Claude may favor Anthropic's cautious stance, Llama may favor Meta's open approach.",
    },
    {
        "id": "technical_deep",
        "question": "What are the fundamental limits of transformer architectures, and what will likely replace them?",
        "category": "technical",
        "key_points": [
            "Quadratic attention scaling",
            "Limited reasoning/planning capability",
            "Context window vs true long-term memory",
            "State-space models (Mamba) as alternative",
            "Mixture-of-experts scaling approach",
            "Hybrid architectures emerging",
            "Honest uncertainty about what comes next",
        ],
        "expected_bias": "Models may overstate their own architecture's capabilities. Should acknowledge genuine uncertainty about what replaces transformers.",
    },
]

JUDGE_PROMPT = """You are an impartial evaluator. Score the following answer to a benchmark question.

## Question
{question}

## Key Points That Should Be Covered
{key_points}

## Known Bias Risk
{expected_bias}

## Answer to Evaluate
{answer}

---

Score on these dimensions (1-10):

1. **Accuracy** (1-10): Are the factual claims correct? Does it avoid hallucination?
2. **Completeness** (1-10): How many of the key points does it cover?
3. **Nuance** (1-10): Does it handle uncertainty honestly? Does it present multiple perspectives where appropriate?
4. **Bias Resistance** (1-10): Does it avoid the known bias risk described above? Does it present both sides?

Respond in EXACTLY this JSON format (no other text):
{{"accuracy": N, "completeness": N, "nuance": N, "bias_resistance": N, "notes": "brief explanation"}}
"""


@dataclass
class EvalResult:
    question_id: str
    question: str
    agent: str
    answer: str
    elapsed: float
    scores: dict = field(default_factory=dict)
    judge_notes: str = ""


def run_eval(questions: list[dict] | None = None):
    """Run the full evaluation benchmark."""
    config = load_config()
    bridge = Bridge(config=config)
    active = config.active_agents
    questions = questions or BENCHMARK

    if not active:
        console.print("[bold red]No active agents.[/bold red]")
        return

    console.print()
    console.print("[bold]COUNCIL EVALUATION[/bold]")
    console.print(f"  {len(questions)} questions x {len(active)} agents + full council")
    console.print(f"  Judge: {config.chairman_agent.display_name}")
    console.print()

    init_memory()
    memory = ""  # Eval runs without memory bias
    soul = config.soul

    all_results: list[EvalResult] = []

    for qi, q in enumerate(questions):
        console.print(f"  [bold]Q{qi+1}/{len(questions)}:[/bold] {q['question'][:70]}...")
        console.print()

        # ─── Single-agent baselines ─────────────────────
        for agent in active:
            console.print(f"    [{get_agent_color(agent.name)}]{agent.display_name}[/{get_agent_color(agent.name)}]...", end=" ")
            prompt = build_stage1_prompt(brief=q["question"], soul=soul, memory=memory, agent_type=agent.type)
            start = time.time()
            resp = bridge.query_agent(agent, prompt, f"eval-{q['id']}-{agent.name}")
            elapsed = time.time() - start

            if resp.success:
                console.print(f"[green]{elapsed:.0f}s[/green] ({len(resp.response)} chars)")
                all_results.append(EvalResult(
                    question_id=q["id"], question=q["question"],
                    agent=agent.display_name, answer=resp.response, elapsed=elapsed,
                ))
            else:
                console.print(f"[red]failed[/red]: {resp.error[:40]}")

        # ─── Full council ───────────────────────────────
        console.print(f"    [bold cyan]Full Council[/bold cyan]...", end=" ")
        council_answer = _run_mini_council(config, bridge, q["question"], soul, memory)
        if council_answer:
            console.print(f"[green]done[/green] ({len(council_answer)} chars)")
            all_results.append(EvalResult(
                question_id=q["id"], question=q["question"],
                agent="COUNCIL (5 agents)", answer=council_answer, elapsed=0,
            ))
        else:
            console.print("[red]failed[/red]")

        console.print()

    # ─── Judge all answers ──────────────────────────────
    console.print("[bold]Judging answers...[/bold]")
    judge = config.chairman_agent

    for result in all_results:
        q = next(bq for bq in questions if bq["id"] == result.question_id)
        judge_prompt = JUDGE_PROMPT.format(
            question=q["question"],
            key_points="\n".join(f"- {p}" for p in q["key_points"]),
            expected_bias=q["expected_bias"],
            answer=result.answer[:3000],
        )
        jr = bridge.query_agent(judge, judge_prompt, f"judge-{result.question_id}-{result.agent[:10]}")
        if jr.success:
            try:
                scores = json.loads(jr.response.strip())
                result.scores = {k: v for k, v in scores.items() if k != "notes"}
                result.judge_notes = scores.get("notes", "")
            except (json.JSONDecodeError, KeyError):
                # Try to extract JSON from response
                text = jr.response
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        scores = json.loads(text[start:end])
                        result.scores = {k: v for k, v in scores.items() if k != "notes"}
                        result.judge_notes = scores.get("notes", "")
                    except json.JSONDecodeError:
                        result.scores = {}
                        result.judge_notes = "Judge response not parseable"

    # ─── Display results ────────────────────────────────
    _display_results(all_results, questions)
    _save_eval(all_results, questions)


def _run_mini_council(config: CouncilConfig, bridge: Bridge, question: str, soul: str, memory: str) -> str | None:
    """Run a minimal council (no display, no memory saving) for eval."""
    import concurrent.futures

    active = config.active_agents
    prompts = {
        a.name: build_stage1_prompt(brief=question, soul=soul, memory=memory, agent_type=a.type)
        for a in active
    }

    # Stage 1
    responses = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(active)) as pool:
        futures = {pool.submit(bridge.query_agent, a, prompts[a.name], "eval-council"): a for a in active}
        for f in concurrent.futures.as_completed(futures):
            responses.append(f.result())

    successful = [r for r in responses if r.success]
    if len(successful) < 2:
        return successful[0].response if successful else None

    response_dicts = [
        {"agent_id": r.agent_name, "agent_name": r.display_name, "response": r.response}
        for r in successful
    ]

    # Stage 2 (parallel)
    review_agents = [a for a in active if any(r.agent_name == a.name for r in successful)]
    review_tasks = []
    for agent in review_agents:
        others = [r for r in response_dicts if r["agent_id"] != agent.name]
        if others:
            prompt = build_stage2_prompt(brief=question, responses=others, rubric=config.rubric, soul=soul, memory=memory)
            review_tasks.append((agent, prompt))

    reviews = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(review_tasks)) as pool:
        futures = {pool.submit(bridge.query_agent, a, p, "eval-rev"): a for a, p in review_tasks}
        for f in concurrent.futures.as_completed(futures):
            reviews.append(f.result())

    successful_reviews = [r for r in reviews if r.success]
    review_dicts = [
        {"agent_id": f"reviewer_{i}", "agent_name": f"Reviewer {i+1}", "response": r.response}
        for i, r in enumerate(successful_reviews)
    ]

    # Stage 3
    chairman = config.chairman_agent
    stage3_prompt = build_stage3_prompt(
        brief=question, responses=response_dicts, reviews=review_dicts,
        preserve_dissent=config.preserve_dissent, soul=soul, memory=memory,
    )
    synthesis = bridge.query_agent(chairman, stage3_prompt, "eval-synth")
    return synthesis.response if synthesis.success else None


def _display_results(results: list[EvalResult], questions: list[dict]):
    """Display a comparison table of scores."""
    from rich.table import Table
    from rich import box

    console.print()
    console.print("[bold]EVALUATION RESULTS[/bold]")
    console.print()

    # Per-question comparison
    for q in questions:
        q_results = [r for r in results if r.question_id == q["id"] and r.scores]
        if not q_results:
            continue

        table = Table(
            title=f"Q: {q['question'][:60]}...",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold",
        )
        table.add_column("Agent", style="bold", min_width=18)
        table.add_column("Accuracy", justify="center")
        table.add_column("Complete", justify="center")
        table.add_column("Nuance", justify="center")
        table.add_column("Bias Resist", justify="center")
        table.add_column("AVG", justify="center", style="bold")

        for r in sorted(q_results, key=lambda x: -sum(x.scores.get(k, 0) for k in ["accuracy", "completeness", "nuance", "bias_resistance"])):
            a = r.scores.get("accuracy", 0)
            c = r.scores.get("completeness", 0)
            n = r.scores.get("nuance", 0)
            b = r.scores.get("bias_resistance", 0)
            avg = (a + c + n + b) / 4

            def color(v):
                if v >= 8: return f"[green]{v}[/green]"
                if v >= 6: return f"[yellow]{v}[/yellow]"
                return f"[red]{v}[/red]"

            is_council = "COUNCIL" in r.agent
            name = f"[bold cyan]{r.agent}[/bold cyan]" if is_council else r.agent
            avg_str = f"[bold cyan]{avg:.1f}[/bold cyan]" if is_council else f"{avg:.1f}"

            table.add_row(name, color(a), color(c), color(n), color(b), avg_str)

        console.print(table)
        console.print()

    # Overall summary
    agents = set(r.agent for r in results)
    console.print("[bold]OVERALL AVERAGES[/bold]")
    summary = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    summary.add_column("Agent", style="bold", min_width=18)
    summary.add_column("Avg Score", justify="center")
    summary.add_column("Questions", justify="center")

    agent_avgs = []
    for agent in sorted(agents):
        agent_results = [r for r in results if r.agent == agent and r.scores]
        if not agent_results:
            continue
        all_scores = []
        for r in agent_results:
            vals = [v for k, v in r.scores.items() if isinstance(v, (int, float))]
            if vals:
                all_scores.append(sum(vals) / len(vals))
        if all_scores:
            avg = sum(all_scores) / len(all_scores)
            agent_avgs.append((agent, avg, len(agent_results)))

    for agent, avg, count in sorted(agent_avgs, key=lambda x: -x[1]):
        is_council = "COUNCIL" in agent
        name = f"[bold cyan]{agent}[/bold cyan]" if is_council else agent
        score_str = f"[bold cyan]{avg:.1f}[/bold cyan]" if is_council else f"{avg:.1f}"
        summary.add_row(name, score_str, str(count))

    console.print(summary)
    console.print()

    # Council vs best single agent
    council_avg = next((a for a, _, _ in agent_avgs if "COUNCIL" in a), None)
    single_avgs = [(a, s) for a, s, _ in agent_avgs if "COUNCIL" not in a]
    if council_avg and single_avgs:
        best_single = max(single_avgs, key=lambda x: x[1])
        c_score = next(s for a, s, _ in agent_avgs if "COUNCIL" in a)
        diff = c_score - best_single[1]
        if diff > 0:
            console.print(f"  [bold green]Council beats best single agent ({best_single[0]}) by +{diff:.1f} points[/bold green]")
        elif diff < 0:
            console.print(f"  [bold red]Council loses to best single agent ({best_single[0]}) by {diff:.1f} points[/bold red]")
        else:
            console.print(f"  [yellow]Council ties with best single agent ({best_single[0]})[/yellow]")
    console.print()


def _save_eval(results: list[EvalResult], questions: list[dict]):
    """Save evaluation results to a JSON file."""
    eval_dir = MEMORY_DIR / "evals"
    eval_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = eval_dir / f"eval_{timestamp}.json"

    data = {
        "timestamp": datetime.now().isoformat(),
        "questions": len(questions),
        "results": [
            {
                "question_id": r.question_id,
                "question": r.question,
                "agent": r.agent,
                "scores": r.scores,
                "judge_notes": r.judge_notes,
                "elapsed": r.elapsed,
                "answer_length": len(r.answer),
            }
            for r in results
        ],
    }
    filepath.write_text(json.dumps(data, indent=2))
    console.print(f"  [dim]Eval saved: {filepath.name}[/dim]")


if __name__ == "__main__":
    run_eval()
