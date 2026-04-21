"""Classifier agent — severity assignment.

Persona: Site Reliability Engineer. Combines the deterministic keyword
scanner's evidence with LLM judgment to settle on a P0–P3 label.
"""
import time

from core.llm import get_llm
from core.logger import build_log_entry
from core.state import TriageState
from tools.severity_scanner import keyword_severity_scanner

from ._parsing import parse_json


SYSTEM_PROMPT = """You are a Site Reliability Engineer specializing in incident severity.
Classify bugs on this strict scale:

- P0 (Critical): Production down, data loss, security breach, payment failures.
- P1 (High): Major feature broken for most users, no workaround.
- P2 (Medium): Feature broken for some users OR workaround exists.
- P3 (Low): Cosmetic, minor UX issues, edge cases.

PROCESS:
1. Call the severity_scanner tool with the bug description to get keyword evidence.
2. Use the tool's evidence PLUS your reasoning to finalize severity.
3. Your final severity may differ from the tool's suggestion if context warrants it.

OUTPUT (JSON only):
{
  "severity": "P0" | "P1" | "P2" | "P3",
  "severity_evidence": [string],
  "severity_confidence": float (0.0-1.0)
}

Do NOT output anything outside this JSON."""


_ALLOWED_SEVERITY = {"P0", "P1", "P2", "P3"}


def run(state: TriageState) -> dict:
    start = time.time()
    description = state.get("description") or state.get("raw_issue") or ""

    scan_result = keyword_severity_scanner(description)

    user_message = (
        f"Bug description:\n{description}\n\n"
        f"Severity scanner output:\n"
        f"  suggested_severity: {scan_result['suggested_severity']}\n"
        f"  matched_keywords:   {scan_result['matched_keywords']}\n"
        f"  scanner_confidence: {scan_result['confidence']}\n\n"
        "Use this evidence + your judgment to produce the final severity JSON."
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
        errors.append(f"classifier LLM call failed: {e}")

    if parsed is None:
        parsed = {}

    severity = parsed.get("severity")
    if severity not in _ALLOWED_SEVERITY:
        # AC4 safe-default: scanner always returns one of P0-P3.
        fallback = scan_result.get("suggested_severity")
        severity = fallback if fallback in _ALLOWED_SEVERITY else "P3"
        errors.append(
            f"classifier: invalid severity {parsed.get('severity')!r}; "
            f"fell back to scanner suggestion {severity}"
        )

    raw_evidence = parsed.get("severity_evidence")
    if isinstance(raw_evidence, list):
        evidence = [str(x) for x in raw_evidence]
    elif isinstance(raw_evidence, str) and raw_evidence:
        evidence = [raw_evidence]
    else:
        evidence = [f"scanner_keywords={scan_result.get('matched_keywords')}"]

    try:
        confidence = float(parsed.get("severity_confidence",
                                      scan_result.get("confidence", 0.0)))
    except (TypeError, ValueError):
        confidence = float(scan_result.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    latency_ms = int((time.time() - start) * 1000)
    log = build_log_entry(
        agent="classifier",
        system_prompt=SYSTEM_PROMPT,
        user_input=description,
        llm_output=response_text,
        tool_called="keyword_severity_scanner",
        tool_output=scan_result,
        latency_ms=latency_ms,
    )

    update: dict = {
        "severity": severity,
        "severity_evidence": evidence,
        "severity_confidence": round(confidence, 2),
        "logs": [log],
    }
    if errors:
        update["errors"] = errors
    return update
