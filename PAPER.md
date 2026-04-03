# Council of LLM CLIs: A Tmux-Bridged Multi-Agent Deliberation System for Bias-Free Complex Question Answering

**Authors:** Adan (with research assistance from Claude Opus 4.6)
**Date:** April 2026
**Repository:** github.com/[TBD]/council

---

## Abstract

We present **Council**, a command-line tool that orchestrates multiple LLM-powered coding agents (Claude Code, OpenAI Codex CLI, Google Gemini CLI) through a structured three-stage deliberation protocol — independent response, anonymized peer review, and chairman synthesis — designed to eliminate confirmation bias in complex question answering. Unlike API-based ensemble approaches, Council bridges directly over full CLI agents via tmux/subprocess, preserving each agent's complete toolchain, reasoning capabilities, and agentic behaviors. Drawing on research in multi-agent debate (Du et al., 2023), Mixture-of-Agents (Wang et al., 2024), and ensemble failure modes (Wynn et al., 2025), we design the system with explicit anti-bias mechanisms: identity anonymization during review, diversity-based weighting over consensus voting, mandatory dissent preservation, and a shared SOUL.md that instructs all agents to prioritize evidence over agreement. We survey the relevant literature, describe the architecture, and discuss how the system addresses known failure modes including echo chambers, sycophancy, and the "popularity trap."

---

## 1. Introduction

### 1.1 The Problem: Confirmation Bias in Single-Model Systems

Large language models (LLMs), despite their capabilities, suffer from systematic biases: they tend to confirm assumptions embedded in prompts (Kim & Torr, 2025), exhibit sycophantic agreement with users (Perez et al., 2022), and share correlated errors due to similar training data and RLHF procedures. When a developer asks a single AI assistant a complex question — one involving trade-offs, contested evidence, or domain uncertainty — the response reflects that single model's biases, training distribution, and alignment pressures.

This is not merely theoretical. Studies show that LLMs reinforce input bias rather than challenging it, creating what Kim & Torr (2025) term "confirmation echo chambers" even within multi-agent debate settings. The result: users receive confident-sounding answers that may be systematically skewed.

### 1.2 The Opportunity: Model Diversity as Debiasing

Different LLM families — Anthropic's Claude, OpenAI's GPT, Google's Gemini, Z.ai's GLM, MiniMax's M-series — have fundamentally different training data, architectures, alignment procedures, and reasoning approaches. A controlled study on multi-agent debate (2025) found that **"intrinsic reasoning strength and group diversity are the dominant drivers of debate success,"** while structural parameters like speaking order or confidence visibility offer limited gains.

This suggests that the most effective debiasing strategy is not better prompting of a single model, but structured deliberation across maximally diverse models.

### 1.3 Our Contribution

We present **Council**, a practical CLI tool that:

1. **Bridges over existing CLI agents** (Claude Code, Codex, Gemini CLI) via subprocess/tmux, preserving each agent's full agentic capabilities
2. **Implements a research-backed 3-stage deliberation protocol** with anonymized peer review
3. **Shares a common "soul"** (SOUL.md) that explicitly instructs all agents to resist confirmation bias
4. **Preserves dissent** rather than forcing consensus — treating disagreement as valuable signal
5. **Addresses known failure modes** from the literature: echo chambers, sycophancy, popularity traps, and persuasion-over-truth

---

## 2. Related Work

### 2.1 Multi-Agent Debate

**Du et al. (2023)** introduced multi-agent debate for LLMs, showing that multiple model instances debating over rounds improve factuality and reasoning on GSM8K, TruthfulQA, and other benchmarks. Their key insight: even same-model debate helps, because the process of confronting alternative reasoning surfaces errors. Published at ICML 2024.

**Liang et al. (2023)** extended this with Encouraging Divergent Thinking, introducing a judge agent to moderate debate and prevent degeneration-of-thought — where models get stuck reinforcing the same reasoning pattern.

### 2.2 Mixture-of-Agents (MoA)

**Wang et al. (2024)** proposed Mixture-of-Agents, a layered architecture where proposer LLMs generate diverse responses and aggregator LLMs synthesize them. Their key finding: LLMs exhibit "collaborativeness" — they produce better responses when given other models' outputs as context, even from weaker models. Using only open-source models, MoA achieved 65.1% on AlpacaEval 2.0, surpassing GPT-4o's 57.5%.

### 2.3 LLM-Blender

