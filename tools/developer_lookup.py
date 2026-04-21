"""Developer database query tool."""
import json
from pathlib import Path
from typing import TypedDict


class DeveloperMatch(TypedDict):
    name: str
    expertise: list[str]
    current_workload: int
    timezone: str
    match_score: float


class LookupResult(TypedDict):
    candidates: list[DeveloperMatch]
    error: str | None


def developer_lookup(
    tags: list[str],
    severity: str,
    db_path: str = "data/developers.json",
) -> LookupResult:
    """Rank developers by expertise match, workload, and timezone.

    Scoring:
        match_score = (tag_overlap * 0.7) - (workload_pct * 0.2) + (tz_bonus * 0.1)
    Where:
        tag_overlap = |dev.expertise ∩ tags| / |tags|
        workload_pct = dev.current_workload / 10  (cap at 1.0)
        tz_bonus = 1.0 if severity in ['P0','P1'] and dev in business hours else 0

    Args:
        tags: Bug tags (e.g., ['auth', 'security']).
        severity: 'P0' | 'P1' | 'P2' | 'P3'.
        db_path: Path to JSON developer database.

    Returns:
        LookupResult with ranked candidates (best first, top 3).
        On failure, candidates=[] and error is set.

    Raises:
        Never raises — all failures are returned as error dicts.

    Example:
        >>> developer_lookup(['auth'], 'P0')
        {'candidates': [{'name': 'Ada', 'match_score': 0.85, ...}], ...}
    """
    if not isinstance(tags, list) or not tags:
        return {"candidates": [],
                "error": "tags must be a non-empty list of strings."}

    if severity not in {"P0", "P1", "P2", "P3"}:
        return {"candidates": [],
                "error": f"severity must be P0/P1/P2/P3, got '{severity}'."}

    path = Path(db_path)
    if not path.exists():
        return {"candidates": [],
                "error": f"Developer database not found at {db_path}."}

    try:
        devs = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return {"candidates": [],
                "error": f"Developer DB is not valid JSON: {e}"}

    tags_set = {t.lower() for t in tags}
    ranked: list[DeveloperMatch] = []
    for dev in devs:
        expertise = {e.lower() for e in dev.get("expertise", [])}
        overlap = len(expertise & tags_set) / max(len(tags_set), 1)
        workload_pct = min(dev.get("current_workload", 0) / 10, 1.0)
        tz_bonus = 0.0
        if severity in {"P0", "P1"} and dev.get("in_business_hours", False):
            tz_bonus = 1.0
        score = (overlap * 0.7) - (workload_pct * 0.2) + (tz_bonus * 0.1)

        ranked.append({
            "name": dev["name"],
            "expertise": dev.get("expertise", []),
            "current_workload": dev.get("current_workload", 0),
            "timezone": dev.get("timezone", "UTC"),
            "match_score": round(score, 3),
        })

    ranked.sort(key=lambda d: d["match_score"], reverse=True)
    return {"candidates": ranked[:3], "error": None}
