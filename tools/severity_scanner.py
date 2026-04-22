"""Rule-based severity keyword scanner."""
import re
from typing import TypedDict


class ScanResult(TypedDict):
    suggested_severity: str
    matched_keywords: dict[str, list[str]]
    confidence: float
    error: str | None


SEVERITY_RULES: dict[str, list[str]] = {
    "P0": [
        r"\bcrash(es|ed|ing)?\b",
        r"\bdata\s+loss\b",
        r"\bsecurity\s+(breach|vulnerability|leak)\b",
        r"\bpayment\s+(fail|broken|error)",
        r"\bproduction\s+down\b",
        r"\bcannot\s+log\s*in\b",
        r"\bauthentication\s+fail",
        r"\bdatabase\s+corrupt",
    ],
    "P1": [
        r"\bbroken\b",
        r"\bfailure\b",
        r"\bnot\s+working\b",
        r"\berror\s+500\b",
        r"\btimeout\b",
        r"\bno\s+workaround\b",
    ],
    "P2": [
        r"\bslow\b",
        r"\blag(gy|ging)?\b",
        r"\bsometimes\b",
        r"\bintermittent\b",
        r"\bworkaround\b",
    ],
    "P3": [
        r"\btypo\b",
        r"\bcosmetic\b",
        r"\bmisaligned\b",
        r"\bcolor\b",
        r"\bpadding\b",
        r"\bnit\b",
    ],
}


def keyword_severity_scanner(text: str) -> ScanResult:
    """Scan bug description for severity-indicating keywords.

    Uses a priority-ordered rule engine (P0 checked first). The highest-priority
    match wins for the suggested severity. Confidence is computed from match density
    (number of matches / text length in words).

    Args:
        text: The bug description to scan. Must be a non-empty string.

    Returns:
        ScanResult dict with:
            suggested_severity: One of 'P0', 'P1', 'P2', 'P3'
            matched_keywords: Dict mapping severity level to matched regex patterns
            confidence: Float 0.0-1.0
            error: None on success, error string on failure

    Raises:
        Never raises — all failures are returned as error dicts.

    Example:
        >>> keyword_severity_scanner("App crashes on login for all users")
        {'suggested_severity': 'P0', 'matched_keywords': {'P0': ['crash...']}, ...}
    """
    if not isinstance(text, str) or not text.strip():
        return {
            "suggested_severity": "P3",
            "matched_keywords": {},
            "confidence": 0.0,
            "error": "Input text is empty or not a string. "
                     "Provide a bug description as plain text.",
        }

    text_lower = text.lower()
    matched: dict[str, list[str]] = {}
    for level, patterns in SEVERITY_RULES.items():
        hits = [p for p in patterns if re.search(p, text_lower)]
        if hits:
            matched[level] = hits

    for level in ("P0", "P1", "P2", "P3"):
        if level in matched:
            suggested = level
            break
    else:
        suggested = "P3"

    total_hits = sum(len(v) for v in matched.values())
    word_count = max(len(text.split()), 1)
    confidence = min(1.0, total_hits / max(word_count / 20, 1))

    return {
        "suggested_severity": suggested,
        "matched_keywords": matched,
        "confidence": round(confidence, 2),
        "error": None,
    }
