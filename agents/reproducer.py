"""Reproducer agent — pristine repro steps + related-files lookup.

Persona: QA Engineer. Extracts high-signal keywords from the bug, runs the
codebase searcher to ground related files, then asks the LLM to produce
numbered steps and an expected/actual contrast.
"""
import re
import time

from core.llm import get_llm
from core.logger import build_log_entry
from core.state import TriageState
from tools.codebase_searcher import codebase_searcher

from ._parsing import parse_json


SYSTEM_PROMPT = """You are a QA Engineer who writes pristine bug reproduction steps.
Your reproduction steps must be executable by any engineer without prior context.

PROCESS:
1. Read the bug title and description carefully.
2. Call the codebase_searcher tool with relevant keywords from the description
   to find related source files.
3. Generate numbered reproduction steps (3-6 steps typical).
4. Clearly state expected vs actual behavior.

CONSTRAINTS:
- Each step starts with an imperative verb (Click, Navigate, Enter, Submit...).
- Avoid assumptions about environment — state prerequisites explicitly.
- If critical information is missing, list it under "missing_info" in the JSON.

OUTPUT (JSON only):
{
  "repro_steps": [string],
  "expected_behavior": string,
  "actual_behavior": string,
  "related_files": [string],
  "missing_info": [string]
}"""


_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "when",
    "then", "than", "what", "which", "have", "been", "will", "they", "them",
    "their", "there", "here", "user", "users", "page", "issue", "bug",
    "fail", "fails", "failed", "error", "errors", "some", "only", "after",
    "before", "while", "also", "very", "every", "should", "would", "could",
    "does", "doesn", "isn", "wasn", "tried", "makes",
}


def _extract_keywords(text: str, k: int = 3) -> list[str]:
    words = re.findall(r"[A-Za-z_]{4,}", text.lower())
    out: list[str] = []
    for w in words:
        if w in _STOPWORDS or w in out:
            continue
        out.append(w)
        if len(out) >= k:
            break
    return out


def run(state: TriageState) -> dict:
    start = time.time()
    title = state.get("title", "") or ""
    description = state.get("description") or state.get("raw_issue") or ""
    text = f"{title} {description}".strip()

    keywords = _extract_keywords(text, k=3)
    discovered_files: list[str] = []
    tool_outputs: list[dict] = []
    for kw in keywords:
        result = codebase_searcher(kw)
        tool_outputs.append({"keyword": kw, "result": result})
        for m in result.get("matches", []):
            f = m.get("file")
            if f and f not in discovered_files:
                discovered_files.append(f)

    user_message = (
        f"Bug title: {title}\n"
        f"Bug description: {description}\n\n"
        f"Codebase searcher matched files (keywords={keywords}):\n"
        f"  {discovered_files or '(no matches)'}\n\n"
        "Produce the reproduction-steps JSON now."
    )

    response_text = ""
    parsed: dict | None = None
    errors: list[str] = []
    try:
        llm = get_llm()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
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
        errors.append(f"reproducer LLM call failed: {e}")

    if parsed is None:
        parsed = {}
        errors.append("reproducer: failed to parse JSON; using safe defaults")

    raw_steps = parsed.get("repro_steps")
    if isinstance(raw_steps, list) and raw_steps:
        repro_steps = [str(s) for s in raw_steps]
    else:
        repro_steps = [
            "Reproduce the scenario described in the bug report.",
            "Observe the actual outcome and compare against the expected behavior.",
        ]

    expected_behavior = str(parsed.get("expected_behavior", ""))[:1000]
    actual_behavior = str(parsed.get("actual_behavior", ""))[:1000]

    raw_files = parsed.get("related_files")
    related: list[str] = []
    if isinstance(raw_files, list):
        for f in raw_files:
            if isinstance(f, str) and f and f not in related:
                related.append(f)
    for f in discovered_files:
        if f not in related:
            related.append(f)

    latency_ms = int((time.time() - start) * 1000)
    log = build_log_entry(
        agent="reproducer",
        system_prompt=SYSTEM_PROMPT,
        user_input=user_message,
        llm_output=response_text,
        tool_called="codebase_searcher",
        tool_output=tool_outputs,
        latency_ms=latency_ms,
    )

    update: dict = {
        "repro_steps": repro_steps,
        "expected_behavior": expected_behavior,
        "actual_behavior": actual_behavior,
        "related_files": related,
        "logs": [log],
    }
    if errors:
        update["errors"] = errors
    return update
