"""3-stage council pipeline with streaming output and shared memory."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from council.bridge import Bridge, AgentResponse
from council.config import CouncilConfig
from council.memory import (
    init_memory,
    load_memory,
    list_memories,
    save_learning,
    EXTRACT_LEARNINGS_PROMPT,
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

        if not active_agents:
            result.errors.append("No active agents configured.")
            console.print("[bold red]No active agents configured.[/bold red]")
            return result

        # Load shared memory
        init_memory()
        memory = load_memory()
        soul = self.config.soul
        memory_count = len(list_memories())
        print_memory_status(memory_count)

        # ═══════════════════════════════════════════
        # STAGE 1: Independent Responses
        # ═══════════════════════════════════════════
        print_stage_header(1, active_agents)
        stage1_prompt = build_stage1_prompt(brief=question, soul=soul, memory=memory)

        if use_parallel and len(active_agents) > 1:
            stream = StreamingDisplay()
            stream.start(active_agents)

            def on_parallel_chunk(agent_name, chunk):
                stream.update_chunk(agent_name, chunk)

            responses = self.bridge.query_agents_parallel(
                active_agents, stage1_prompt, run_id,
                on_chunk=on_parallel_chunk,
            )
            for r in responses:
                stream.mark_done(r.agent_name, r.elapsed_seconds, r.success)

            stream.stop()
        else:
            responses = []
            for agent in active_agents:
                stream = StreamingDisplay()
                stream.start([agent])

                def on_chunk(chunk, _name=agent.name):
                    stream.update_chunk(_name, chunk)

                resp = self.bridge.query_agent(agent, stage1_prompt, run_id, on_chunk=on_chunk)
                stream.mark_done(agent.name, resp.elapsed_seconds, resp.success)
                stream.stop()

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
                self._save_learnings(result)
                answer = print_final_result(successful[0])
                return result
            result.errors.append("All agents failed in Stage 1.")
            console.print("  [bold red]All agents failed.[/bold red]")
            return result

        # ═══════════════════════════════════════════
        # STAGE 2: Anonymized Peer Review
        # ═══════════════════════════════════════════
        # Each agent reviews ONLY other agents' responses (not their own)
        review_agents = [a for a in active_agents if any(r.agent_name == a.name for r in successful)]
        print_stage_header(2, review_agents)

        response_dicts = [
            {"agent_id": r.agent_name, "agent_name": r.display_name, "response": r.response}
            for r in successful
        ]

        reviews = []
        for agent in review_agents:
            # Filter out this agent's own response to prevent self-review bias
            other_responses = [r for r in response_dicts if r["agent_id"] != agent.name]
            if not other_responses:
                continue  # Nothing to review

            stage2_prompt = build_stage2_prompt(
                brief=question,
                responses=other_responses,
                rubric=self.config.rubric,
            )

            stream = StreamingDisplay()
            stream.start([agent])

            def on_chunk(chunk, _name=agent.name):
                stream.update_chunk(_name, chunk)

            rev = self.bridge.query_agent(agent, stage2_prompt, run_id, on_chunk=on_chunk)
            stream.mark_done(agent.name, rev.elapsed_seconds, rev.success)
            stream.stop()

            reviews.append(rev)
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
            review_dicts = [
                {"agent_id": r.agent_name, "agent_name": r.display_name, "response": r.response}
                for r in successful_reviews
            ]
        else:
            console.print("  [yellow]No reviews succeeded — synthesizing from responses only[/yellow]")
            review_dicts = []

        stage3_prompt = build_stage3_prompt(
            brief=question,
            responses=response_dicts,
            reviews=review_dicts,
            preserve_dissent=self.config.preserve_dissent,
        )

        stream = StreamingDisplay()
        stream.start([chairman])

        def on_chunk(chunk):
            stream.update_chunk(chairman.name, chunk)

        synthesis = self.bridge.query_agent(chairman, stage3_prompt, run_id, on_chunk=on_chunk)
        stream.mark_done(chairman.name, synthesis.elapsed_seconds, synthesis.success)
        stream.stop()

        result.stage3_synthesis = synthesis

        # Display final answer
        answer = print_final_result(synthesis, fallback=result.final_answer)

        # Stats
        print_stats(result.stage1_responses, result.stage2_reviews, result.stage3_synthesis)

        # Save learnings to memory
        self._save_learnings(result)

        return result

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
                # Get until next ## or end
                next_section = rest.find("\n## ")
                disagreements = rest[:next_section].strip() if next_section > 0 else rest.strip()

        # Use the chairman to extract learnings
        learning_prompt = EXTRACT_LEARNINGS_PROMPT.format(
            question=result.question,
            synthesis=synthesis[:2000],  # Truncate to avoid huge prompts
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
