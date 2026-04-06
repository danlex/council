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

import re
from datetime import datetime
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = _PROJECT_ROOT / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
SUBDIRS = ["learnings", "corrections", "context", "preferences", "sessions"]


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


def load_memory(limit: int = 20, query: str = "") -> str:
    """Load memory entries for injection into prompts.

    If a query is provided, filters by keyword relevance — only memories
    whose filename or content share words with the query are included.
    Without a query, loads the N most recent entries.

    Args:
        limit: Maximum number of memory entries to load (default 20)
        query: Optional question/topic to filter by relevance
    """
    if not MEMORY_DIR.exists():
        return ""

    # Collect memories from each subdirectory (exclude sessions — too large)
    all_memories = []
    for sub in SUBDIRS:
        if sub == "sessions":
            continue
        subdir = MEMORY_DIR / sub
        if subdir.exists():
            for f in sorted(subdir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                all_memories.append((f.stat().st_mtime, sub, f))

    all_memories.sort(key=lambda x: x[0], reverse=True)

    if query:
        # Keyword relevance filtering
        query_words = _extract_keywords(query)
        scored = []
        for mtime, category, filepath in all_memories:
            content = filepath.read_text().strip()
            if not content:
                continue
            # Score = number of query keywords found in filename + content
            text = (filepath.stem + " " + content).lower()
            score = sum(1 for w in query_words if w in text)
            if score > 0:
                scored.append((score, mtime, category, filepath, content))

        # Sort by relevance (score desc), then recency (mtime desc)
        scored.sort(key=lambda x: (-x[0], -x[1]))
        parts = []
        for score, _, category, filepath, content in scored[:limit]:
            parts.append(f"### [{category}] {filepath.stem}\n{content}")
    else:
        # No query — load most recent
        parts = []
        for _, category, filepath in all_memories[:limit]:
            content = filepath.read_text().strip()
            if content:
                parts.append(f"### [{category}] {filepath.stem}\n{content}")

    if not parts:
        return ""

    return "\n\n---\n\n".join(parts)


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text for relevance matching."""
    # Common stop words to skip
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "and", "but", "or",
        "nor", "not", "no", "so", "if", "then", "than", "that", "this",
        "these", "those", "it", "its", "what", "which", "who", "whom",
        "how", "when", "where", "why", "all", "each", "every", "both",
        "few", "more", "most", "other", "some", "such", "only", "own",
        "same", "very", "just", "about", "also", "we", "you", "they",
        "i", "me", "my", "your", "our", "us", "him", "her", "them",
    }
    words = set(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())
    return {w for w in words if w not in stop and len(w) > 2}


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


MAX_INDEX_ENTRIES = 100


def _update_index(filepath: Path, category: str, title: str):
    """Add an entry to MEMORY.md index, capped at MAX_INDEX_ENTRIES lines."""
    rel_path = filepath.relative_to(MEMORY_DIR)
    entry = f"- [{title}]({rel_path}) — {category}, {datetime.now().strftime('%Y-%m-%d')}\n"

    header = (
        "# Council Shared Memory\n\n"
        "This file indexes all memories accumulated by the Council across sessions.\n\n"
        "---\n\n"
    )

    if MEMORY_INDEX.exists():
        current = MEMORY_INDEX.read_text()
        # Extract existing entries (lines starting with "- [")
        existing_entries = [
            line for line in current.split("\n") if line.strip().startswith("- [")
        ]
    else:
        existing_entries = []

    # Add new entry and cap to most recent MAX_INDEX_ENTRIES
    all_entries = existing_entries + [entry.rstrip()]
    if len(all_entries) > MAX_INDEX_ENTRIES:
        all_entries = all_entries[-MAX_INDEX_ENTRIES:]

    MEMORY_INDEX.write_text(header + "\n".join(all_entries) + "\n")


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
