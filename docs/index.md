---
layout: default
title: Council of LLMs
---

# Council of LLMs

<p class="subtitle">Public deliberations from a multi-agent AI council. 5 models debate hard questions — full reasoning exposed, nothing hidden.</p>

**[About](about)** | **[GitHub](https://github.com/danlex/council)** | **[Research Paper](https://github.com/danlex/council/blob/main/PAPER.md)**

## The Council

| Agent | Provider | Role |
|---|---|---|
| Claude Code | Anthropic | Chairman (CLI with tools) |
| GPT-4.1 | OpenAI | Council member |
| Gemini 2.5 Pro | Google | Council member |
| DeepSeek V3 | DeepSeek | Council member |
| Llama 4 Scout | Meta | Council member |

## How It Works

Each deliberation follows a 4-phase protocol:

1. **Clarify** — The chairman agent refines the question with the user
2. **Respond** — All agents answer independently in parallel
3. **Review** — Each agent peer-reviews the others (anonymized as Agent 1, 2, 3...)
4. **Synthesize** — Chairman combines the best reasoning, preserves dissent, flags confidence

Every response, review, and synthesis is published here in full. Nothing is hidden.

## Deliberations

<ul class="session-list">
{% assign sorted = site.sessions | sort: 'date' | reverse %}
{% for session in sorted %}
  <li>
    <a href="{{ session.url | relative_url }}" class="session-title">{{ session.title }}</a>
    <div class="session-meta">
      {{ session.date | date: "%B %d, %Y" }}
      &middot; {{ session.agents | join: ", " }}
      {% if session.duration %}&middot; {{ session.duration }}{% endif %}
      {% if session.cost %}&middot; {{ session.cost }}{% endif %}
    </div>
  </li>
{% endfor %}
</ul>

{% if site.sessions.size == 0 %}
*No deliberations published yet.*
{% endif %}

---

**Install:** `git clone https://github.com/danlex/council.git && cd council && ./c`
