"""Prompt templates for the 3-stage council pipeline."""

SOUL_PREAMBLE = """{soul}

---

"""

STAGE1_RESPONSE = """You are one member of a council of AI experts being asked to answer a complex question. Provide your best, most thorough answer.

Be specific, cite evidence where possible, and flag any areas of uncertainty. Do not hedge excessively — give your genuine assessment.

{soul_section}Question:
{question}"""


STAGE2_REVIEW = """You are a peer reviewer in a council of AI experts. Below are anonymized responses from other council members to the same question.

Your task:
1. Rate each response on these criteria (1-10 scale):
{rubric_items}
2. Identify the strongest and weakest response, with specific reasons.
3. Flag any factual errors, logical gaps, or blind spots you notice.
4. Note where responses DISAGREE — these disagreements are valuable signal, not noise.

IMPORTANT: Responses are anonymized. Judge ONLY by content quality, not by writing style.

Original question:
{question}

---

{anonymized_responses}

---

Provide your review in this format:

## Ratings
For each agent, rate on each criterion (1-10):
{rating_template}

## Strongest Response
[Which agent and why]

## Weakest Response
[Which agent and why]

## Factual Errors or Gaps
[List any errors found in any response]

## Key Disagreements
[Where do the responses conflict? Which side has stronger evidence?]"""


STAGE3_SYNTHESIS = """You are the Chairman of a council of AI experts. Your job is to synthesize the best possible answer from multiple expert responses and their peer reviews.

CRITICAL RULES:
1. DO NOT simply average opinions or find the middle ground — that is a bias trap.
2. Weight responses by the QUALITY OF REASONING, not by consensus. A well-reasoned minority opinion beats a poorly-reasoned majority.
3. PRESERVE DISSENT: If experts genuinely disagree, present both sides with their evidence. Do not paper over real disagreements.
4. Flag your confidence level for each major claim (High/Medium/Low).
5. Clearly mark which parts of your answer are consensus vs. contested.

Original question:
{question}

---

## Expert Responses:
{anonymized_responses}

---

## Peer Reviews:
{reviews}

---

Now synthesize the council's best answer. Structure your response as:

## Council Answer
[The synthesized answer, incorporating the strongest reasoning from all experts]

## Confidence Assessment
[For each major claim: High/Medium/Low confidence and why]

## Points of Consensus
[Where all or most experts agreed, with reasoning]

## Points of Dissent
[Where experts disagreed — present BOTH sides with their evidence. Do NOT resolve disagreements by averaging — let the user see the genuine tension]

## Blind Spots & Caveats
[What the council might be missing. What further investigation would help.]"""


def format_rubric_items(rubric: list[str]) -> str:
    return "\n".join(f"   - **{item.title()}**: [1-10]" for item in rubric)


def format_anonymized_responses(responses: list[dict], include_names: bool = False) -> str:
    """Format responses with anonymized agent labels.

    Args:
        responses: list of {"agent_id": str, "agent_name": str, "response": str}
        include_names: if True, show real names (for final display only)
    """
    parts = []
    for i, r in enumerate(responses):
        label = r["agent_name"] if include_names else f"Agent {i + 1}"
        parts.append(f"### {label}\n\n{r['response']}")
    return "\n\n---\n\n".join(parts)


def format_rating_template(num_agents: int, rubric: list[str]) -> str:
    lines = []
    for i in range(num_agents):
        lines.append(f"### Agent {i + 1}")
        for item in rubric:
            lines.append(f"- {item.title()}: ?/10")
        lines.append("")
    return "\n".join(lines)


def _soul_section(soul: str) -> str:
    if soul:
        return SOUL_PREAMBLE.format(soul=soul)
    return ""


def build_stage1_prompt(question: str, soul: str = "") -> str:
    return STAGE1_RESPONSE.format(question=question, soul_section=_soul_section(soul))


def build_stage2_prompt(
    question: str,
    responses: list[dict],
    rubric: list[str],
) -> str:
    return STAGE2_REVIEW.format(
        question=question,
        rubric_items=format_rubric_items(rubric),
        anonymized_responses=format_anonymized_responses(responses),
        rating_template=format_rating_template(len(responses), rubric),
    )


def build_stage3_prompt(
    question: str,
    responses: list[dict],
    reviews: list[dict],
    preserve_dissent: bool = True,
) -> str:
    formatted_reviews = []
    for i, rev in enumerate(reviews):
        label = f"Reviewer {i + 1}"
        formatted_reviews.append(f"### {label}\n\n{rev['response']}")

    return STAGE3_SYNTHESIS.format(
        question=question,
        anonymized_responses=format_anonymized_responses(responses),
        reviews="\n\n---\n\n".join(formatted_reviews),
    )
