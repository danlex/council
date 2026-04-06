# Council

**Multi-agent deliberation without confirmation bias.**

Council orchestrates 5 frontier LLMs — Claude, GPT, Gemini, DeepSeek, Llama — through a structured protocol: clarify the question, get independent expert responses, conduct anonymized peer review, and synthesize the strongest reasoning into a final answer. It learns from every session.

**[Live Deliberations](https://danlex.github.io/council/)** | **[Research Paper](PAPER.md)** | **[GitHub](https://github.com/danlex/council)**

---

## Why?

A single AI has confirmation bias. Different AI models have *different* biases. Council surfaces genuine disagreement across models and synthesizes the strongest reasoning — not the average.

- **Model diversity is the #1 factor** for reducing bias ([arXiv:2511.07784](https://arxiv.org/abs/2511.07784))
- **Multi-model ensembles can perform 83% above the best single model** ([arXiv:2510.21513](https://arxiv.org/abs/2510.21513))
- **Naive consensus voting is a trap** — Council uses structured evaluation instead ([arXiv:2509.05396](https://arxiv.org/abs/2509.05396))

## The Council

| Agent | Provider | Architecture | Why it's here |
|---|---|---|---|
| **Claude Code** | Anthropic (CLI) | Dense transformer | Full agentic tools (chairman) |
| **GPT-4.1** | OpenAI (OpenRouter) | Dense transformer | Broad knowledge, speed |
| **Gemini 2.5 Pro** | Google (OpenRouter) | Multimodal | Different training distribution |
| **DeepSeek V3** | DeepSeek (OpenRouter) | MoE | Chinese + English training data |
| **Llama 4 Scout** | Meta (OpenRouter) | Open-weight | Open-source perspective |

5 model families with different training data, architectures, and alignment approaches = maximally different blind spots.

## How It Works

```
$ ./c

  COUNCIL   of LLM CLIs
  Council: Claude Code  GPT-4.1  Gemini 2.5 Pro  DeepSeek V3  Llama 4 Scout
  Chairman: Claude Code
  Memory: 3 entries loaded

  What do you want the council to investigate?
  > Should we build AGI as fast as possible, or slow down?

  ┌── Claude Code (Chairman) ──────────────────────┐
  │ A few clarifications:                           │
  │ 1. Whose perspective — humanity, labs, govts?   │
  │ 2. What time horizon?                           │
  │ 3. What does "slow down" mean concretely?       │
  └─────────────────────────────────────────────────┘

  Your response: > All perspectives. Go.

  ┌── Council Brief ───────────────────────────────┐
  │ Analyze AGI development pace from all angles... │
  └─────────────────────────────────────────────────┘

  [1/3] Stage 1: Independent Responses     (5 agents in parallel, streaming)
  [2/3] Stage 2: Anonymized Peer Review    (each reviews others, no self-review)
  [3/3] Chairman Synthesis                 (preserves dissent, flags confidence)

  ┌── Council Answer (Chairman: Claude Code) ──────┐
  │ ### Consensus Points                            │
  │ All agents agree safety research is essential...│
  │                                                 │
  │ ### Points of Dissent                           │
  │ GPT emphasized competitive dynamics...          │
  │ DeepSeek highlighted different cultural views... │
  │ Gemini flagged regulatory capture risks...      │
  │                                                 │
  │ ### Confidence: Medium                          │
  └─────────────────────────────────────────────────┘

  Session saved: 20260406_111216.json
  Memory saved: memory/learnings/agi_development_pace.md

  Any corrections or feedback? (enter to skip):
```

### The 4-Phase Flow

```
Question + SOUL.md + Relevant Memories
       │
  ┌────┼────┬────┬────┐
  v    v    v    v    v
Claude GPT Gemini DS Llama     ← Phase 1: Independent Responses (parallel)
  │    │    │    │    │
  v    v    v    v    v
  Anonymized Peer Review        ← Phase 2: Each reviews others (parallel)
  (Agent 1,2,3,4,5)              (self-review excluded, SOUL enforced)
       │
       v
  Chairman Synthesis            ← Phase 3: Best reasoning + dissent
  (SOUL + memory injected)        (not consensus — dissent preserved)
       │
       v
  Learn + Save                  ← Phase 4: Extract learnings to memory
```

### Anti-Bias Mechanisms

| Mechanism | What it prevents | Source |
|---|---|---|
| **Anonymized review** | Models favoring their own output | Karpathy (2025) |
| **No self-review** | Self-evaluation bias | Round 2 fix |
| **SOUL.md in all stages** | Sycophancy, conformity | Council design |
| **Preserve dissent** | Tyranny of majority | Wynn et al. (2025) |
| **Structured rubrics** | Persuasion over truth | Du et al. (2023) |
| **5 model families** | Correlated errors | Wang et al. (2024) |
| **Memory relevance filter** | Prompt noise from unrelated memories | Round 4 |
| **CLI vs API honest prompts** | API agents told to "use tools" they don't have | Round 3 |

## Install

```bash
git clone https://github.com/danlex/council.git
cd council
echo 'OPENROUTER_API_KEY=your-key-here' > .env   # Get key at openrouter.ai/keys
./c                                                # Auto-creates venv on first run
```

### Requirements

- **Python 3.11+**
- **tmux** (`brew install tmux`)
- **OpenRouter API key** ([openrouter.ai/keys](https://openrouter.ai/keys)) — one key for GPT, Gemini, DeepSeek, Llama
- **Claude Code** (optional, for chairman CLI agent): `npm install -g @anthropic-ai/claude-code`

Without Claude Code installed, the council uses the 4 API agents with GPT as chairman.

## Usage

Just `./c`. No subcommands, no flags.

### REPL Commands

| Command | Description |
|---|---|
| *(your question)* | Start a council investigation |
| `!your question` | Skip clarification — go straight to council |
| `go` / `yes` / `y` | Confirm brief and start deliberation |
| `cancel` | Cancel current investigation |
| `memory` | View saved memories |
| `sessions` | Browse past council sessions |
| `models` | Show configured agents |
| `eval` | Run benchmark: council vs single agents (5 questions) |
| `publish` | Generate GitHub Pages from sessions |
| `web` | Launch browser UI at localhost:8080 |
| `help` | Show commands |
| `quit` | Exit |

### Web UI

Type `web` in the REPL or run directly:

```bash
python3 -m council.web
# Open http://localhost:8080
```

Live streaming interface — watch all agents respond in parallel in your browser.

### MCP Server (Claude Code / Cursor)

Use the council as a tool from Claude Code or Cursor:

```json
// .mcp.json or ~/.claude/settings.json
{
  "mcpServers": {
    "council": {
      "command": "/path/to/council/.venv/bin/python3",
      "args": ["-m", "council.mcp_server"]
    }
  }
}
```

Exposes two tools: `council_ask` (full deliberation) and `council_memory` (view learnings).

### Evaluation

Run the benchmark to compare council vs individual agents:

```bash
./c
> eval
```

Runs 5 questions across categories (contested, reasoning, factual, values, technical). Each agent answers individually, then the full council runs. A judge scores accuracy, completeness, nuance, and bias resistance (1-10). Results show whether the council actually outperforms single models.

## Architecture

### Hybrid CLI + API Bridge

```
Claude Code ──── subprocess (Popen) ──── Full agentic: files, shell, web
GPT-4.1    ──── OpenRouter SSE API ──── Fast, streaming, cost-tracked
Gemini 2.5 ──── OpenRouter SSE API ──── Different training distribution
DeepSeek V3 ─── OpenRouter SSE API ──── Chinese + English perspective
Llama 4    ──── OpenRouter SSE API ──── Open-weight perspective
```

- **CLI agents** (Claude) keep full tool-use capabilities
- **API agents** use OpenRouter's streaming SSE with retry + backoff
- **Parallel execution** via `ThreadPoolExecutor` with thread-safe streaming display
- **Cost tracking** from OpenRouter usage data, shown per-session

### SOUL.md — Shared Anti-Bias Protocol

All agents in all stages receive `SOUL.md`:

```markdown
Core Principles:
1. Intellectual honesty over agreement
2. Evidence over eloquence
3. Uncertainty is information — quantify it
4. No sycophancy — disagree when you should
5. If all responses agree, be suspicious
```

### Persistent Shared Memory

```
memory/
├── MEMORY.md           # Index (capped at 100 entries)
├── learnings/          # Key insights from sessions
├── corrections/        # User feedback
├── context/            # Domain knowledge
├── sessions/           # Full JSON transcripts
├── evals/              # Benchmark results
└── preferences/        # User preferences
```

- **Relevance-filtered**: only memories matching the current question are loaded
- **Keyword extraction**: stop words removed, scored by overlap
- **Session transcripts**: full JSON with all responses, reviews, synthesis, costs
- **Learning extraction**: chairman distills key insights after each session

## Configuration

```yaml
# ~/.config/council/config.yaml
agents:
  claude:
    enabled: true
    type: cli
    command: claude
    args: ["-p", "--max-turns", "10", "--output-format", "text"]
    display_name: Claude Code
    timeout: 300
  gpt:
    enabled: true
    type: openrouter
    model: openai/gpt-4.1
    display_name: GPT-4.1
    timeout: 120
  gemini:
    enabled: true
    type: openrouter
    model: google/gemini-2.5-pro-preview
    display_name: Gemini 2.5 Pro
    timeout: 120
  deepseek:
    enabled: true
    type: openrouter
    model: deepseek/deepseek-chat-v3-0324
    display_name: DeepSeek V3
    timeout: 120
  llama:
    enabled: true
    type: openrouter
    model: meta-llama/llama-4-scout
    display_name: Llama 4 Scout
    timeout: 120

chairman: claude
soul_file: SOUL.md
```

Add any model from [OpenRouter's catalog](https://openrouter.ai/models) with just a config entry.

## Project Quality

- **127 automated tests** covering config, bridge, memory, prompts, pipeline, display
- **4 rounds of code review** — 42 issues found and fixed
- **Thread-safe** streaming display with `threading.Lock`
- **Ctrl-C handling** with clean terminal cleanup
- **Session transcripts** saved automatically
- **No test pollution** — tests isolated from real memory via `conftest.py`

## Research

See [PAPER.md](PAPER.md) for the full research paper (15 references).

Key findings from the literature:

| Paper | Finding |
|---|---|
| Du et al. (ICML 2024) | Multi-agent debate improves factuality and reasoning |
| Wang et al. (2024) | Mixture-of-Agents surpasses GPT-4o with open-source models |
| Wynn et al. (ICML 2025) | Naive debate can backfire — echo chambers, sycophancy |
| Karpathy (2025) | Anonymized peer review prevents favoritism |
| Vallecillos-Ruiz et al. (2025) | Consensus voting falls into "popularity trap" |
| Kim & Torr (2025) | Confirmation bias is worse in multi-agent debate without safeguards |

## Example: AGI Development Pace

The council's first public deliberation asked: *"Should we build AGI as fast as possible, or slow down?"*

- **3 agents** responded independently (GPT-4.1, Gemini 2.5 Pro, Claude Code)
- **3 peer reviews** conducted anonymously
- **Chairman synthesis** preserved genuine disagreements
- **Key dissent**: agents disagreed on whether competitive dynamics justify speed
- **Full transcript**: [danlex.github.io/council](https://danlex.github.io/council/)

## License

MIT
