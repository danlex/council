# Council

**Council of LLM CLIs** — Query multiple AI coding agents and synthesize bias-free answers.

Council orchestrates Claude Code, OpenAI Codex CLI, and Google Gemini CLI through a 3-stage deliberation protocol: independent response, anonymized peer review, and chairman synthesis. Based on research in multi-agent debate, Mixture-of-Agents, and ensemble failure modes.

## Why?

A single AI model has confirmation bias. Different models have *different* biases. A structured council surfaces disagreement and synthesizes the strongest reasoning across all of them.

- **Model diversity is the #1 factor** for reducing bias (arXiv:2511.07784)
- **Multi-model ensembles can perform 83% above the best single model** (arXiv:2510.21513)
- **Naive consensus voting is a trap** — Council uses structured evaluation instead

## How It Works

```
Question + SOUL.md
       |
  ┌────┼────┐
  v    v    v
Claude Codex Gemini     <- Stage 1: Independent Response
  |    |    |
  v    v    v
  Anonymized Peer       <- Stage 2: Each reviews all others
  Review (Agent 1,2,3)     (identities hidden)
       |
       v
  Chairman Synthesis    <- Stage 3: Best reasoning + dissent
```

Each CLI agent runs with its **full capabilities** (file I/O, shell, web search, tool use) — not just raw API calls.

## Install

```bash
git clone https://github.com/[user]/council.git
cd council
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Requires: `claude` (Claude Code), `codex` (OpenAI Codex CLI), `gemini` (Gemini CLI), `tmux`.

## Usage

```bash
# Ask the council
council ask "What are the trade-offs between microservices and monoliths?"

# Quick mode (parallel responses, no review)
council quick "Explain quantum computing"

# Verbose (show individual responses and reviews)
council ask -v "Is P equal to NP?"

# Pick specific agents
council ask --agents claude,codex "Best database for time-series data?"

# Parallel execution via tmux
council ask -p "Compare Rust vs Go for systems programming"

# Override chairman
council ask -c codex "Should we use GraphQL or REST?"
```

## Commands

| Command | Description |
|---------|-------------|
| `council ask` | Full 3-stage deliberation |
| `council quick` | Stage 1 only (fast, no review) |
| `council models` | List configured agents |
| `council config --init` | Create default config |
| `council config --show` | Show current config |

## Configuration

```yaml
# ~/.config/council/config.yaml
agents:
  claude:
    enabled: true
    command: claude
    args: ["-p", "--max-turns", "10", "--output-format", "text"]
    timeout: 300
  codex:
    enabled: true
    command: codex
    args: ["exec", "--skip-git-repo-check"]
    timeout: 300
  gemini:
    enabled: true
    command: gemini
    args: ["-p"]
    timeout: 300

chairman: claude
soul_file: SOUL.md
```

## SOUL.md — Shared Anti-Bias Protocol

All agents receive a shared `SOUL.md` that instructs them to:
- Prioritize evidence over agreement
- Quantify uncertainty explicitly
- Resist sycophancy and conformity
- Treat disagreement as valuable signal

## Research

See [PAPER.md](PAPER.md) for the full research paper with literature review, architecture analysis, and references.

Key references:
- Du et al. (2023) — Multi-agent debate improves factuality
- Wang et al. (2024) — Mixture-of-Agents surpasses GPT-4o
- Wynn et al. (2025) — Failure modes of naive debate
- Karpathy (2025) — LLM Council implementation
- Vallecillos-Ruiz et al. (2025) — "Popularity trap" in consensus voting

## License

MIT
