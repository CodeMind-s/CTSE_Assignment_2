"""Member 4 — Delegator agent + developer_lookup tool."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from agents import delegator
from tools.developer_lookup import developer_lookup
from tests.llm_judge import judge


# =============================================================================
# Tier 1 — Tool: developer_lookup invariants
# =============================================================================

class TestDeveloperLookup:

    def test_returns_ranked_top_three(self):
        r = developer_lookup(["auth", "security"], "P0")
        assert r["error"] is None
        assert 1 <= len(r["candidates"]) <= 3
        scores = [c["match_score"] for c in r["candidates"]]
        assert scores == sorted(scores, reverse=True), "must be sorted by score desc"

    def test_rejects_empty_tags(self):
        r = developer_lookup([], "P0")
        assert r["error"] is not None
        assert r["candidates"] == []

    def test_rejects_invalid_severity(self):
        r = developer_lookup(["auth"], "URGENT")
        assert r["error"] is not None

    def test_missing_db_is_graceful(self, tmp_path: Path):
        r = developer_lookup(["auth"], "P0", db_path=str(tmp_path / "none.json"))
        assert r["error"] is not None
        assert r["candidates"] == []

    def test_corrupt_db_is_graceful(self, tmp_path: Path):
        bad = tmp_path / "broken.json"
        bad.write_text("{not json", encoding="utf-8")
        r = developer_lookup(["auth"], "P0", db_path=str(bad))
        assert r["error"] is not None

    def test_p0_gives_timezone_bonus(self, tmp_path: Path):
        """tz_bonus only fires for P0/P1 and only for in-business-hours devs."""
        db = tmp_path / "devs.json"
        db.write_text(json.dumps([
            {"name": "Awake", "expertise": ["api"], "current_workload": 0,
             "timezone": "Asia/Colombo", "in_business_hours": True},
            {"name": "Asleep", "expertise": ["api"], "current_workload": 0,
             "timezone": "US/Pacific", "in_business_hours": False},
        ]), encoding="utf-8")
        p0 = developer_lookup(["api"], "P0", db_path=str(db))
        p3 = developer_lookup(["api"], "P3", db_path=str(db))
        assert p0["candidates"][0]["name"] == "Awake"
        # At P3 the tz bonus evaporates — scores tie.
        assert p3["candidates"][0]["match_score"] == p3["candidates"][1]["match_score"]

    @given(severity=st.sampled_from(["P0", "P1", "P2", "P3"]))
    @settings(max_examples=10, deadline=None)
    def test_match_scores_are_finite(self, severity: str):
        r = developer_lookup(["api", "auth"], severity)
        for c in r["candidates"]:
            assert -1.0 <= c["match_score"] <= 1.1  # upper bound allows tz bonus


# =============================================================================
# Tier 1 — Agent: Delegator invariants (LLM stubbed)
# =============================================================================

def _stub_llm(response_content: str):
    class _StubLLM:
        def invoke(self, messages):
            class _Msg:
                content = response_content
            return _Msg()
    return patch("agents.delegator.get_llm", return_value=_StubLLM())


class TestDelegatorInvariants:

    def test_picks_top_candidate_when_llm_blanks(self, make_state):
        """If LLM omits assignee, agent falls back to developer_lookup top result."""
        state = make_state(title="Auth bug", tags=["auth"], severity="P0",
                           description="Users cannot log in")
        with _stub_llm('{"assignee": "", "assignee_reason": "", '
                       '"notification_message": ""}'):
            update = delegator.run(state)
        assert update["assignee"], "must fall back to a real candidate"
        assert update["notification_message"], "must build a fallback message"

    def test_notification_contains_severity_emoji_and_assignee(self, make_state):
        state = make_state(title="Payment outage", tags=["payment"], severity="P0",
                           description="Checkout broken",
                           repro_steps=["Open checkout.", "Submit card."])
        with _stub_llm('{"assignee": "Ben Silva", '
                       '"assignee_reason": "payment expert", '
                       '"notification_message": "🚨 *[P0] Payment outage*\\n'
                       'Assigned to: @Ben Silva\\nSLA: 2h\\nSummary: Checkout broken"}'):
            update = delegator.run(state)
        assert "🚨" in update["notification_message"]
        assert "Ben Silva" in update["notification_message"]
        assert "P0" in update["notification_message"]

    def test_fallback_message_when_emoji_missing(self, make_state):
        """Delegator must rebuild the message if the LLM skipped the emoji."""
        state = make_state(title="Payment outage", tags=["payment"], severity="P0",
                           description="Checkout broken",
                           repro_steps=["Open checkout."])
        with _stub_llm('{"assignee": "Ben Silva", '
                       '"assignee_reason": "payment expert", '
                       '"notification_message": "Payment outage is broken, assign Ben"}'):
            update = delegator.run(state)
        # Fallback must have kicked in — deterministic template always has the emoji.
        assert "🚨" in update["notification_message"]
        assert "Ben Silva" in update["notification_message"]

    def test_log_captures_tool_call(self, make_state):
        state = make_state(tags=["api"], severity="P2")
        with _stub_llm('{"assignee": "", "assignee_reason": "", '
                       '"notification_message": ""}'):
            update = delegator.run(state)
        log = update["logs"][0]
        assert log["agent"] == "delegator"
        assert log["tool_called"] == "developer_lookup"

    @given(severity=st.sampled_from(["P0", "P1", "P2", "P3"]))
    @settings(max_examples=8, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_never_raises(self, severity: str, empty_state):
        state = dict(empty_state)
        state["severity"] = severity
        state["tags"] = ["api"]
        state["title"] = "probe"
        state["description"] = "x"
        with _stub_llm('{"assignee": "X", "assignee_reason": "y", '
                       '"notification_message": "msg"}'):
            delegator.run(state)


# =============================================================================
# Tier 2 — LLM-as-a-Judge
# =============================================================================

@pytest.mark.llm
class TestDelegatorJudged:

    def test_judge_accepts_on_topic_assignment(self, make_state):
        state = make_state(
            title="Webhook signature verification accepts forged payloads",
            description=(
                "verify_webhook returns True for payloads signed with an empty "
                "secret. Attackers can trigger refunds without auth."
            ),
            tags=["payment", "security"],
            severity="P0",
            repro_steps=["Send a forged webhook.", "Observe refund processed."],
        )
        update = delegator.run(state)
        answer = (
            f"assignee={update['assignee']}\n"
            f"reason={update['assignee_reason']}\n"
            f"message={update['notification_message']}"
        )
        verdict = judge(
            question=f"{state['title']}\n{state['description']}",
            answer=answer,
            rubric=(
                "A correct assignment picks a developer with payment AND/OR "
                "security expertise. The notification must include a P0 emoji "
                "and an SLA. Score 4+ if both hold, 5 if the reasoning explicitly "
                "cites expertise match."
            ),
        )
        assert verdict["score"] >= 3, f"judge rejected: {verdict['reasoning']}"


# =============================================================================
# Tier 3 — Golden dataset (member4-owned cases)
# =============================================================================

@pytest.mark.llm
class TestDelegatorGolden:

    def test_member4_assignee_expertise_overlap(self, golden_by_owner, make_state):
        """Chosen assignee's expertise must overlap expected expertise set."""
        cases = [c for c in golden_by_owner["member4"]
                 if c["expected_assignee_expertise"]]
        devs = json.loads(
            (Path(__file__).resolve().parent.parent / "data" / "developers.json")
            .read_text(encoding="utf-8")
        )
        dev_expertise = {d["name"]: set(e.lower() for e in d["expertise"])
                         for d in devs}

        mismatches: list[str] = []
        for case in cases:
            state = make_state(
                title=case["title"],
                description=case["description"],
                tags=case["tags"],
                severity=case["expected_severity"] or "P2",
            )
            update = delegator.run(state)
            expected = {e.lower() for e in case["expected_assignee_expertise"]}
            got = dev_expertise.get(update["assignee"], set())
            if not (got & expected):
                mismatches.append(
                    f"{case['id']}: assigned {update['assignee']!r} "
                    f"with expertise {got} — expected overlap with {expected}"
                )
        # Allow one flaky miss.
        assert len(mismatches) <= 1, "; ".join(mismatches)
