"""3-stage council pipeline with streaming output and shared memory."""

from __future__ import annotations

import concurrent.futures
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from council.bridge import Bridge, AgentResponse
from council.config import CouncilConfig
from council.memory import (
    init_memory,
    load_memory,
    list_memories,
    save_learning,
    EXTRACT_LEARNINGS_PROMPT,
    MEMORY_DIR,
)
from council.prompts import (
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
)
from council.display import (
    console,
    print_stage_header,
    print_agent_result,
    print_stage_summary,
    print_final_result,
    print_memory_saved,
    print_memory_status,
    print_stats,
    StreamingDisplay,
)


@dataclass
class CouncilResult:
    question: str
    run_id: str
    stage1_responses: list[AgentResponse] = field(default_factory=list)
    stage2_reviews: list[AgentResponse] = field(default_factory=list)
    stage3_synthesis: AgentResponse | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def final_answer(self) -> str:
        if self.stage3_synthesis and self.stage3_synthesis.success:
            return self.stage3_synthesis.response
        successful = [r for r in self.stage1_responses if r.success]
        if successful:
            return successful[0].response
        return "Council failed to produce an answer."


class CouncilPipeline:
    """Orchestrates the 3-stage council deliberation with live feedback."""

    def __init__(self, config: CouncilConfig, bridge: Bridge):
        self.config = config
        self.bridge = bridge

    def run(
        self,
        question: str,
        verbose: bool = False,
        use_parallel: bool = True,
    ) -> CouncilResult:
        run_id = uuid.uuid4().hex[:8]
        result = CouncilResult(question=question, run_id=run_id)
        active_agents = self.config.active_agents
        stream = None  # Track for cleanup on interrupt

        if not active_agents:
            result.errors.append("No active agents configured.")
            console.print("[bold red]No active agents configured.[/bold red]")
            return result

        # Load shared memory and soul
        init_memory()
        memory = load_memory()
        soul = self.config.soul
        memory_count = len(list_memories())
        print_memory_status(memory_count)

        try:
            # ═══════════════════════════════════════════
            # STAGE 1: Independent Responses (parallel)
            # ═══════════════════════════════════════════
            print_stage_header(1, active_agents)

            # Build per-agent prompts (CLI agents get tool instructions, API agents don't)
            stage1_prompts = {
                a.name: build_stage1_prompt(brief=question, soul=soul, memory=memory, agent_type=a.type)
                for a in active_agents
            }

            if use_parallel and len(active_agents) > 1:
                stream = StreamingDisplay()
                with stream:
                    stream.start(active_agents)
                    responses = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=len(active_agents)) as pool:
                        def run_stage1(agent):
                            return self.bridge.query_agent(
                                agent, stage1_prompts[agent.name], run_id,
                                on_chunk=lambda chunk, _n=agent.name: stream.update_chunk(_n, chunk),
                            )
                        futures = {pool.submit(run_stage1, a): a for a in active_agents}
                        for future in concurrent.futures.as_completed(futures):
                            responses.append(future.result())

                    for r in responses:
                        stream.mark_done(r.agent_name, r.elapsed_seconds, r.success)
                stream = None
            else:
                responses = []
                for agent in active_agents:
                    stream = StreamingDisplay()
                    with stream:
                        stream.start([agent])
                        resp = self.bridge.query_agent(
                            agent, stage1_prompts[agent.name], run_id,
                            on_chunk=lambda chunk, _n=agent.name: stream.update_chunk(_n, chunk),
                        )
                        stream.mark_done(agent.name, resp.elapsed_seconds, resp.success)
                    stream = None
                    responses.append(resp)
                    print_agent_result(resp)

            result.stage1_responses = responses
            successful = [r for r in responses if r.success]
            print_stage_summary(1, responses)

            if verbose:
                for r in successful:
                    print_agent_result(r, show_content=True)

            if len(successful) < 2:
                if len(successful) == 1:
                    console.print("  [yellow]Only 1 agent succeeded — skipping peer review[/yellow]")
                    result.stage3_synthesis = successful[0]
                    self._save_session(result)
                    self._save_learnings(result)
                    print_final_result(successful[0])
                    return result
                result.errors.append("All agents failed in Stage 1.")
                console.print("  [bold red]All agents failed.[/bold red]")
                return result

            # ═══════════════════════════════════════════
            # STAGE 2: Anonymized Peer Review (parallel)
            # ═══════════════════════════════════════════
            review_agents = [a for a in active_agents if any(r.agent_name == a.name for r in successful)]
            print_stage_header(2, review_agents)

            response_dicts = [
                {"agent_id": r.agent_name, "agent_name": r.display_name, "response": r.response}
                for r in successful
            ]

            # Build per-agent review prompts (excluding self)
            review_tasks = []
            for agent in review_agents:
                other_responses = [r for r in response_dicts if r["agent_id"] != agent.name]
                if not other_responses:
                    continue
                prompt = build_stage2_prompt(
                    brief=question,
                    responses=other_responses,
                    rubric=self.config.rubric,
                    soul=soul,
                    memory=memory,
                )
                review_tasks.append((agent, prompt))

            # Run reviews in parallel
            if len(review_tasks) > 1:
                stream = StreamingDisplay()
                reviews = []
                with stream:
                    stream.start([t[0] for t in review_tasks])
                    with concurrent.futures.ThreadPoolExecutor(max_workers=len(review_tasks)) as pool:
                        def run_review(agent, prompt):
                            return self.bridge.query_agent(
                                agent, prompt, run_id,
                                on_chunk=lambda chunk, _n=agent.name: stream.update_chunk(_n, chunk),
                            )
                        futures = {pool.submit(run_review, a, p): a for a, p in review_tasks}
                        for future in concurrent.futures.as_completed(futures):
                            rev = future.result()
                            stream.mark_done(rev.agent_name, rev.elapsed_seconds, rev.success)
                            reviews.append(rev)
                stream = None
            else:
                reviews = []
                for agent, prompt in review_tasks:
                    stream = StreamingDisplay()
                    with stream:
                        stream.start([agent])
                        rev = self.bridge.query_agent(
                            agent, prompt, run_id,
                            on_chunk=lambda chunk, _n=agent.name: stream.update_chunk(_n, chunk),
                        )
                        stream.mark_done(agent.name, rev.elapsed_seconds, rev.success)
                    stream = None
                    reviews.append(rev)

            for rev in reviews:
                print_agent_result(rev)

            result.stage2_reviews = reviews
            successful_reviews = [r for r in reviews if r.success]
            print_stage_summary(2, reviews)

            if verbose:
                for r in successful_reviews:
                    print_agent_result(r, show_content=True)

            # ═══════════════════════════════════════════
            # STAGE 3: Chairman Synthesis
            # ═══════════════════════════════════════════
            chairman = self.config.chairman_agent
            print_stage_header(3, [chairman])

            if successful_reviews:
                # Strip agent identity from reviews to prevent deanonymization
                review_dicts = [
                    {"agent_id": f"reviewer_{i}", "agent_name": f"Reviewer {i+1}", "response": r.response}
                    for i, r in enumerate(successful_reviews)
                ]
            else:
                console.print("  [yellow]No reviews succeeded — synthesizing from responses only[/yellow]")
                review_dicts = []

            stage3_prompt = build_stage3_prompt(
                brief=question,
                responses=response_dicts,
                reviews=review_dicts,
                preserve_dissent=self.config.preserve_dissent,
                soul=soul,
                memory=memory,
            )

            stream = StreamingDisplay()
            with stream:
                stream.start([chairman])
                synthesis = self.bridge.query_agent(
                    chairman, stage3_prompt, run_id,
                    on_chunk=lambda chunk: stream.update_chunk(chairman.name, chunk),
                )
                stream.mark_done(chairman.name, synthesis.elapsed_seconds, synthesis.success)
            stream = None

            result.stage3_synthesis = synthesis

            # Display final answer
            print_final_result(synthesis, fallback=result.final_answer)

            # Stats
            print_stats(result.stage1_responses, result.stage2_reviews, result.stage3_synthesis)

            # Save session transcript and learnings
            self._save_session(result)
            self._save_learnings(result)

        except KeyboardInterrupt:
            if stream:
                stream.stop()
            console.print("\n  [yellow]Council interrupted.[/yellow]")
            result.errors.append("Interrupted by user")
            self._save_session(result)
        except Exception as e:
            if stream:
                stream.stop()
            console.print(f"\n  [bold red]Pipeline error:[/bold red] {e}")
            result.errors.append(f"Pipeline exception: {e}")
            self._save_session(result)

        return result

    def _save_session(self, result: CouncilResult):
        """Save full session transcript as JSON."""
        sessions_dir = MEMORY_DIR / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = sessions_dir / f"{timestamp}_{result.run_id}.json"

        def serialize_response(r: AgentResponse) -> dict:
            return {
                "agent": r.agent_name,
                "display_name": r.display_name,
                "response": r.response,
                "elapsed_seconds": r.elapsed_seconds,
                "success": r.success,
                "error": r.error,
                "cost_usd": r.cost_usd,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
            }

        session = {
            "run_id": result.run_id,
            "question": result.question,
            "timestamp": datetime.now().isoformat(),
            "stage1": [serialize_response(r) for r in result.stage1_responses],
            "stage2": [serialize_response(r) for r in result.stage2_reviews],
            "stage3": serialize_response(result.stage3_synthesis) if result.stage3_synthesis else None,
            "final_answer": result.final_answer,
            "errors": result.errors,
        }

        filepath.write_text(json.dumps(session, indent=2))
        console.print(f"  [dim]Session saved: {filepath.name}[/dim]")

    def _save_learnings(self, result: CouncilResult):
        """Extract and save learnings from this session to shared memory."""
        if not result.stage3_synthesis or not result.stage3_synthesis.success:
            return

        synthesis = result.stage3_synthesis.response

        # Extract disagreements section if present
        disagreements = ""
        if "## Points of Dissent" in synthesis:
            parts = synthesis.split("## Points of Dissent")
            if len(parts) > 1:
                rest = parts[1]
                next_section = rest.find("\n## ")
                disagreements = rest[:next_section].strip() if next_section > 0 else rest.strip()

        learning_prompt = EXTRACT_LEARNINGS_PROMPT.format(
            question=result.question,
            synthesis=synthesis[:2000],
            disagreements=disagreements[:500] if disagreements else "None identified",
        )

        chairman = self.config.chairman_agent
        learning_resp = self.bridge.query_agent(
            chairman, learning_prompt, result.run_id + "-learn"
        )

        if learning_resp.success and learning_resp.response:
            path = save_learning(
                learning=learning_resp.response,
                question=result.question,
                session_id=result.run_id,
            )
            print_memory_saved(path)
