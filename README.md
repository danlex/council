# Council

**Council of LLM CLIs** -- Multi-agent deliberation without confirmation bias.

Council orchestrates multiple AI coding agents (Claude Code, OpenAI Codex CLI, Google Gemini CLI) through a structured protocol: clarify the question, get independent expert responses, conduct anonymized peer review, and synthesize the strongest reasoning into a final answer. It learns from every session.

## Why?

A single AI has confirmation bias. Different AI models have *different* biases. Council surfaces disagreement across models and synthesizes the strongest reasoning -- not the average.

- **Model diversity is the #1 factor** for reducing bias ([arXiv:2511.07784](https://arxiv.org/abs/2511.07784))
- **Multi-model ensembles can perform 83% above the best single model** ([arXiv:2510.21513](https://arxiv.org/abs/2510.21513))
- **Naive consensus voting is a trap** -- Council uses structured evaluation instead

## How It Works

```
$ ./c

  COUNCIL   of LLM CLIs
  Council: Claude Code  Codex CLI  Gemini CLI
  Memory: 5 entries loaded

  What do you want the council to investigate?
  > Should we use Rust or Go for our new API service?

  ┌── Claude Code (Chairman) ──────────────────────┐
  │ A few clarifications:                           │
  │ 1. What kind of API? High-throughput? CRUD?     │
  │ 2. Team size and existing expertise?            │
  │ 3. Performance vs productivity priority?        │
  └─────────────────────────────────────────────────┘

  Your response (or 'go' to start):
  > High-throughput, team of 5, performance matters most. Go.

  ┌── Council Brief ───────────────────────────────┐
  │ Compare Rust vs Go for high-throughput APIs...  │
  └─────────────────────────────────────────────────┘

  [1/3] Stage 1: Independent Responses
  (Claude, Codex, Gemini respond in parallel with live streaming)

  [2/3] Stage 2: Anonymized Peer Review
  (Each agent reviews all others -- identities hidden as Agent 1, 2, 3)

  [3/3] Chairman Synthesis
  ┌── Council Answer ──────────────────────────────┐
  │ ### Consensus: Go for most teams                │
  │ ### Dissent: Rust when compute costs dominate   │
  │ ### Confidence: Medium-High                     │
  └─────────────────────────────────────────────────┘

  Memory saved: memory/learnings/20260404_rust_vs_go.md

  Any corrections or feedback? (enter to skip):
```

### The 4-Phase Flow

1. **Clarify** -- Chairman agent asks questions to refine the scope
2. **Respond** -- All agents answer independently and in parallel (with live streaming)
3. **Review** -- Each agent peer-reviews all responses (anonymized as Agent 1, 2, 3)
4. **Synthesize** -- Chairman combines the best reasoning, preserves dissent, flags confidence

Each CLI agent runs with its **full capabilities** (file I/O, shell, web search, tool use) -- not just raw API calls.

## Install

```bash
git clone https://github.com/danlex/council.git
cd council

# That's it -- ./c auto-creates the venv on first run
./c
```

### Requirements

- **Python 3.11+**
- **tmux** (`brew install tmux`)
- At least one CLI agent:
  - `claude` -- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`npm install -g @anthropic-ai/claude-code`)
  - `codex` -- [Codex CLI](https://github.com/openai/codex) (`npm install -g @openai/codex`)
  - `gemini` -- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`npm install -g @google/gemini-cli`)

## Usage

Just run `./c`. That's it. No subcommands, no flags.

```bash
./c
```

### In-session commands

| Command | Description |
|---------|-------------|
| *(your question)* | Start a council investigation |
| `go` / `yes` / `y` | Confirm and start the council after clarification |
| `cancel` | Cancel current investigation |
| `memory` | View saved memories |
| `models` | Show configured agents |
| `quit` / `exit` | End the session |

### After each council session

The council automatically:
1. **Extracts learnings** from the synthesis and saves to `memory/learnings/`
2. **Asks for feedback** -- your corrections are saved to `memory/corrections/`
3. **Loads all memories** into the next session, so the council gets smarter over time

## Architecture

### SOUL.md -- Shared Anti-Bias Protocol

All agents receive a shared `SOUL.md` that instructs them to:
- Prioritize **evidence over agreement**
- Quantify **uncertainty explicitly**
- Resist **sycophancy and conformity**
- Treat **disagreement as valuable signal**
- Ask "what would a smart person who disagrees say?"

### memory/ -- Persistent Shared Memory

```
memory/
├── MEMORY.md           # Index of all memories
├── learnings/          # Key insights from council sessions
├── corrections/        # User feedback and corrections
├── context/            # Domain knowledge
└── preferences/        # User preferences
```

Memories are loaded into every agent's prompt, so the council learns from past sessions. The memory system is inspired by Claude Code's own memory architecture.

### Key Design Decisions (from research)

| Decision | Why |
|----------|-----|
| **Anonymized review** | Prevents models from recognizing and favoring their own responses |
| **Diverse model families** | Different training data, architectures, and alignment = different blind spots |
| **Preserve dissent** | Forcing consensus destroys the signal -- disagreements are the most valuable output |
| **Structured rubrics** | Open debate lets persuasive-but-wrong arguments win; rubrics enforce evidence evaluation |
| **CLI bridge, not API** | Each agent keeps its full tool-use capabilities (web search, file I/O, shell) |

## Configuration

```yaml
# ~/.config/council/config.yaml
agents:
  claude:
    enabled: true
    command: claude
    args: ["-p", "--max-turns", "10", "--output-format", "text"]
    display_name: Claude Code
    timeout: 300
  codex:
    enabled: true
    command: codex
    args: ["exec", "--skip-git-repo-check"]
    display_name: Codex CLI
    timeout: 300
  gemini:
    enabled: true
    command: gemini
    args: ["-p", "{prompt}"]  # {prompt} is replaced with the actual prompt
    display_name: Gemini CLI
    timeout: 300

chairman: claude
soul_file: SOUL.md
```

To add a new agent (e.g., Aider, Cline, GLM), add an entry to the agents section with the appropriate command and args for non-interactive mode.

## Research

See [PAPER.md](PAPER.md) for the full research paper with literature review, architecture analysis, and 15 references.

Key findings:
- Du et al. (2023) -- Multi-agent debate improves factuality (ICML 2024)
- Wang et al. (2024) -- Mixture-of-Agents surpasses GPT-4o with open-source models
- Wynn et al. (2025) -- Failure modes of naive debate (echo chambers, sycophancy)
- Karpathy (2025) -- LLM Council: anonymized peer review as the key mechanism
- Vallecillos-Ruiz et al. (2025) -- "Popularity trap" in consensus voting

## License

MIT
