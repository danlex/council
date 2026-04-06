"""Tests for council.memory."""

import pytest

import council.memory as mem


# conftest.py's isolate_memory_dir fixture handles isolation automatically.
# This alias preserves the old fixture name for existing test functions.
@pytest.fixture
def isolated_memory(isolate_memory_dir):
    """Alias for the autouse conftest fixture."""
    return isolate_memory_dir


class TestInitMemory:
    def test_creates_structure(self, isolated_memory):
        mem.init_memory()
        assert isolated_memory.exists()
        assert (isolated_memory / "MEMORY.md").exists()
        for sub in mem.SUBDIRS:
            assert (isolated_memory / sub).exists()

    def test_idempotent(self, isolated_memory):
        mem.init_memory()
        mem.init_memory()  # Should not crash
        assert (isolated_memory / "MEMORY.md").exists()

    def test_preserves_existing_index(self, isolated_memory):
        mem.init_memory()
        (isolated_memory / "MEMORY.md").write_text("Custom content\n")
        mem.init_memory()
        assert "Custom content" in (isolated_memory / "MEMORY.md").read_text()


class TestSaveMemory:
    def test_saves_to_correct_category(self, isolated_memory):
        path = mem.save_memory("test content", category="learnings", title="test")
        assert "learnings" in str(path)
        assert path.exists()
        assert "test content" in path.read_text()

    def test_invalid_category_defaults_to_learnings(self, isolated_memory):
        path = mem.save_memory("test", category="invalid_category")
        assert "learnings" in str(path)

    def test_auto_generates_filename(self, isolated_memory):
        path = mem.save_memory("test content")
        assert path.stem.startswith("20")  # Timestamp

    def test_title_in_filename(self, isolated_memory):
        path = mem.save_memory("test", title="My Great Learning")
        assert "my_great_learning" in path.stem

    def test_updates_index(self, isolated_memory):
        mem.save_memory("test", category="learnings", title="indexed entry")
        index = (isolated_memory / "MEMORY.md").read_text()
        assert "indexed entry" in index

    def test_long_title_truncated(self, isolated_memory):
        long_title = "x" * 200
        path = mem.save_memory("test", title=long_title)
        assert len(path.stem) < 100  # Should be truncated


class TestSaveLearning:
    def test_saves_with_metadata(self, isolated_memory):
        path = mem.save_learning(
            learning="Rust is faster than Go",
            question="Which is better?",
            session_id="abc123",
        )
        content = path.read_text()
        assert "abc123" in content
        assert "Which is better?" in content
        assert "Rust is faster than Go" in content


class TestSaveCorrection:
    def test_saves_feedback(self, isolated_memory):
        path = mem.save_correction(
            user_feedback="Actually Go is faster for web services",
            question="Rust vs Go",
        )
        content = path.read_text()
        assert "Actually Go is faster" in content
        assert "corrections" in str(path)


class TestLoadMemory:
    def test_empty_memory(self, isolated_memory):
        result = mem.load_memory()
        assert result == ""

    def test_loads_after_save(self, isolated_memory):
        mem.save_memory("fact: water is wet", category="learnings", title="water")
        result = mem.load_memory()
        assert "water is wet" in result

    def test_loads_multiple_entries(self, isolated_memory):
        mem.save_memory("entry one", category="learnings", title="one")
        mem.save_memory("entry two", category="corrections", title="two")
        result = mem.load_memory()
        assert "entry one" in result
        assert "entry two" in result

    def test_limits_to_20_entries(self, isolated_memory):
        for i in range(30):
            mem.save_memory(f"entry {i}", category="learnings", title=f"entry_{i}")
        result = mem.load_memory()
        # Should contain index + at most 20 memory entries
        sections = result.split("---")
        # Index + up to 20 entries, each separated by ---
        assert len(sections) <= 22


class TestListMemories:
    def test_empty(self, isolated_memory):
        mem.init_memory()
        assert mem.list_memories() == []

    def test_lists_saved(self, isolated_memory):
        mem.save_memory("test", category="learnings", title="first")
        mem.save_memory("test2", category="corrections", title="second")
        entries = mem.list_memories()
        assert len(entries) == 2
        categories = {e["category"] for e in entries}
        assert categories == {"learnings", "corrections"}

    def test_entry_structure(self, isolated_memory):
        mem.save_memory("test", category="learnings", title="structured")
        entries = mem.list_memories()
        entry = entries[0]
        assert "path" in entry
        assert "category" in entry
        assert "name" in entry
        assert "modified" in entry
        assert "size" in entry


class TestClearMemory:
    def test_clears_everything(self, isolated_memory):
        mem.save_memory("test", category="learnings", title="doomed")
        assert len(mem.list_memories()) == 1
        mem.clear_memory()
        assert len(mem.list_memories()) == 0
        # But structure should be re-initialized
        assert isolated_memory.exists()
        assert (isolated_memory / "MEMORY.md").exists()
