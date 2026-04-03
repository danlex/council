"""3-stage council pipeline: Respond -> Review -> Synthesize."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from council.bridge import TmuxBridge, AgentResponse
from council.config import CouncilConfig
from council.prompts import (
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
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
        # Fallback: return best individual response
        successful = [r for r in self.stage1_responses if r.success]
        if successful:
            return successful[0].response
        return "Council failed to produce an answer."


class CouncilPipeline:
    """Orchestrates the 3-stage council deliberation."""

    def __init__(self, config: CouncilConfig, bridge: TmuxBridge):
        self.config = config
        self.bridge = bridge

    def run(
        self,
        question: str,
        on_stage_start=None,
        on_agent_done=None,
        on_stage_done=None,
        use_tmux_parallel: bool = False,
    ) -> CouncilResult:
        run_id = uuid.uuid4().hex[:8]
        result = CouncilResult(question=question, run_id=run_id)
        active_agents = self.config.active_agents

        if len(active_agents) == 0:
            result.errors.append("No active agents configured.")
            return result

        # --- STAGE 1: Independent Responses ---
        if on_stage_start:
            on_stage_start(1, "Independent Responses", active_agents)

        soul = self.config.soul
        stage1_prompt = build_stage1_prompt(question, soul=soul)

        if use_tmux_parallel and len(active_agents) > 1:
            responses = self.bridge.query_agents_parallel_tmux(
                active_agents, stage1_prompt, run_id
            )
        else:
            responses = []
            for agent in active_agents:
                resp = self.bridge.query_agent(agent, stage1_prompt, run_id)
                responses.append(resp)
                if on_agent_done:
                    on_agent_done(1, resp)

        result.stage1_responses = responses
        successful = [r for r in responses if r.success]

        if on_stage_done:
            on_stage_done(1, responses)

        if len(successful) < 2:
            # Need at least 2 responses for peer review to be meaningful
            if len(successful) == 1:
                # Skip review, just return the single response
                result.stage3_synthesis = successful[0]
                return result
            result.errors.append("All agents failed in Stage 1.")
            return result

        # --- STAGE 2: Anonymized Peer Review ---
        if on_stage_start:
            on_stage_start(2, "Anonymized Peer Review", active_agents)

        response_dicts = [
            {"agent_id": r.agent_name, "agent_name": r.display_name, "response": r.response}
            for r in successful
        ]

        stage2_prompt = build_stage2_prompt(
            question=question,
            responses=response_dicts,
            rubric=self.config.rubric,
        )

        # Each active agent reviews all responses
        reviews = []
        for agent in active_agents:
            if not any(r.agent_name == agent.name and r.success for r in successful):
                continue  # Skip agents that failed in stage 1
            rev = self.bridge.query_agent(agent, stage2_prompt, run_id)
            reviews.append(rev)
            if on_agent_done:
                on_agent_done(2, rev)

        result.stage2_reviews = reviews
        successful_reviews = [r for r in reviews if r.success]

        if on_stage_done:
            on_stage_done(2, reviews)

        # --- STAGE 3: Chairman Synthesis ---
        if on_stage_start:
            on_stage_start(3, "Chairman Synthesis", [self.config.chairman_agent])

        review_dicts = [
            {"agent_id": r.agent_name, "agent_name": r.display_name, "response": r.response}
            for r in successful_reviews
        ]

        stage3_prompt = build_stage3_prompt(
            question=question,
            responses=response_dicts,
            reviews=review_dicts,
            preserve_dissent=self.config.preserve_dissent,
        )

        chairman = self.config.chairman_agent
        synthesis = self.bridge.query_agent(chairman, stage3_prompt, run_id)
        result.stage3_synthesis = synthesis

        if on_agent_done:
            on_agent_done(3, synthesis)
        if on_stage_done:
            on_stage_done(3, [synthesis])

        return result
