"""Tests for council.prompts."""

from council.prompts import (
    format_rubric_items,
    format_anonymized_responses,
    format_rating_template,
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    _section,
)


class TestFormatHelpers:
    def test_rubric_items(self):
        result = format_rubric_items(["accuracy", "reasoning"])
        assert "**Accuracy**" in result
        assert "**Reasoning**" in result
        assert "[1-10]" in result

    def test_rubric_items_empty(self):
        assert format_rubric_items([]) == ""

    def test_anonymized_responses(self):
        responses = [
            {"response": "Answer A"},
            {"response": "Answer B"},
        ]
        result = format_anonymized_responses(responses)
        assert "Agent 1" in result
        assert "Agent 2" in result
        assert "Answer A" in result
        assert "Answer B" in result

    def test_anonymized_responses_single(self):
        responses = [{"response": "Only one"}]
        result = format_anonymized_responses(responses)
        assert "Agent 1" in result
        assert "---" not in result  # No separator for single response

    def test_rating_template(self):
        result = format_rating_template(2, ["accuracy", "nuance"])
        assert "Agent 1" in result
        assert "Agent 2" in result
        assert "Accuracy" in result
        assert "Nuance" in result
        assert "?/10" in result

    def test_section_with_content(self):
        result = _section("Title", "Content here")
        assert "## Title" in result
        assert "Content here" in result

    def test_section_empty(self):
        assert _section("Title", "") == ""


class TestBuildStage1:
    def test_includes_brief(self):
        result = build_stage1_prompt("What is Python?")
        assert "What is Python?" in result

    def test_includes_soul(self):
        result = build_stage1_prompt("test", soul="Be honest")
        assert "Be honest" in result
        assert "Council Soul" in result

    def test_includes_memory(self):
        result = build_stage1_prompt("test", memory="Previous: Rust is fast")
        assert "Rust is fast" in result
        assert "Shared Memory" in result

    def test_no_soul_no_memory(self):
        result = build_stage1_prompt("test")
        assert "Council Soul" not in result
        assert "Shared Memory" not in result

    def test_instructions_present(self):
        result = build_stage1_prompt("test")
        assert "USE TOOLS" in result
        assert "confidence levels" in result


class TestBuildStage2:
    def _responses(self):
        return [
            {"response": "Go is better"},
            {"response": "Rust is better"},
        ]

    def test_includes_brief(self):
        result = build_stage2_prompt("Rust vs Go", self._responses(), ["accuracy"])
        assert "Rust vs Go" in result

    def test_anonymizes_responses(self):
        result = build_stage2_prompt("test", self._responses(), ["accuracy"])
        assert "Agent 1" in result
        assert "Agent 2" in result
        assert "Go is better" in result
        assert "Rust is better" in result

    def test_includes_rubric(self):
        result = build_stage2_prompt("test", self._responses(), ["accuracy", "nuance"])
        assert "Accuracy" in result
        assert "Nuance" in result

    def test_includes_rating_template(self):
        result = build_stage2_prompt("test", self._responses(), ["accuracy"])
        assert "?/10" in result


class TestBuildStage3:
    def _responses(self):
        return [{"response": "Answer A"}, {"response": "Answer B"}]

    def _reviews(self):
        return [{"response": "Review 1"}, {"response": "Review 2"}]

    def test_includes_all_sections(self):
        result = build_stage3_prompt("brief", self._responses(), self._reviews())
        assert "brief" in result
        assert "Answer A" in result
        assert "Answer B" in result
        assert "Review 1" in result
        assert "Review 2" in result

    def test_synthesis_instructions(self):
        result = build_stage3_prompt("test", self._responses(), self._reviews())
        assert "DO NOT average" in result
        assert "PRESERVE DISSENT" in result
        assert "QUALITY OF REASONING" in result

    def test_output_format(self):
        result = build_stage3_prompt("test", self._responses(), self._reviews())
        assert "Council Answer" in result
        assert "Confidence Assessment" in result
        assert "Points of Dissent" in result
        assert "Blind Spots" in result

    def test_reviewer_labels(self):
        result = build_stage3_prompt("test", self._responses(), self._reviews())
        assert "Reviewer 1" in result
        assert "Reviewer 2" in result
