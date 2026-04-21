"""Delegator agent — assignment + Slack-formatted notification.

Persona: Team Lead. Asks the developer-lookup tool for ranked candidates,
lets the LLM pick + draft the message, and falls back to a deterministic
template if the LLM output is missing the required emoji/title/assignee.
"""
import time

from core.llm import get_llm
from core.logger import build_log_entry
from core.state import TriageState
from tools.developer_lookup import developer_lookup

from ._parsing import parse_json


SYSTEM_PROMPT = """You are a Team Lead managing a 6-person engineering squad.
Your job is to assign bugs to the right developer AND draft the notification message.

PROCESS:
1. Call the developer_lookup tool with the bug's tags and severity.
2. The tool returns ranked candidates. Pick the best one based on:
   - Expertise match (primary)
   - Current workload (secondary — prefer lower)
   - Timezone overlap for P0/P1 (tertiary)
3. Draft a Slack-formatted notification message that includes:
   - Severity badge (emoji)
   - Title
   - Summary
   - Repro steps (numbered)
   - Assigned developer mention
   - SLA based on severity

OUTPUT (JSON only):
{
  "assignee": string,
  "assignee_reason": string,
  "notification_message": string
}

SLA map: P0=2h, P1=24h, P2=3 days, P3=next sprint."""


SEVERITY_EMOJI: dict[str, str] = {"P0": "🚨", "P1": "🔴", "P2": "🟡", "P3": "🔵"}
SEVERITY_SLA: dict[str, str] = {"P0": "2h", "P1": "24h",
                                "P2": "3 days", "P3": "next sprint"}


def _build_fallback_message(severity: str, title: str, assignee: str,
                            description: str, repro_steps: list[str]) -> str:
    emoji = SEVERITY_EMOJI.get(severity, "🔔")
    sla = SEVERITY_SLA.get(severity, "TBD")
    handle = f"@{assignee}" if assignee else "@unassigned"
    steps_block = (
        "\n".join(f"{i}. {s}" for i, s in enumerate(repro_steps, 1))
        if repro_steps else "(no steps yet)"
    )
    return (
        f"{emoji} *[{severity}] {title}*\n"
        f"Assigned to: {handle}\n"
        f"SLA: {sla}\n\n"
        f"Summary: {description}\n\n"
        f"Repro steps:\n{steps_block}"
    )


def run(state: TriageState) -> dict:
    start = time.time()
    tags = state.get("tags") or []
    severity = state.get("severity") or "P3"
    title = state.get("title") or "(untitled)"
    description = state.get("description") or ""
    repro_steps = state.get("repro_steps") or []

    lookup = developer_lookup(tags or ["api"], severity)
    candidates = lookup.get("candidates", [])

    user_message = (
        f"Bug title: {title}\n"
        f"Severity: {severity}\n"
        f"Tags: {tags}\n"
        f"Summary: {description}\n"
        f"Reproduction steps: {repro_steps}\n\n"
        f"Ranked candidates from developer_lookup:\n{candidates}\n\n"
        "Pick the best assignee and draft the Slack notification. JSON only."
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
        errors.append(f"delegator LLM call failed: {e}")

    if parsed is None:
        parsed = {}
        errors.append("delegator: failed to parse JSON; using top candidate fallback")

    assignee = parsed.get("assignee")
    if not isinstance(assignee, str) or not assignee.strip():
        assignee = candidates[0]["name"] if candidates else "unassigned"

    assignee_reason = parsed.get("assignee_reason")
    if not isinstance(assignee_reason, str) or not assignee_reason.strip():
        if candidates:
            top = candidates[0]
            assignee_reason = (
                f"Top expertise match for tags {tags} with workload "
                f"{top.get('current_workload', '?')} (score {top.get('match_score')})."
            )
        else:
            assignee_reason = "No matching candidates; assigned to triage queue."

    notification_message = parsed.get("notification_message")
    emoji = SEVERITY_EMOJI.get(severity, "🔔")
    needs_fallback = (
        not isinstance(notification_message, str)
        or not notification_message.strip()
        or emoji not in notification_message
        or title not in notification_message
        or assignee not in notification_message
    )
    if needs_fallback:
        notification_message = _build_fallback_message(
            severity, title, assignee, description, repro_steps
        )

    latency_ms = int((time.time() - start) * 1000)
    log = build_log_entry(
        agent="delegator",
        system_prompt=SYSTEM_PROMPT,
        user_input=user_message,
        llm_output=response_text,
        tool_called="developer_lookup",
        tool_output=lookup,
        latency_ms=latency_ms,
    )

    update: dict = {
        "assignee": assignee,
        "assignee_reason": assignee_reason,
        "notification_message": notification_message,
        "logs": [log],
    }
    if errors:
        update["errors"] = errors
    return update
