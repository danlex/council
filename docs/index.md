---
layout: default
title: Council of LLMs
---

# Council of LLMs

<p class="subtitle">Public deliberations from a multi-agent AI council. Claude, GPT, and Gemini debate hard questions — no confirmation bias, full reasoning exposed.</p>

## How It Works

Each deliberation follows a 4-phase protocol:

1. **Clarify** — A chairman agent refines the question with the user
2. **Respond** — All agents answer independently in parallel
3. **Review** — Each agent peer-reviews the others (anonymized as Agent 1, 2, 3)
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
*No deliberations yet. Run `./c` and publish with `./publish`.*
{% endif %}

---

**Source:** [github.com/danlex/council](https://github.com/danlex/council)
