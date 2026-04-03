"""Shared long-term memory system for the Council.

File-based memory that persists across sessions and is accessible
by all agents. Inspired by Claude Code's memory system.

Structure:
    memory/
    ├── MEMORY.md           # Index of all memories
    ├── learnings/          # What the council has learned from sessions
    ├── corrections/        # User corrections and feedback
    ├── context/            # Domain knowledge accumulated
    └── preferences/        # User preferences and patterns
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path


MEMORY_DIR = Path("memory")
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
SUBDIRS = ["learnings", "corrections", "context", "preferences"]


def init_memory():
    """Initialize the memory directory structure."""
    MEMORY_DIR.mkdir(exist_ok=True)
    for sub in SUBDIRS:
        (MEMORY_DIR / sub).mkdir(exist_ok=True)

    if not MEMORY_INDEX.exists():
        MEMORY_INDEX.write_text(
            "# Council Shared Memory\n\n"
            "This file indexes all memories accumulated by the Council across sessions.\n\n"
            "---\n\n"
        )


def load_memory() -> str:
    """Load all memory content for injection into prompts.

    Returns a formatted string with the memory index and recent entries.
    """
    if not MEMORY_INDEX.exists():
        return ""

    parts = []

    # Load index
    index = MEMORY_INDEX.read_text().strip()
    if index:
        parts.append(index)

    # Load recent memories from each subdirectory (last 20 total)
    all_memories = []
    for sub in SUBDIRS:
        subdir = MEMORY_DIR / sub
        if subdir.exists():
            for f in sorted(subdir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                all_memories.append((f.stat().st_mtime, sub, f))

    # Sort by recency, take last 20
    all_memories.sort(key=lambda x: x[0], reverse=True)
    for _, category, filepath in all_memories[:20]:
        content = filepath.read_text().strip()
        if content:
            parts.append(f"### [{category}] {filepath.stem}\n{content}")

    if not parts:
        return ""

    return "\n\n---\n\n".join(parts)


def save_memory(
    content: str,
    category: str = "learnings",
    title: str | None = None,
) -> Path:
    """Save a new memory entry.

    Args:
        content: The memory content
        category: One of learnings, corrections, context, preferences
        title: Optional title (auto-generated if not provided)
    """
    init_memory()

    if category not in SUBDIRS:
        category = "learnings"

    subdir = MEMORY_DIR / category
    subdir.mkdir(exist_ok=True)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if title:
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower().strip())[:50]
        filename = f"{timestamp}_{slug}.md"
    else:
        filename = f"{timestamp}.md"

    filepath = subdir / filename
    filepath.write_text(content.strip() + "\n")

    # Update index
    _update_index(filepath, category, title or filepath.stem)

    return filepath


def save_correction(user_feedback: str, question: str) -> Path:
    """Save a user correction/feedback."""
    content = (
        f"**Question:** {question}\n\n"
        f"**User Feedback:** {user_feedback}\n\n"
        f"**Date:** {datetime.now().isoformat()}\n"
    )
    return save_memory(content, category="corrections", title=f"correction_{question[:30]}")


def save_learning(learning: str, question: str, session_id: str) -> Path:
    """Save a learning extracted from a council session."""
    content = (
        f"**Session:** {session_id}\n"
        f"**Question:** {question}\n"
        f"**Date:** {datetime.now().isoformat()}\n\n"
        f"{learning}\n"
    )
    return save_memory(content, category="learnings", title=question[:40])


def _update_index(filepath: Path, category: str, title: str):
    """Add an entry to MEMORY.md index."""
    rel_path = filepath.relative_to(MEMORY_DIR)
    entry = f"- [{title}]({rel_path}) — {category}, {datetime.now().strftime('%Y-%m-%d')}\n"

    if MEMORY_INDEX.exists():
        current = MEMORY_INDEX.read_text()
    else:
        current = "# Council Shared Memory\n\n---\n\n"

    # Append entry
    MEMORY_INDEX.write_text(current + entry)


def list_memories() -> list[dict]:
    """List all memory entries."""
    entries = []
    for sub in SUBDIRS:
        subdir = MEMORY_DIR / sub
        if subdir.exists():
            for f in sorted(subdir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                entries.append({
                    "path": str(f),
                    "category": sub,
                    "name": f.stem,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    "size": f.stat().st_size,
                })
    return entries


def clear_memory():
    """Clear all memories (dangerous!)."""
    import shutil
    if MEMORY_DIR.exists():
        shutil.rmtree(MEMORY_DIR)
    init_memory()


EXTRACT_LEARNINGS_PROMPT = """You just completed a council deliberation. Review the question, all responses, reviews, and the final synthesis below.

Extract the KEY LEARNINGS that would be valuable for future council sessions. Focus on:
1. Factual knowledge that was established or corrected
2. Reasoning patterns that proved effective
3. Blind spots or biases that were identified
4. Disagreements that remained unresolved (these are especially important)
5. Domain-specific insights

Format as a concise list of learnings. Each learning should be self-contained and useful without context.
Do NOT include meta-commentary about the council process itself.
Keep it under 500 words.

---

Question: {question}

Final Synthesis:
{synthesis}

Key Disagreements (if any):
{disagreements}
"""