**Jiang et al. (ACL 2023)** introduced LLM-Blender with two-stage ensembling: PairRanker (pairwise comparison of candidate outputs) followed by GenFuser (fusion of top-ranked outputs). The blended output ranked top-3 in 68.59% of cases, consistently outperforming any individual model.

### 2.4 Council and Jury Approaches

**Zhao et al. (2024)** proposed Language Model Council — 20 LLMs collaborating to create tests, respond, and evaluate each other. Council rankings proved more robust and more aligned with human evaluations than any single-model judge.

**Karpathy (2025)** released LLM Council as a practical implementation: a web app that sends queries to multiple LLMs via OpenRouter, conducts anonymized peer review, and has a Chairman model synthesize the final answer. The anonymization during peer review — preventing models from recognizing and favoring their own responses — is a critical anti-bias mechanism.

**Verga et al. (EMNLP 2024)** showed in PoLL that a pool of diverse smaller LLM judges outperforms GPT-4 as a single judge, at lower cost and with less individual bias.

### 2.5 Failure Modes and Limitations

The literature also identifies significant failure modes:

**Wynn et al. (ICML 2025)** — "Talk Isn't Always Cheap" — demonstrated that debate can be harmful. Models shift from correct to incorrect answers to agree with peers (sycophancy), creating a "tyranny of the majority" where incorrect majority opinions suppress correct minority positions. Eloquent but wrong arguments can sway model judges.

**A controlled study (2025)** — "Can LLM Agents Really Debate?" — found that when model groups are homogeneous, debates create echo chambers. The study confirmed that diversity is the dominant driver of success, not debate structure.

**Kim & Torr (2025)** — MoLaCE — showed that confirmation bias in LLMs is "already harmful in base models and poses an even greater risk in multi-agent debate, where echo chambers reinforce bias instead of correction." They proposed Mixture of Latent Concept Experts as a single-model alternative that matches multi-agent debate performance at lower cost.

**Vallecillos-Ruiz et al. (2025)** — studying LLM ensembles for code generation — found that consensus-based strategies fall into a **"popularity trap"** that amplifies common but incorrect outputs. Diversity-based selection strategies realize up to 95% of the theoretical performance ceiling.

### 2.6 Secure Code Generation with Multi-LLM Teams

**arXiv:2603.22717 (March 2026)** showed that multi-LLM ensemble pipelines augmented with static analysis improved secure code generation by **up to 47.3%** over single-model baselines, demonstrating the approach's value beyond question-answering.

---

## 3. CLI Agent Landscape

### 3.1 Claude Code (Anthropic)

- **Model:** Opus 4.6 (1M context)
- **SWE-bench Verified:** 80.8% (highest)
- **Strengths:** Deep reasoning, multi-file refactoring, Agent Teams for parallel sub-agents
- **Architecture:** Dense transformer with extended thinking

### 3.2 Codex CLI (OpenAI)

- **Model:** GPT-5-Codex / GPT-5.4
- **Aider Polyglot:** 88.0% (highest code editing score)
- **Strengths:** Speed (240+ tok/s), breadth across languages, GitHub integration
- **Architecture:** Dense transformer, open-source Rust CLI

### 3.3 Gemini CLI (Google)

- **Model:** Gemini 2.5+ (1M token context)
- **Strengths:** Largest native context window, free tier (1000 req/day), Google Search grounding
- **Architecture:** Multimodal foundation model

### 3.4 GLM-5 (Z.ai)

- **Model:** 745B MoE (44B active parameters)
- **SWE-bench Verified:** 77.8% (highest open-source)
- **Strengths:** Open-weights, cost-effective, strong agentic capabilities

### 3.5 MiniMax M2.5

- **SWE-bench Verified:** 80.2%
- **Multi-SWE-bench:** 51.3% (highest, beating Claude at 50.3%)
- **Strengths:** Function calling, speed, Anthropic-compatible API

### 3.6 Complementarity Argument

These models are **complementary, not substitutable**:

| Dimension | Claude | GPT/Codex | Gemini | GLM-5 | MiniMax |
|-----------|--------|-----------|--------|-------|---------|
| Training Data | Anthropic corpus | OpenAI corpus | Google corpus | Chinese + English | Chinese + English |
| Architecture | Dense transformer | Dense transformer | Multimodal | MoE (256 experts) | MoE variant |
| Alignment | Constitutional AI | RLHF + InstructGPT | RLHF + Google Safety | Chinese RLHF | Chinese RLHF |
| Reasoning Style | Careful analysis | Broad pattern matching | Grounded search | Engineering-focused | Agent-optimized |

