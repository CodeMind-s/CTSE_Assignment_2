"""Member 1 — Coordinator agent + github_fetcher tool.

Three tiers (Lecture 9 — Unit Testing Dilemma):
    Tier 1: Property-based invariants — fast, deterministic, no LLM.
    Tier 2: LLM-as-a-Judge semantic checks — marked @pytest.mark.llm.
    Tier 3: Golden-dataset checks for the 5 member1-owned bugs.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from agents import coordinator
from tools.github_fetcher import fetch_github_issue
from tests.llm_judge import judge


# =============================================================================
# Tier 1 — Tool: github_fetcher (no network; validation-only properties)
# =============================================================================

class TestGithubFetcherInputValidation:
    """github_fetcher must fail gracefully on malformed input (Lec 9 pattern)."""

    @given(issue_number=st.integers(max_value=0))
    def test_non_positive_issue_returns_error(self, issue_number: int):
        result = fetch_github_issue(issue_number, "octocat/Hello-World")
        assert result["error"] is not None
        assert "positive" in result["error"].lower()

    @pytest.mark.parametrize("bad_repo", ["", "octocat", "a/b/c"])
    def test_malformed_repo_returns_error(self, bad_repo: str):
        result = fetch_github_issue(1, bad_repo)
        assert result["error"] is not None
        assert "owner/name" in result["error"]

    def test_error_shape_is_stable(self):
        """On error, all declared keys must still be present (TypedDict contract)."""
        r = fetch_github_issue(-1, "a/b")
        for key in ("title", "body", "labels", "state", "created_at", "error"):
            assert key in r


# =============================================================================
# Tier 1 — Agent: Coordinator invariants (LLM stubbed)
# =============================================================================

def _stub_llm(response_content: str):
    """Return a context manager that replaces core.llm.get_llm with a stub."""
    class _StubLLM:
        def invoke(self, messages):
            class _Msg:
                content = response_content
            return _Msg()
    return patch("agents.coordinator.get_llm", return_value=_StubLLM())


class TestCoordinatorInvariants:

    def test_iteration_count_increments(self, make_state):
        """AC: the failsafe counter must advance every coordinator pass."""
        state = make_state(raw_issue="App crashes on login.")
        with _stub_llm('{"is_valid_bug": true, "title": "Login crash", '
                       '"description": "Users cannot log in.", "tags": ["auth"]}'):
            update = coordinator.run(state)
        assert update["iteration_count"] == state["iteration_count"] + 1

    def test_tags_are_restricted_to_allowlist(self, make_state):
        """Unknown tags from the LLM must be filtered out."""
        state = make_state(raw_issue="anything")
        with _stub_llm('{"is_valid_bug": true, "title": "x", "description": "y", '
                       '"tags": ["auth", "nonsense", "UI", "ANOTHER"]}'):
            update = coordinator.run(state)
        # Allowed tags get lowercased; unknown tags dropped.
        assert set(update["tags"]) <= {"auth", "payment", "database", "api",
                                        "ui", "performance", "security", "mobile"}
        assert "auth" in update["tags"]
        assert "ui" in update["tags"]
        assert "nonsense" not in update["tags"]

    def test_malformed_json_falls_back_safely(self, make_state):
        """Non-JSON LLM output must not crash — errors recorded, state valid."""
        state = make_state(raw_issue="some bug")
        with _stub_llm("totally not json, just prose"):
            update = coordinator.run(state)
        # Should land in a safe-default state, not raise.
        assert update["is_valid_bug"] is False
        assert isinstance(update["title"], str)
        assert isinstance(update["tags"], list)
        assert update.get("errors"), "expected an error to be logged"

    def test_log_entry_is_emitted(self, make_state):
        state = make_state(raw_issue="App crashes")
        with _stub_llm('{"is_valid_bug": true, "title": "t", '
                       '"description": "d", "tags": []}'):
            update = coordinator.run(state)
        assert len(update["logs"]) == 1
        log = update["logs"][0]
        assert log["agent"] == "coordinator"
        assert "timestamp" in log
        assert "latency_ms" in log

    @given(raw=st.text(min_size=0, max_size=400))
    @settings(max_examples=25, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_never_raises_on_arbitrary_input(self, raw: str, empty_state):
        """Hypothesis invariant: coordinator.run must never raise."""
        state = dict(empty_state)
        state["raw_issue"] = raw
        with _stub_llm('{"is_valid_bug": false, "title": "", '
                       '"description": "", "tags": []}'):
            coordinator.run(state)  # must not raise


# =============================================================================
# Tier 2 — LLM-as-a-Judge (requires Ollama)
# =============================================================================

@pytest.mark.llm
class TestCoordinatorJudged:

    def test_judge_accepts_valid_bug_classification(self, make_state):
        state = make_state(raw_issue=(
            "All checkout attempts fail with 'card declined' even on valid cards. "
            "Revenue has been zero since 09:00 UTC this morning."
        ))
        update = coordinator.run(state)
        assert update["is_valid_bug"] is True, "clear outage must be flagged as a bug"
        verdict = judge(
            question=state["raw_issue"],
            answer=f"title={update['title']!r}, is_valid_bug={update['is_valid_bug']}, "
                   f"tags={update['tags']}",
            rubric=("The input describes a production payment outage. "
                    "A correct triage result must flag is_valid_bug=true and "
                    "produce a concise, on-topic title. Tags should include payment "
                    "or api. Score 4+ if those hold, 5 if the title is sharp."),
        )
        assert verdict["score"] >= 4, f"judge rejected: {verdict['reasoning']}"

    def test_judge_rejects_feature_request_as_bug(self, make_state):
        state = make_state(raw_issue=(
            "Please add a CSV export button to the Orders page. "
            "Would be nice to have alongside the filter bar."
        ))
        update = coordinator.run(state)
        # A correct agent should reject a feature-request as a bug.
        assert update["is_valid_bug"] is False, (
            "feature requests must be rejected at coordinator")


# =============================================================================
# Tier 3 — Golden dataset (member1-owned cases)
# =============================================================================

@pytest.mark.llm
class TestCoordinatorGolden:
    """Runs the coordinator on each of member1's 5 labelled bugs."""

    def test_member1_cases(self, golden_by_owner, make_state):
        cases = golden_by_owner["member1"]
        assert len(cases) == 5, "golden dataset should have 5 member1 cases"
        mismatches: list[str] = []
        for case in cases:
            state = make_state(raw_issue=f"{case['title']}\n\n{case['description']}")
            update = coordinator.run(state)
            is_real_bug = case["expected_severity"] is not None
            if update["is_valid_bug"] != is_real_bug:
                mismatches.append(
                    f"{case['id']}: expected is_valid_bug={is_real_bug}, "
                    f"got {update['is_valid_bug']}"
                )
        # Allow one flaky miss out of five (SLM tolerance).
        assert len(mismatches) <= 1, (
            "more than 1 coordinator misclassification on member1 golden set: "
            + "; ".join(mismatches)
        )
