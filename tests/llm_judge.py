"""LLM-as-a-Judge evaluator (Lecture 9).

A second pass of the same local SLM, given a stricter system prompt, is
used to score an agent's output on a 1-5 Likert scale. Keeping the judge
on the same model keeps the footprint small while still providing a
semantic-correctness signal that pure string assertions cannot.
"""
from __future__ import annotations

import json
from typing import TypedDict

from core.llm import get_llm
from agents._parsing import parse_json


JUDGE_SYSTEM_PROMPT = """You are a strict evaluation judge.
Given a question, an agent's answer, and a rubric, score the answer on a 1-5 scale.

RESPOND ONLY IN JSON:
{
  "score": int (1-5),
  "reasoning": string (one sentence)
}

Scoring guide:
5 = Excellent, fully correct, no issues
4 = Good, minor issues, acceptable
3 = Adequate but with real problems
2 = Poor, significant errors
1 = Incorrect or unsafe
"""


class Judgment(TypedDict):
    score: int
    reasoning: str


def judge(question: str, answer: str, rubric: str) -> Judgment:
    """Ask the local judge LLM to score an answer against a rubric.

    Args:
        question: The original task posed to the agent under test.
        answer:   The agent's answer (or a compact summary of it).
        rubric:   Natural-language success criteria.

    Returns:
        Judgment with an int ``score`` in 1-5 and one-sentence ``reasoning``.
        Returns ``{"score": 0, "reasoning": ...}`` if the judge output
        cannot be parsed — tests should treat 0 as a hard failure.
    """
    llm = get_llm(temperature=0.0)
    prompt = (
        f"QUESTION:\n{question}\n\n"
        f"ANSWER:\n{answer}\n\n"
        f"RUBRIC:\n{rubric}"
    )
    try:
        response = llm.invoke([
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        return {"score": 0, "reasoning": f"Judge LLM invocation failed: {e}"}

    text = getattr(response, "content", str(response))
    parsed = parse_json(text)
    if not parsed or "score" not in parsed:
        return {"score": 0, "reasoning": f"Judge returned malformed output: {text[:200]}"}

    try:
        score = int(parsed["score"])
    except (TypeError, ValueError):
        return {"score": 0, "reasoning": f"Judge score not an int: {parsed.get('score')!r}"}
    score = max(0, min(5, score))
    reasoning = str(parsed.get("reasoning", ""))[:500]
    return {"score": score, "reasoning": reasoning}
