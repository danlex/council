"""Publish council sessions as Jekyll pages for GitHub Pages."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from council.memory import MEMORY_DIR

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
SESSIONS_DIR = DOCS_DIR / "_sessions"


def publish_all():
    """Convert all session JSON files to Jekyll markdown pages."""
    src = MEMORY_DIR / "sessions"
    if not src.exists():
        print("No sessions found.")
        return

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for json_file in sorted(src.glob("*.json")):
        try:
            session = json.loads(json_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        md = _session_to_markdown(session)
        if md:
            slug = _slugify(session.get("question", "untitled"))
            ts = session.get("timestamp", "")[:10]
            filename = f"{ts}-{slug}.md"
            out_path = SESSIONS_DIR / filename
            out_path.write_text(md)
            count += 1
            print(f"  Published: {filename}")

    print(f"\n  {count} sessions published to docs/_sessions/")
    if count:
        print("  Commit and push to update the site.")


def publish_latest():
    """Publish only the most recent session."""
    src = MEMORY_DIR / "sessions"
    if not src.exists():
        print("No sessions found.")
        return

    files = sorted(src.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("No sessions found.")
        return

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    session = json.loads(files[0].read_text())
    md = _session_to_markdown(session)
    if md:
        slug = _slugify(session.get("question", "untitled"))
        ts = session.get("timestamp", "")[:10]
        filename = f"{ts}-{slug}.md"
        out_path = SESSIONS_DIR / filename
        out_path.write_text(md)
        print(f"  Published: {filename}")
        print("  Commit and push to update the site.")


def _session_to_markdown(session: dict) -> str | None:
    """Convert a session JSON dict to a Jekyll markdown page."""
    question = session.get("question", "")
    if not question:
        return None

    timestamp = session.get("timestamp", "")
    stage1 = session.get("stage1", [])
    stage2 = session.get("stage2", [])
    stage3 = session.get("stage3")
    final = session.get("final_answer", "")

    # Compute metadata
    agents = list({r["display_name"] for r in stage1 if r.get("success")})
    total_time = (
        sum(r.get("elapsed_seconds", 0) for r in stage1)
        + sum(r.get("elapsed_seconds", 0) for r in stage2)
        + (stage3.get("elapsed_seconds", 0) if stage3 else 0)
    )
    total_cost = (
        sum(r.get("cost_usd", 0) for r in stage1)
        + sum(r.get("cost_usd", 0) for r in stage2)
        + (stage3.get("cost_usd", 0) if stage3 else 0)
    )

    # Title: first 80 chars of question
    title = question[:80].replace('"', "'")
    if len(question) > 80:
        title += "..."

    # Build frontmatter
    date_str = timestamp[:10] if timestamp else datetime.now().strftime("%Y-%m-%d")
    lines = [
        "---",
        "layout: session",
        f'title: "{title}"',
        f"date: {date_str}",
        f"agents: [{', '.join(repr(a) for a in agents)}]",
        f'duration: "{total_time:.0f}s"',
        f'cost: "${total_cost:.4f}"' if total_cost > 0 else 'cost: "N/A"',
        f'run_id: "{session.get("run_id", "")}"',
        "---",
        "",
        f"> **{question}**",
        "",
    ]

    # Stage 1: Individual Responses
    successful_s1 = [r for r in stage1 if r.get("success")]
    if successful_s1:
        lines.append("## Stage 1: Independent Responses")
        lines.append("")
        for i, r in enumerate(successful_s1):
            agent = r.get("display_name", f"Agent {i+1}")
            time_s = r.get("elapsed_seconds", 0)
            lines.append(f'<div class="stage">')
            lines.append(f'<div class="stage-header">Agent {i+1} ({agent}) &middot; {time_s:.1f}s</div>')
            lines.append("")
            lines.append(r.get("response", "*(no response)*"))
            lines.append("")
            lines.append("</div>")
            lines.append("")

    # Stage 2: Peer Reviews
    successful_s2 = [r for r in stage2 if r.get("success")]
    if successful_s2:
        lines.append("## Stage 2: Anonymized Peer Review")
        lines.append("")
        for i, r in enumerate(successful_s2):
            time_s = r.get("elapsed_seconds", 0)
            lines.append(f'<div class="stage">')
            lines.append(f'<div class="stage-header">Reviewer {i+1} &middot; {time_s:.1f}s</div>')
            lines.append("")
            lines.append(r.get("response", "*(no review)*"))
            lines.append("")
            lines.append("</div>")
            lines.append("")

    # Stage 3: Synthesis
    if stage3 and stage3.get("success"):
        chairman = stage3.get("display_name", "Chairman")
        time_s = stage3.get("elapsed_seconds", 0)
        lines.append("## Stage 3: Council Synthesis")
        lines.append("")
        lines.append(f'<div class="synthesis">')
        lines.append(f'<div class="stage-header">Chairman: {chairman} &middot; {time_s:.1f}s</div>')
        lines.append("")
        lines.append(stage3.get("response", "*(no synthesis)*"))
        lines.append("")
        lines.append("</div>")
        lines.append("")

    # Stats
    lines.append("## Session Stats")
    lines.append("")
    lines.append('<div class="stats">')
    lines.append(f'<span class="stat">Agents: <strong>{len(agents)}</strong></span>')
    lines.append(f'<span class="stat">Total time: <strong>{total_time:.0f}s</strong></span>')
    if total_cost > 0:
        lines.append(f'<span class="stat">Cost: <strong>${total_cost:.4f}</strong></span>')
    lines.append("</div>")

    return "\n".join(lines) + "\n"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())[:60]
    return slug.strip("-")


if __name__ == "__main__":
    import sys
    if "--latest" in sys.argv:
        publish_latest()
    else:
        publish_all()
