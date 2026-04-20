"""Shared pytest fixtures and markers for the triage test harness.

Run modes
---------
- Fast (default): ``pytest -m "not llm and not integration"``
  Only deterministic property-based tests + tool unit tests — no Ollama required.

- Full: ``pytest`` (default)
  Includes the LLM-as-a-Judge tests and the golden-dataset end-to-end run.
  Requires ``ollama serve`` running with the configured model pulled.

The ``llm`` marker skips automatically when Ollama is unreachable so CI on a
machine without the model still returns green on the deterministic tier.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest


ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = ROOT / "data" / "golden_dataset.json"


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "llm: test requires a live Ollama server (skipped if unreachable).",
    )
    config.addinivalue_line(
        "markers",
        "integration: end-to-end test that runs the full LangGraph pipeline.",
    )


def _ollama_reachable() -> bool:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    parsed = urlparse(base)
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip llm-marked tests when Ollama is not reachable."""
    if _ollama_reachable():
        return
    skip_llm = pytest.mark.skip(reason="Ollama server not reachable on OLLAMA_BASE_URL")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip_llm)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def golden_dataset() -> list[dict[str, Any]]:
    """The full 20-bug labelled dataset from data/golden_dataset.json."""
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def golden_by_owner(golden_dataset: list[dict]) -> dict[str, list[dict]]:
    """Dataset grouped by team-member owner (member1..member4)."""
    buckets: dict[str, list[dict]] = {}
    for case in golden_dataset:
        buckets.setdefault(case["owner"], []).append(case)
    return buckets


@pytest.fixture
def empty_state() -> dict:
    """A zero-valued TriageState dict suitable for unit-testing a single agent."""
    return {
        "raw_issue": "",
        "issue_number": None,
        "repo": None,
        "is_valid_bug": False,
        "title": "",
        "description": "",
        "tags": [],
        "severity": None,
        "severity_evidence": [],
        "severity_confidence": 0.0,
        "repro_steps": [],
        "expected_behavior": "",
        "actual_behavior": "",
        "related_files": [],
        "assignee": "",
        "assignee_reason": "",
        "notification_message": "",
        "logs": [],
        "iteration_count": 0,
        "errors": [],
    }


@pytest.fixture
def make_state(empty_state):
    """Factory that returns a state dict populated with given overrides."""
    def _make(**overrides) -> dict:
        s = dict(empty_state)
        s.update(overrides)
        return s
    return _make


@pytest.fixture
def mock_codebase(tmp_path: Path) -> str:
    """Tiny throwaway codebase for codebase_searcher tests."""
    root = tmp_path / "code"
    root.mkdir()
    (root / "auth.py").write_text(
        "def login(user, password):\n    return check_password(user, password)\n",
        encoding="utf-8",
    )
    (root / "payment.py").write_text(
        "def process_payment(order):\n    # charges the card\n    pass\n",
        encoding="utf-8",
    )
    (root / "ignored.txt").write_text("should not be scanned", encoding="utf-8")
    return str(root)