Different training data, architectures, and alignment approaches produce genuinely different blind spots and strengths — which is precisely what makes a council effective.

---

## 4. Architecture

### 4.1 Design Principles

Based on the literature review, we adopt five design principles:

1. **Bridge over CLIs, not APIs:** Each CLI agent (Claude Code, Codex, Gemini CLI) has its own agentic capabilities — file access, shell execution, web search, tool use. By bridging over the full CLI rather than calling a raw API, the council preserves each agent's complete reasoning and tool-use capabilities.

2. **Maximize model diversity:** The default configuration includes agents from Anthropic, OpenAI, and Google — three different training distributions, architectures, and alignment approaches. Additional agents (GLM, MiniMax, DeepSeek) can be added.

3. **Anonymize during peer review:** Following Karpathy's design, agent identities are hidden during Stage 2 review. Models evaluate responses labeled "Agent 1, 2, 3..." preventing style-based favoritism.

4. **Preserve dissent:** The chairman is explicitly instructed NOT to average opinions or force consensus. Genuine disagreements are presented with evidence on both sides.

5. **Shared soul, not shared bias:** A common SOUL.md file instructs all agents to resist sycophancy, prioritize evidence, and flag uncertainty — establishing a shared anti-bias protocol across different model families.

### 4.2 Three-Stage Pipeline

```
                    ┌─────────────┐
                    │  User Query │
                    │  + SOUL.md  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌──────────┐
     │ Claude Code│ │ Codex CLI │ │Gemini CLI│    STAGE 1
     │ (Opus 4.6) │ │(GPT-5.4)  │ │(Gemini 3)│    Independent
     └─────┬──────┘ └─────┬─────┘ └────┬─────┘    Response
           │              │             │
           ▼              ▼             ▼
     ┌──────────────────────────────────────┐
     │     Responses anonymized as          │
     │   Agent 1, Agent 2, Agent 3          │     STAGE 2
     │                                      │     Anonymized
     │   Each agent reviews ALL others      │     Peer Review
     │   Structured rubric evaluation       │
     └──────────────────┬───────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │   Chairman LLM   │
              │                  │                  STAGE 3
              │   Synthesizes:   │                  Chairman
              │   - Best reasoning│                 Synthesis
              │   - Confidence   │
              │   - Consensus    │
              │   - Dissent      │
              │   - Blind spots  │
              └──────────────────┘
```

### 4.3 Tmux Bridge Architecture

Rather than using API clients, Council uses subprocess/tmux to interface with CLI agents:

```python
# Sequential: subprocess with stdin pipe
subprocess.run(
    ["claude", "-p", "--max-turns", "10", "--output-format", "text"],
    input=prompt, capture_output=True, text=True, timeout=300,
)

# Parallel: tmux sessions
tmux new-session -d -s council-{run_id}-{agent}
    "cat prompt.txt | claude -p ... > output.txt 2>&1"
```

This approach:
- Preserves each CLI's full tool-use capabilities (file I/O, shell, web search)
- Allows true parallel execution via tmux
- Handles heterogeneous CLI interfaces (different flag syntax per tool)
- Strips CLI-specific metadata from outputs (Codex headers, ANSI codes)

### 4.4 SOUL.md: Shared Anti-Bias Protocol

All agents receive the same SOUL.md preamble, which establishes:

- **No sycophancy**: "Do not agree with a position simply because it is popular or expected"
- **Evidence-first**: "A correct but plain argument beats a persuasive but wrong one"
- **Quantified uncertainty**: "If you are uncertain, quantify it"
- **Suspicious consensus**: "If all responses agree, be suspicious — ask what everyone might be missing"
- **Active disagreement**: "Disagreements between experts are the most valuable signal"

This shared identity document ensures that even though agents come from different model families, they share a common deliberation ethic that actively resists the failure modes identified in the literature.

---

## 5. Addressing Known Failure Modes

| Failure Mode | Source | Our Mitigation |
|---|---|---|
| **Echo chambers** | Wynn et al., 2025; "Can LLM Agents Really Debate?" | Use maximally diverse model families (Anthropic + OpenAI + Google) |
| **Sycophancy** | Models abandon correct answers for consensus | SOUL.md explicitly prohibits conformity; chairman instructed to preserve minority positions |
| **Tyranny of majority** | Incorrect majority suppresses correct minority | Chairman weights by reasoning quality, not vote count |
| **Popularity trap** | Vallecillos-Ruiz et al., 2025 | No majority voting; synthesis is by structured evaluation |
| **Persuasion over truth** | Eloquent wrong answers sway judges | Structured rubric evaluation (accuracy, reasoning, completeness, nuance) — not open debate |
| **Same-model bias** | Shared training → correlated errors | Different CLI tools use different model families by design |
| **Prompt confirmation bias** | Kim & Torr, 2025 | SOUL.md instructs "consider what a smart person who disagrees would say" |
| **Identity favoritism** | Models prefer their own outputs | Anonymized identities (Agent 1, 2, 3) during peer review |

