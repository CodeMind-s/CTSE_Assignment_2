"""Member 2 — Classifier agent + severity_scanner tool."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from agents import classifier
from tools.severity_scanner import keyword_severity_scanner
from tests.llm_judge import judge


SEVERITIES = {"P0", "P1", "P2", "P3"}


# =============================================================================
# Tier 1 — Tool: severity_scanner invariants
# =============================================================================

class TestSeverityScannerProperties:

    @given(text=st.text(min_size=1, max_size=300))
    @settings(max_examples=50, deadline=None)
    def test_suggested_severity_always_valid(self, text: str):
        """Invariant: the scanner must always suggest one of P0-P3."""
        result = keyword_severity_scanner(text)
        assert result["suggested_severity"] in SEVERITIES
        assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.parametrize("text,expected", [
        ("App crashes on login for all iOS users", "P0"),
        ("Payment fail on every checkout", "P0"),
        ("API returns error 500 on the orders endpoint", "P1"),
        ("Search feels a bit slow sometimes", "P2"),
        ("Cosmetic typo in the billing tooltip", "P3"),
    ])
    def test_known_phrases_map_to_expected(self, text: str, expected: str):
        result = keyword_severity_scanner(text)
        assert result["suggested_severity"] == expected

    def test_empty_input_is_graceful(self):
        result = keyword_severity_scanner("")
        assert result["error"] is not None
        assert result["suggested_severity"] == "P3"

    def test_p0_wins_over_p1_when_both_present(self):
        """Priority: P0 matches take precedence over lower tiers."""
        result = keyword_severity_scanner("Payment fail and the API also timeout")
        assert result["suggested_severity"] == "P0"

    @given(text=st.integers())
    def test_non_string_input_never_raises(self, text):
        """Hypothesis invariant: even garbage input returns a dict."""
        result = keyword_severity_scanner(text)  # type: ignore[arg-type]
        assert "error" in result


# =============================================================================
# Tier 1 — Agent: Classifier invariants (LLM stubbed)
# =============================================================================

def _stub_llm(response_content: str):
    class _StubLLM:
        def invoke(self, messages):
            class _Msg:
                content = response_content
            return _Msg()
    return patch("agents.classifier.get_llm", return_value=_StubLLM())


class TestClassifierInvariants:

    def test_output_severity_always_valid(self, make_state):
        state = make_state(description="Users cannot log in — auth is broken.")
        with _stub_llm('{"severity": "P1", "severity_evidence": ["login broken"], '
                       '"severity_confidence": 0.8}'):
            update = classifier.run(state)
        assert update["severity"] in SEVERITIES

    def test_invalid_llm_severity_falls_back_to_scanner(self, make_state):
        """AC4 safe-default: if LLM returns garbage, scanner suggestion wins."""
        state = make_state(description="App crashes on every login attempt.")
        with _stub_llm('{"severity": "URGENT!!!", "severity_evidence": [], '
                       '"severity_confidence": 0.5}'):
            update = classifier.run(state)
        assert update["severity"] in SEVERITIES
        assert update["severity"] == "P0", (
            "scanner sees 'crashes' → P0; classifier must honour that fallback")
        assert update.get("errors"), "invalid severity should log an error"

    def test_confidence_is_clamped(self, make_state):
        state = make_state(description="Cosmetic typo")
        with _stub_llm('{"severity": "P3", "severity_evidence": ["typo"], '
                       '"severity_confidence": 99.0}'):
            update = classifier.run(state)
        assert 0.0 <= update["severity_confidence"] <= 1.0

    def test_log_captures_tool_call(self, make_state):
        state = make_state(description="Payment fails")
        with _stub_llm('{"severity": "P0", "severity_evidence": ["payment"], '
                       '"severity_confidence": 0.9}'):
            update = classifier.run(state)
        log = update["logs"][0]
        assert log["agent"] == "classifier"
        assert log["tool_called"] == "keyword_severity_scanner"

    @given(desc=st.text(min_size=0, max_size=300))
    @settings(max_examples=15, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_never_raises(self, desc: str, empty_state):
        state = dict(empty_state)
        state["description"] = desc
        with _stub_llm('{"severity": "P3", "severity_evidence": [], '
                       '"severity_confidence": 0.1}'):
            update = classifier.run(state)
        assert update["severity"] in SEVERITIES


# =============================================================================
# Tier 2 — LLM-as-a-Judge
# =============================================================================

@pytest.mark.llm
class TestClassifierJudged:

    def test_judge_agrees_on_critical_outage(self, make_state):
        state = make_state(description=(
            "Production checkout is completely down. Every transaction returns "
            "'card declined' even on valid cards. Revenue is zero."
        ))
        update = classifier.run(state)
        assert update["severity"] == "P0", "clear production outage must be P0"
        verdict = judge(
            question=state["description"],
            answer=f"severity={update['severity']}, "
                   f"evidence={update['severity_evidence']}",
            rubric=("A production-wide payment outage is a textbook P0. "
                    "Score 5 if severity is P0 and evidence is on-topic, "
                    "1 if severity is anything else."),
        )
        assert verdict["score"] >= 4, f"judge rejected: {verdict['reasoning']}"


# =============================================================================
# Tier 3 — Golden dataset (member2 + cross-member sanity)
# =============================================================================

@pytest.mark.llm
class TestClassifierGolden:

    def test_member2_cases_within_one_tier(self, golden_by_owner, make_state):
        """Allow off-by-one on SLM noise; hard-fail on 2+ tier miss."""
        cases = [c for c in golden_by_owner["member2"]
                 if c["expected_severity"] is not None]
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        mismatches: list[str] = []
        for case in cases:
            state = make_state(
                title=case["title"],
                description=case["description"],
                tags=case["tags"],
            )
            update = classifier.run(state)
            got = update["severity"]
            exp = case["expected_severity"]
            if abs(order[got] - order[exp]) > 1:
                mismatches.append(f"{case['id']}: expected {exp}, got {got}")
        assert not mismatches, (
            "classifier off by more than one tier on: " + "; ".join(mismatches)
        )
