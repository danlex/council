"""Tests for council.display."""

from council.bridge import AgentResponse
from council.config import AgentConfig
from council.display import (
    get_agent_color,
    AGENT_COLORS,
    STAGE_COLORS,
    STAGE_NAMES,
    StreamingDisplay,
)


class TestAgentColors:
    def test_known_agents(self):
        assert get_agent_color("claude") == "magenta"
        assert get_agent_color("gpt") == "bright_green"
        assert get_agent_color("gemini") == "blue"
        assert get_agent_color("deepseek") == "bright_cyan"

    def test_unknown_agent_default(self):
        assert get_agent_color("unknown_agent") == "white"

    def test_all_stage_colors_defined(self):
        for stage in (1, 2, 3):
            assert stage in STAGE_COLORS
            assert stage in STAGE_NAMES


class TestStreamingDisplay:
    def _agent(self, name="test"):
        return AgentConfig(name=name, enabled=True, display_name=name.title())

    def test_init(self):
        sd = StreamingDisplay()
        assert sd.agent_buffers == {}
        assert sd.live is None

    def test_update_chunk(self):
        sd = StreamingDisplay()
        sd.agent_buffers["test"] = ""
        sd.agent_status["test"] = "streaming"
        sd.agent_colors["test"] = "white"
        sd.agent_display_names["test"] = "Test"
        sd.agent_times["test"] = 0
        sd.update_chunk("test", "Hello ")
        sd.update_chunk("test", "World")
        assert sd.agent_buffers["test"] == "Hello World"

    def test_update_chunk_unknown_agent(self):
        sd = StreamingDisplay()
        sd.update_chunk("nonexistent", "data")  # Should not crash
        assert "nonexistent" not in sd.agent_buffers

    def test_mark_done(self):
        sd = StreamingDisplay()
        sd.agent_buffers["test"] = "content"
        sd.agent_status["test"] = "streaming"
        sd.agent_times["test"] = 0
        sd.agent_colors["test"] = "white"
        sd.agent_display_names["test"] = "Test"
        sd.mark_done("test", 5.2, success=True)
        assert sd.agent_status["test"] == "done"
        assert sd.agent_times["test"] == 5.2

    def test_mark_done_failure(self):
        sd = StreamingDisplay()
        sd.agent_buffers["test"] = ""
        sd.agent_status["test"] = "streaming"
        sd.agent_times["test"] = 0
        sd.agent_colors["test"] = "white"
        sd.agent_display_names["test"] = "Test"
        sd.mark_done("test", 1.0, success=False)
        assert sd.agent_status["test"] == "failed"

    def test_render_truncates_long_content(self):
        sd = StreamingDisplay()
        sd.agent_buffers["test"] = "\n".join(f"line {i}" for i in range(50))
        sd.agent_status["test"] = "streaming"
        sd.agent_times["test"] = 0
        sd.agent_colors["test"] = "white"
        sd.agent_display_names["test"] = "Test"
        rendered = sd._render()
        # Should not crash and should produce output
        assert rendered is not None

    def test_stop_without_start(self):
        sd = StreamingDisplay()
        sd.stop()  # Should not crash
        assert sd.live is None

    def test_concurrent_updates_no_crash(self):
        """Verify thread safety — concurrent chunk updates don't crash."""
        import threading
        sd = StreamingDisplay()
        sd.agent_buffers = {"a": "", "b": ""}
        sd.agent_status = {"a": "streaming", "b": "streaming"}
        sd.agent_times = {"a": 0, "b": 0}
        sd.agent_colors = {"a": "white", "b": "white"}
        sd.agent_display_names = {"a": "A", "b": "B"}
        # Don't start Live (would need terminal), just test buffer safety
        errors = []
        def writer(name, count):
            try:
                for i in range(count):
                    sd.update_chunk(name, f"chunk{i} ")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer, args=("a", 100))
        t2 = threading.Thread(target=writer, args=("b", 100))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(errors) == 0
        assert sd.agent_buffers["a"].count("chunk") == 100
        assert sd.agent_buffers["b"].count("chunk") == 100