---

## 6. Comparison with Existing Approaches

| Feature | Karpathy's LLM Council | Copilot Council | Together MoA | **Council (ours)** |
|---|---|---|---|---|
| Interface | Web app | CLI | Library | **CLI** |
| Model access | API via OpenRouter | API via Copilot | API | **Full CLI agents** |
| Tool use preserved | No (API only) | No (API only) | No (API only) | **Yes (full CLI)** |
| Anonymized review | Yes | Yes | No | **Yes** |
| Shared soul/memory | No | No | No | **Yes (SOUL.md)** |
| Dissent preservation | No (consensus) | No (consensus) | No (synthesis) | **Yes (explicit)** |
| Parallel execution | Yes | Yes | Yes | **Yes (tmux)** |
| Open source | Yes | Yes | Yes | **Yes** |
| Runs locally | Yes | No (GitHub sub) | No (API) | **Yes** |

The key differentiator of Council is that it bridges over **full CLI agents** rather than raw API calls. When Claude Code answers a question, it can read files, search the web, run code, and use its full agentic loop. This is fundamentally more capable than sending a prompt to a model API endpoint.

---

## 7. Empirical Evidence for Council Effectiveness

The literature provides strong evidence that the council approach works:

| Study | Method | Improvement |
|---|---|---|
| Du et al., 2023 | Multi-agent debate | ~7% accuracy gain on GSM8K |
| Wang et al., 2024 | Mixture of Agents | +7.6% on AlpacaEval (65.1% vs 57.5%) |
| Jiang et al., 2023 | LLM-Blender | Top-3 in 68.59% of cases |
| Chen et al., 2023 | ReConcile | 4-10% gains on reasoning benchmarks |
| Zhao et al., 2024 | Language Model Council | More robust rankings than any single judge |
| Verga et al., 2024 | PoLL (diverse judges) | Outperforms GPT-4 single judge |
| Vallecillos-Ruiz et al., 2025 | Code ensembles | 83% theoretical ceiling above best single model |
| arXiv:2603.22717, 2026 | Multi-LLM secure code | Up to 47.3% improvement in code security |

The theoretical upper bound of 83% improvement over the best single model (Vallecillos-Ruiz et al.) represents the maximum achievable with perfect selection from diverse outputs. With diversity-based selection, up to 95% of this ceiling can be realized in practice.

---

## 8. Limitations and Future Work

### 8.1 Current Limitations

1. **Latency:** Three sequential stages (respond → review → synthesize) multiply the response time. A single Claude Code response takes ~5-30s; the full council protocol takes 3-10x longer.

2. **Cost:** Each stage queries each agent, so a 3-agent, 3-stage council makes ~9 LLM calls per question. At frontier model pricing, this is $1-5 per complex query.

3. **Agent availability:** Not all CLIs are installed on all systems. The tool gracefully degrades but a single-agent council provides no bias reduction.

4. **Codex limitations:** OpenAI Codex CLI is designed for coding tasks and may not handle general knowledge questions as effectively as its ChatGPT counterpart.

### 8.2 Future Directions

1. **Streaming output:** Show Stage 1 responses as they arrive, start Stage 2 as each agent finishes, reducing perceived latency.

2. **Smart chairman rotation:** Rotate which model acts as chairman across queries to prevent chairman bias.

3. **Confidence-weighted routing:** Skip the full council for questions where a single model is confident; escalate only uncertain questions to the full protocol.

4. **Adding more agents:** GLM CLI, MiniMax CLI, DeepSeek CLI, Aider, Cline — more model diversity increases debiasing effectiveness.

5. **Persistent memory:** Extend SOUL.md into a shared memory system that accumulates knowledge across queries, building a council-level understanding over time.

6. **Evaluation framework:** Systematic comparison of council answers vs. single-model answers on benchmarks like TruthfulQA, StrategyQA, and domain-specific factual questions.

---

## 9. Conclusion

