"""Shared pytest fixtures — isolates tests from real project memory."""

import pytest


@pytest.fixture(autouse=True)
def isolate_memory_dir(tmp_path, monkeypatch):
    """Redirect MEMORY_DIR to a temp directory for ALL tests.

    Without this fixture, tests that exercise the pipeline or memory
    module write to the real project memory/ directory, polluting
    user data with test entries.
    """
    import council.memory as mem_mod

    test_memory = tmp_path / "memory"
    monkeypatch.setattr(mem_mod, "MEMORY_DIR", test_memory)
    monkeypatch.setattr(mem_mod, "MEMORY_INDEX", test_memory / "MEMORY.md")

    # Also patch the re-import in pipeline
    import council.pipeline as pipe_mod
    monkeypatch.setattr(pipe_mod, "MEMORY_DIR", test_memory)

    yield test_memory
