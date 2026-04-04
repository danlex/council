"""Tests for council.pipeline."""

from unittest.mock import patch, MagicMock

import pytest

from council.bridge import Bridge, AgentResponse
from council.config import AgentConfig, CouncilConfig
from council.pipeline import CouncilPipeline, CouncilResult


def _make_response(name="agent", success=True, response="Test response", elapsed=1.0):
    return AgentResponse(
        agent_name=name,
        display_name=name.title(),
        response=response if success else "",
        elapsed_seconds=elapsed,
        success=success,
        error=None if success else "Failed",
    )


class TestCouncilResult:
    def test_final_answer_from_synthesis(self):
        r = CouncilResult(question="test", run_id="1")
        r.stage3_synthesis = _make_response(response="Synthesized answer")
        assert r.final_answer == "Synthesized answer"

    def test_final_answer_fallback_to_stage1(self):
        r = CouncilResult(question="test", run_id="1")
        r.stage1_responses = [_make_response(response="Stage 1 answer")]
        assert r.final_answer == "Stage 1 answer"

    def test_final_answer_failed_synthesis_falls_back(self):
        r = CouncilResult(question="test", run_id="1")
        r.stage3_synthesis = _make_response(success=False)
        r.stage1_responses = [_make_response(response="Fallback")]
        assert r.final_answer == "Fallback"

    def test_final_answer_all_failed(self):
        r = CouncilResult(question="test", run_id="1")
        r.stage1_responses = [_make_response(success=False)]
        assert "failed" in r.final_answer.lower()

    def test_final_answer_empty(self):
        r = CouncilResult(question="test", run_id="1")
        assert "failed" in r.final_answer.lower()


class TestCouncilPipeline:
    def _make_config(self, agents=None, chairman="a"):
        if agents is None:
            agents = {
                "a": AgentConfig(name="a", enabled=True, display_name="Agent A", type="cli", command="echo"),
                "b": AgentConfig(name="b", enabled=True, display_name="Agent B", type="cli", command="echo"),
            }
        return CouncilConfig(agents=agents, chairman=chairman)

    def _make_bridge(self, responses):
        """Create a mock bridge that returns predefined responses."""
        bridge = MagicMock(spec=Bridge)
        call_count = [0]

        def side_effect(agent, prompt, run_id, on_chunk=None):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            return _make_response(name=agent.name, response=f"Response {idx}")

        bridge.query_agent.side_effect = side_effect
        bridge.query_agents_parallel.return_value = responses[:2] if len(responses) >= 2 else responses
        return bridge

    @patch("council.pipeline.console")
    @patch("council.pipeline.print_stage_header")
    @patch("council.pipeline.print_agent_result")
    @patch("council.pipeline.print_stage_summary")
    @patch("council.pipeline.print_final_result")
    @patch("council.pipeline.print_memory_status")
    @patch("council.pipeline.print_memory_saved")
    @patch("council.pipeline.print_stats")
    @patch("council.pipeline.StreamingDisplay")
    @patch("council.pipeline.init_memory")
    @patch("council.pipeline.load_memory", return_value="")
    @patch("council.pipeline.list_memories", return_value=[])
    def test_no_active_agents(self, *mocks):
        cfg = CouncilConfig(agents={})
        bridge = MagicMock(spec=Bridge)
        pipeline = CouncilPipeline(config=cfg, bridge=bridge)
        result = pipeline.run("test question")
        assert len(result.errors) > 0
        assert "No active agents" in result.errors[0]

    @patch("council.pipeline.console")
    @patch("council.pipeline.print_stage_header")
    @patch("council.pipeline.print_agent_result")
    @patch("council.pipeline.print_stage_summary")
    @patch("council.pipeline.print_final_result")
    @patch("council.pipeline.print_memory_status")
    @patch("council.pipeline.print_memory_saved")
    @patch("council.pipeline.print_stats")
    @patch("council.pipeline.StreamingDisplay")
    @patch("council.pipeline.init_memory")
    @patch("council.pipeline.load_memory", return_value="")
    @patch("council.pipeline.list_memories", return_value=[])
    def test_single_agent_skips_review(self, *mocks):
        cfg = self._make_config(agents={
            "solo": AgentConfig(name="solo", enabled=True, display_name="Solo", type="cli", command="echo"),
        })
        bridge = self._make_bridge([_make_response(name="solo", response="Solo answer")])
        pipeline = CouncilPipeline(config=cfg, bridge=bridge)
        result = pipeline.run("test", use_parallel=False)
        # Should skip stage 2 and 3, use stage 1 response as synthesis
        assert result.stage3_synthesis is not None
        assert result.stage3_synthesis.response == "Solo answer"
        assert len(result.stage2_reviews) == 0

    @patch("council.pipeline.console")
    @patch("council.pipeline.print_stage_header")
    @patch("council.pipeline.print_agent_result")
    @patch("council.pipeline.print_stage_summary")
    @patch("council.pipeline.print_final_result")
    @patch("council.pipeline.print_memory_status")
    @patch("council.pipeline.print_memory_saved")
    @patch("council.pipeline.print_stats")
    @patch("council.pipeline.StreamingDisplay")
    @patch("council.pipeline.init_memory")
    @patch("council.pipeline.load_memory", return_value="")
    @patch("council.pipeline.list_memories", return_value=[])
    def test_all_agents_fail(self, *mocks):
        cfg = self._make_config()
        bridge = self._make_bridge([
            _make_response(name="a", success=False),
            _make_response(name="b", success=False),
        ])
        pipeline = CouncilPipeline(config=cfg, bridge=bridge)
        result = pipeline.run("test", use_parallel=False)
        assert len(result.errors) > 0
        assert "All agents failed" in result.errors[0]

    @patch("council.pipeline.console")
    @patch("council.pipeline.print_stage_header")
    @patch("council.pipeline.print_agent_result")
    @patch("council.pipeline.print_stage_summary")
    @patch("council.pipeline.print_final_result", return_value="Final answer")
    @patch("council.pipeline.print_memory_status")
    @patch("council.pipeline.print_memory_saved")
    @patch("council.pipeline.print_stats")
    @patch("council.pipeline.StreamingDisplay")
    @patch("council.pipeline.init_memory")
    @patch("council.pipeline.load_memory", return_value="")
    @patch("council.pipeline.list_memories", return_value=[])
    def test_full_pipeline_sequential(self, *mocks):
        cfg = self._make_config()
        # Stage 1: 2 responses, Stage 2: 2 reviews, Stage 3: 1 synthesis, + 1 learning
        responses = [
            _make_response(name="a", response="Answer A"),
            _make_response(name="b", response="Answer B"),
            _make_response(name="a", response="Review by A"),
            _make_response(name="b", response="Review by B"),
            _make_response(name="a", response="## Council Answer\nSynthesized."),
            _make_response(name="a", response="Learning: X is Y"),  # Learning extraction
        ]
        bridge = self._make_bridge(responses)
        pipeline = CouncilPipeline(config=cfg, bridge=bridge)
        result = pipeline.run("test question", use_parallel=False)

        assert len(result.stage1_responses) == 2
        assert len(result.stage2_reviews) == 2
        assert result.stage3_synthesis is not None
        assert result.stage3_synthesis.success