Council demonstrates that practical multi-LLM deliberation systems can be built today using existing CLI tools. By bridging over full CLI agents rather than raw APIs, we preserve each model's complete capabilities while adding the bias-reduction benefits of structured multi-agent deliberation.

The literature is clear: model diversity is the strongest lever for reducing confirmation bias, but naive debate can backfire through echo chambers and sycophancy. Our design addresses these failure modes through anonymization, structured rubric evaluation, mandatory dissent preservation, and a shared anti-bias protocol.

The council of LLMs is not about finding the "average" answer — it is about surfacing the best reasoning, preserving genuine disagreement, and making the user aware of what the collective intelligence of multiple frontier models actually agrees and disagrees about.

---

## References

1. Du, Y., Li, S., Torralba, A., Tenenbaum, J.B., & Mordatch, I. (2023). "Improving Factuality and Reasoning in Language Models through Multiagent Debate." *ICML 2024*. arXiv:2305.14325

2. Wang, J., Wang, J., Athiwaratkun, B., Zhang, C., & Zou, J. (2024). "Mixture-of-Agents Enhances Large Language Model Capabilities." arXiv:2406.04692

3. Jiang, D., Ren, X., & Lin, B.Y. (2023). "LLM-Blender: Ensembling Large Language Models with Pairwise Ranking and Generative Fusion." *ACL 2023*. arXiv:2306.02561

4. Kim, H. & Torr, P. (2025). "Single LLM Debate, MoLaCE: Mixture of Latent Concept Experts Against Confirmation Bias." arXiv:2512.23518

5. Wynn, M., Satija, H., & Hadfield, G. (2025). "Talk Isn't Always Cheap: Understanding Failure Modes in Multi-Agent Debate." *ICML 2025*. arXiv:2509.05396

6. "Can LLM Agents Really Debate? A Controlled Study of Multi-Agent Debate in Logical Reasoning." (2025). arXiv:2511.07784

7. Chen, J.C., Saha, S., & Bansal, M. (2023). "ReConcile: Round-Table Conference Improves Reasoning via Consensus Among Diverse LLMs." arXiv:2309.13007

8. Zhao, Y. et al. (2024). "Language Model Council." arXiv:2406.08598

9. Verga, P. et al. (2024). "PoLL: A Pool of LLM Judges." *EMNLP 2024*.

10. Li, J. et al. (2024). "More Agents Is All You Need." arXiv:2402.05120

11. Vallecillos-Ruiz, J. et al. (2025). "Wisdom and Delusion of LLM Ensembles for Code Generation and Repair." arXiv:2510.21513

12. "Does Teaming-Up LLMs Improve Secure Code Generation?" (2026). arXiv:2603.22717

13. Liang, T. et al. (2023). "Encouraging Divergent Thinking in Large Language Models through Multi-Agent Debate." arXiv:2305.19118

14. Karpathy, A. (2025). "LLM Council." GitHub: karpathy/llm-council

15. Irving, G., Christiano, P., & Amodei, D. (2018). "AI Safety via Debate." arXiv:1805.00899

---

## Appendix A: Installation

```bash
# Clone the repository
git clone https://github.com/[user]/council.git
cd council

# Create virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Verify CLI agents are available
which claude codex gemini

# Initialize config
council config --init

# Ask the council a question
council ask "What are the trade-offs between microservices and monoliths for a 10-person startup?"

# Quick mode (no peer review, just parallel responses)
council quick "Explain quantum computing"

# Verbose mode (show individual responses and reviews)
council ask -v "Is P equal to NP?"

# Specify which agents to use
council ask --agents claude,codex "Best database for time-series data?"

# Use tmux for true parallel execution
council ask -p "Compare Rust vs Go for systems programming"
```

## Appendix B: Configuration

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
    args: ["-p"]
    display_name: Gemini CLI
    timeout: 300

chairman: claude
soul_file: SOUL.md

review:
  anonymize: true
  rubric: [accuracy, reasoning, completeness, nuance]

synthesis:
  preserve_dissent: true
  show_confidence: true
```

## Appendix C: SOUL.md Template

The shared soul file establishes the deliberation ethic:

```markdown
# Council Soul

## Core Principles
1. Intellectual honesty over agreement
2. Evidence over eloquence
3. Uncertainty is information
4. No sycophancy
5. Diverse perspectives are the council's strength

## Anti-Bias Guardrails
- Do not anchor on the first response you see
- Do not assume majority opinion = correct opinion
- Consider: "What would a smart person who disagrees say?"
- If all responses agree, be suspicious
```
