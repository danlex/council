"""MCP server — exposes the council as a tool for Claude Code and Cursor.

Usage:
  Add to ~/.claude/settings.json or .mcp.json:
  {
    "mcpServers": {
      "council": {
        "command": "/path/to/council/.venv/bin/python3",
        "args": ["-m", "council.mcp_server"]
      }
    }
  }

Protocol: JSON-RPC over stdio (MCP standard)
"""

from __future__ import annotations

import json
import sys

from council.config import load_config
from council.bridge import Bridge
from council.memory import init_memory, load_memory, list_memories, save_learning, EXTRACT_LEARNINGS_PROMPT
from council.prompts import build_stage1_prompt, build_stage2_prompt, build_stage3_prompt


def main():
    """MCP server main loop — reads JSON-RPC from stdin, writes to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            _respond(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "council", "version": "0.2.0"},
            })

        elif method == "tools/list":
            _respond(req_id, {
                "tools": [
                    {
                        "name": "council_ask",
                        "description": (
                            "Ask the Council of LLMs a question. Queries multiple AI models "
                            "(Claude, GPT, Gemini) and synthesizes their answers through "
                            "anonymized peer review. Use this for complex questions where "
                            "you want multiple perspectives and reduced confirmation bias."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "question": {
                                    "type": "string",
                                    "description": "The question to ask the council",
                                },
                            },
                            "required": ["question"],
                        },
                    },
                    {
                        "name": "council_memory",
                        "description": "List the council's accumulated memories and learnings from past sessions.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                ]
            })

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})

            if tool_name == "council_ask":
                result = _run_council(tool_args.get("question", ""))
                _respond(req_id, {
                    "content": [{"type": "text", "text": result}],
                })

            elif tool_name == "council_memory":
                memories = _get_memory()
                _respond(req_id, {
                    "content": [{"type": "text", "text": memories}],
                })

            else:
                _respond(req_id, {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                })

        elif method == "notifications/initialized":
            pass  # Acknowledgement, no response needed

        else:
            if req_id is not None:
                _respond(req_id, None, error={"code": -32601, "message": f"Unknown method: {method}"})


def _respond(req_id, result=None, error=None):
    """Send a JSON-RPC response."""
    response = {"jsonrpc": "2.0", "id": req_id}
    if error:
        response["error"] = error
    else:
        response["result"] = result
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _run_council(question: str) -> str:
    """Run a council deliberation and return the synthesis as text."""
    if not question:
        return "No question provided."

    config = load_config()
    bridge = Bridge(config=config)
    active = config.active_agents

    if not active:
        return "No active agents configured."

    init_memory()
    memory = load_memory(query=question)
    soul = config.soul

    # Stage 1: Parallel responses
    import concurrent.futures
    stage1_prompts = {
        a.name: build_stage1_prompt(brief=question, soul=soul, memory=memory, agent_type=a.type)
        for a in active
    }

    responses = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(active)) as pool:
        futures = {pool.submit(bridge.query_agent, a, stage1_prompts[a.name], "mcp"): a for a in active}
        for f in concurrent.futures.as_completed(futures):
            responses.append(f.result())

    successful = [r for r in responses if r.success]
    if len(successful) < 2:
        if successful:
            return f"## Council Answer (single agent: {successful[0].display_name})\n\n{successful[0].response}"
        return "All agents failed in Stage 1."

    # Stage 2: Peer reviews (parallel)
    response_dicts = [
        {"agent_id": r.agent_name, "agent_name": r.display_name, "response": r.response}
        for r in successful
    ]
    review_agents = [a for a in active if any(r.agent_name == a.name for r in successful)]

    review_tasks = []
    for agent in review_agents:
        others = [r for r in response_dicts if r["agent_id"] != agent.name]
        if others:
            prompt = build_stage2_prompt(brief=question, responses=others, rubric=config.rubric, soul=soul, memory=memory)
            review_tasks.append((agent, prompt))

    reviews = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(review_tasks)) as pool:
        futures = {pool.submit(bridge.query_agent, a, p, "mcp-rev"): a for a, p in review_tasks}
        for f in concurrent.futures.as_completed(futures):
            reviews.append(f.result())

    successful_reviews = [r for r in reviews if r.success]
    review_dicts = [
        {"agent_id": f"reviewer_{i}", "agent_name": f"Reviewer {i+1}", "response": r.response}
        for i, r in enumerate(successful_reviews)
    ]

    # Stage 3: Chairman synthesis
    chairman = config.chairman_agent
    stage3_prompt = build_stage3_prompt(
        brief=question, responses=response_dicts, reviews=review_dicts,
        preserve_dissent=config.preserve_dissent, soul=soul, memory=memory,
    )
    synthesis = bridge.query_agent(chairman, stage3_prompt, "mcp-synth")

    if synthesis.success:
        # Save learning
        learning_prompt = EXTRACT_LEARNINGS_PROMPT.format(
            question=question, synthesis=synthesis.response[:2000],
            disagreements="See synthesis above",
        )
        lr = bridge.query_agent(chairman, learning_prompt, "mcp-learn")
        if lr.success:
            save_learning(lr.response, question, "mcp")

        return synthesis.response
    else:
        return f"Synthesis failed: {synthesis.error}\n\nBest individual response:\n{successful[0].response}"


def _get_memory() -> str:
    init_memory()
    memories = list_memories()
    if not memories:
        return "No memories yet."

    lines = [f"Council Memory ({len(memories)} entries):\n"]
    for m in memories[:20]:
        lines.append(f"- [{m['category']}] {m['name']} ({m['modified'][:10]})")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
