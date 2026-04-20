"""Coordinator agent — triage lead.

Persona: Senior Engineering Manager. Decides if an inbound report is a real
bug, then extracts a clean title, description, and tag set. Optionally pulls
the issue body from the public GitHub API when an issue number is provided.
"""
import time

from core.llm import get_llm
from core.logger import build_log_entry
from core.state import TriageState
from tools.github_fetcher import fetch_github_issue

from ._parsing import parse_json


SYSTEM_PROMPT = """You are a Senior Engineering Manager running triage for a software team.
Your job is to read incoming bug reports and determine:
1. Is this actually a bug (not a feature request, question, or duplicate)?
2. What is the concise title (max 80 chars)?
3. What is the core description (2-4 sentences)?
4. What tags apply? Choose from: ["auth", "payment", "database", "api", "ui", "performance", "security", "mobile"]

CONSTRAINTS:
- Respond ONLY in valid JSON matching this schema:
{
  "is_valid_bug": boolean,
  "title": string,
  "description": string,
  "tags": string[]
}
- Do not add explanations outside the JSON.
- If the report is too vague to classify, set is_valid_bug=false and explain in description.

You MUST call the fetch_github_issue tool if the input contains an issue number
reference (e.g., "#123" or "issue 456"). Otherwise work with the raw text provided."""


_ALLOWED_TAGS = {"auth", "payment", "database", "api", "ui",
                 "performance", "security", "mobile"}


def run(state: TriageState) -> dict:
    start = time.time()
    raw = state.get("raw_issue", "") or ""
    tool_called: str | None = None
    tool_output = None
    errors: list[str] = []

    if state.get("issue_number") and state.get("repo"):
        tool_called = "fetch_github_issue"
        tool_output = fetch_github_issue(state["issue_number"], state["repo"])
        if tool_output and not tool_output.get("error"):
            raw = f"{tool_output['title']}\n\n{tool_output['body']}"

    response_text = ""
    parsed: dict | None = None
    try:
        llm = get_llm()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw},
        ]
        response = llm.invoke(messages)
        response_text = getattr(response, "content", str(response))
        parsed = parse_json(response_text)
        if parsed is None:
            messages.append({"role": "user",
                             "content": "Return ONLY valid JSON matching the schema. No prose."})
            response = llm.invoke(messages)
            response_text = getattr(response, "content", str(response))
            parsed = parse_json(response_text)
    except Exception as e:
        errors.append(f"coordinator LLM call failed: {e}")

    if parsed is None:
        parsed = {}
        errors.append("coordinator: failed to parse JSON; using safe defaults")

    is_valid_bug = bool(parsed.get("is_valid_bug", False))
    title = str(parsed.get("title", ""))[:200]
    description = str(parsed.get("description", raw))[:2000]
    raw_tags = parsed.get("tags") or []
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if isinstance(t, str) and t.lower() in _ALLOWED_TAGS and t.lower() not in tags:
                tags.append(t.lower())

    latency_ms = int((time.time() - start) * 1000)
    log = build_log_entry(
        agent="coordinator",
        system_prompt=SYSTEM_PROMPT,
        user_input=raw,
        llm_output=response_text,
        tool_called=tool_called,
        tool_output=tool_output,
        latency_ms=latency_ms,
    )

    update: dict = {
        "is_valid_bug": is_valid_bug,
        "title": title,
        "description": description,
        "tags": tags,
        "iteration_count": state.get("iteration_count", 0) + 1,
        "logs": [log],
    }
    if errors:
        update["errors"] = errors
    return update
