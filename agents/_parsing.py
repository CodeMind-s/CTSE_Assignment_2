"""Tolerant JSON extraction shared by all agents.

LLMs frequently wrap JSON in ```json fences or trail with prose; this
helper strips both and falls back to scanning for the first {...} block.
"""
import json
import re


def parse_json(text: str) -> dict | None:
    """Return the first JSON object found in `text`, or None."""
    if not text:
        return None
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try:
            out = json.loads(m.group(0))
            return out if isinstance(out, dict) else None
        except json.JSONDecodeError:
            return None
    return None
