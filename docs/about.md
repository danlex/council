---
layout: default
title: About — Council of LLMs
---

# About Council

Council is a multi-agent deliberation system that orchestrates 5 frontier LLMs to answer complex questions without confirmation bias.

## The Problem

A single AI model has confirmation bias — it tends to reinforce assumptions in the prompt, agree with the user, and present a single coherent narrative that hides genuine uncertainty. When you ask Claude, GPT, or Gemini the same hard question, each gives you a confident answer that reflects its own training biases.

## The Solution

Council queries **5 different model families** simultaneously, has them **anonymously peer-review each other**, then synthesizes the strongest reasoning while **preserving genuine disagreements**. The result is an answer that surfaces tension rather than hiding it.

## The 5 Agents

| Agent | Provider | Why |
|---|---|---|
| Claude Code | Anthropic | Deep reasoning, tool use (chairman) |
| GPT-4.1 | OpenAI | Broad knowledge, speed |
| Gemini 2.5 Pro | Google | Different training distribution |
| DeepSeek V3 | DeepSeek | Chinese + English perspective |
| Llama 4 Scout | Meta | Open-weight, different alignment |

## The Protocol

1. **Clarify** — Chairman refines the question with the user
2. **Respond** — All 5 agents answer independently in parallel
3. **Review** — Each agent peer-reviews the others (anonymized, no self-review)
4. **Synthesize** — Chairman combines best reasoning, preserves dissent, flags confidence

## Anti-Bias Mechanisms

- **Anonymized review**: models evaluate responses without knowing who wrote them
- **No self-review**: agents cannot review their own responses
- **SOUL.md**: shared protocol instructing all agents to resist sycophancy
- **Dissent preservation**: chairman is explicitly told NOT to average opinions
- **5 model families**: different training data = different blind spots

## Research Basis

Based on 15 academic papers. See [PAPER.md](https://github.com/danlex/council/blob/main/PAPER.md) for the full literature review.

## Source Code

Open source: [github.com/danlex/council](https://github.com/danlex/council)

127 automated tests. 42 bugs found and fixed across 4 review rounds.
