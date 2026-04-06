"""Web UI for watching the council deliberate in a browser."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path

from council.config import load_config
from council.bridge import Bridge
from council.memory import init_memory, load_memory, list_memories, save_learning, EXTRACT_LEARNINGS_PROMPT
from council.prompts import build_stage1_prompt, build_stage2_prompt, build_stage3_prompt

# Use stdlib http.server — no extra dependencies
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

_events: dict[str, queue.Queue] = {}
_HTML = Path(__file__).parent / "web_ui.html"


class CouncilHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "":
            self._serve_html()
        elif parsed.path == "/stream":
            self._handle_stream(parsed)
        elif parsed.path == "/models":
            self._handle_models()
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/ask":
            self._handle_ask()
        else:
            self.send_error(404)

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_HTML.read_bytes())

    def _handle_models(self):
        config = load_config()
        agents = [
            {"name": a.name, "display_name": a.display_name, "type": a.type, "enabled": a.enabled}
            for a in config.agents.values()
        ]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(agents).encode())

    def _handle_ask(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        question = body.get("question", "")

        if not question:
            self.send_error(400, "No question provided")
            return

        run_id = uuid.uuid4().hex[:8]
        _events[run_id] = queue.Queue()

        # Start council in background thread
        t = threading.Thread(target=_run_council, args=(run_id, question), daemon=True)
        t.start()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"run_id": run_id}).encode())

    def _handle_stream(self, parsed):
        params = parse_qs(parsed.query)
        run_id = params.get("run_id", [""])[0]

        if run_id not in _events:
            self.send_error(404, "Unknown run_id")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = _events[run_id]
        while True:
            try:
                event = q.get(timeout=120)
                if event is None:  # Sentinel — stream done
                    self.wfile.write(b"data: {\"type\":\"done\"}\n\n")
                    self.wfile.flush()
                    break
                data = json.dumps(event)
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
            except queue.Empty:
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                break

        _events.pop(run_id, None)

    def log_message(self, format, *args):
        pass  # Suppress request logging


def _run_council(run_id: str, question: str):
    """Run a full council deliberation, pushing events to the SSE queue."""
    q = _events.get(run_id)
    if not q:
        return

    config = load_config()
    bridge = Bridge(config=config)
    active = config.active_agents

    def emit(event_type: str, **data):
        q.put({"type": event_type, **data})

    init_memory()
    memory = load_memory(query=question)
    soul = config.soul

    try:
        # Stage 1
        emit("stage", stage=1, name="Independent Responses", agents=[a.display_name for a in active])

        import concurrent.futures
        stage1_prompts = {
            a.name: build_stage1_prompt(brief=question, soul=soul, memory=memory, agent_type=a.type)
            for a in active
        }

        responses = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(active)) as pool:
            def run_s1(agent):
                def on_chunk(chunk):
                    emit("chunk", agent=agent.display_name, text=chunk)
                return bridge.query_agent(agent, stage1_prompts[agent.name], run_id, on_chunk=on_chunk)
            futures = {pool.submit(run_s1, a): a for a in active}
            for future in concurrent.futures.as_completed(futures):
                resp = future.result()
                responses.append(resp)
                emit("agent_done", agent=resp.display_name, success=resp.success,
                     elapsed=resp.elapsed_seconds, chars=len(resp.response))

        successful = [r for r in responses if r.success]
        emit("stage_done", stage=1, success=len(successful), total=len(responses))

        if len(successful) < 2:
            if successful:
                emit("synthesis", text=successful[0].response, chairman="(single agent)")
            else:
                emit("error", message="All agents failed")
            q.put(None)
            return

        # Stage 2
        response_dicts = [
            {"agent_id": r.agent_name, "agent_name": r.display_name, "response": r.response}
            for r in successful
        ]
        review_agents = [a for a in active if any(r.agent_name == a.name for r in successful)]
        emit("stage", stage=2, name="Anonymized Peer Review", agents=[a.display_name for a in review_agents])

        review_tasks = []
        for agent in review_agents:
            others = [r for r in response_dicts if r["agent_id"] != agent.name]
            if others:
                prompt = build_stage2_prompt(brief=question, responses=others, rubric=config.rubric, soul=soul, memory=memory)
                review_tasks.append((agent, prompt))

        reviews = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(review_tasks)) as pool:
            def run_rev(agent, prompt):
                def on_chunk(chunk):
                    emit("chunk", agent=f"Reviewer", text=chunk)
                return bridge.query_agent(agent, prompt, run_id, on_chunk=on_chunk)
            futures = {pool.submit(run_rev, a, p): a for a, p in review_tasks}
            for future in concurrent.futures.as_completed(futures):
                rev = future.result()
                reviews.append(rev)
                emit("agent_done", agent="Reviewer", success=rev.success, elapsed=rev.elapsed_seconds, chars=len(rev.response))

        successful_reviews = [r for r in reviews if r.success]
        emit("stage_done", stage=2, success=len(successful_reviews), total=len(reviews))

        # Stage 3
        chairman = config.chairman_agent
        emit("stage", stage=3, name="Chairman Synthesis", agents=[chairman.display_name])

        review_dicts = [
            {"agent_id": f"reviewer_{i}", "agent_name": f"Reviewer {i+1}", "response": r.response}
            for i, r in enumerate(successful_reviews)
        ]
        stage3_prompt = build_stage3_prompt(
            brief=question, responses=response_dicts, reviews=review_dicts,
            preserve_dissent=config.preserve_dissent, soul=soul, memory=memory,
        )

        def on_synth_chunk(chunk):
            emit("chunk", agent=chairman.display_name, text=chunk)
        synthesis = bridge.query_agent(chairman, stage3_prompt, run_id, on_chunk=on_synth_chunk)

        emit("synthesis", text=synthesis.response if synthesis.success else "Synthesis failed",
             chairman=chairman.display_name, elapsed=synthesis.elapsed_seconds)

        # Cost summary
        all_responses = responses + reviews + [synthesis]
        total_cost = sum(r.cost_usd for r in all_responses)
        total_time = sum(r.elapsed_seconds for r in all_responses)
        emit("stats", cost=total_cost, time=total_time, agents=len(active))

    except Exception as e:
        emit("error", message=str(e))

    q.put(None)  # Sentinel


def serve(host: str = "0.0.0.0", port: int = 8080):
    """Start the web UI server."""
    server = HTTPServer((host, port), CouncilHandler)
    print(f"\n  Council Web UI: http://localhost:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()
