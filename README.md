# Code Minds — Bug Triage Multi-Agent System

A LangGraph-based multi-agent system that triages incoming bug reports end-to-end — validating issues, classifying severity, generating reproduction steps, finding the right developer, and drafting a Slack notification — all running **locally** against a small open-source LLM via Ollama.

Built for **CTSE Assignment II (SE4010)** at SLIIT. Four agents, four tools, one shared state, zero cloud cost.

```
Raw bug report ─▶ Coordinator ─▶ [Classifier ∥ Reproducer] ─▶ Delegator ─▶ Slack-formatted ticket
```

> **Project status: scaffold.** The folder layout, shared `core/`, data fixtures, and documentation are in place. Each team member's agent, tool, and test file is a stub that raises `NotImplementedError`. Start from [`MEMBERS.md`](MEMBERS.md) — it tells you which file is yours and what contract it has to satisfy.

Full architecture: [`docs/architecture.md`](docs/architecture.md). Onboarding: [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md).

---

## Quick start (for all team members)

Prerequisites: **Python 3.10+**, **Ollama**, ~3 GB free disk for the model.

```bash
# 1. Install Ollama
#    macOS/Linux:
curl -fsSL https://ollama.com/install.sh | sh
#    Windows: download from https://ollama.com/download

# 2. Pull the model (~2 GB)
ollama pull qwen2.5:3b

# 3. Clone + install (after the repo is on your machine)
cd code_minds
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 4. Configure environment
cp .env.example .env                # defaults are fine

# 5. Read your brief
#    Open MEMBERS.md, find your section, implement the three files listed.
```

Once **all four members** have filled in their stubs:

```bash
python main.py --bug "All checkout attempts return 'card declined' even on valid cards"
```

---

## Running the tests

Two tiers. The LLM tier auto-skips if Ollama is unreachable.

```bash
# Deterministic tier — fast, no Ollama required
pytest -m "not llm and not integration" -v

# Full suite — requires Ollama running with qwen2.5:3b pulled
pytest -v

# Only your own slice
pytest tests/test_<your_file>.py -v
```

Test fixtures: [`tests/conftest.py`](tests/conftest.py). LLM judge: [`tests/llm_judge.py`](tests/llm_judge.py). Golden dataset: [`data/golden_dataset.json`](data/golden_dataset.json) (20 labelled bugs, 5 per team member).

---

## Repository layout

```
code_minds/
├── agents/              # 4 agents: coordinator, classifier, reproducer, delegator  [stubs]
├── core/                # state.py, llm.py, graph.py, logger.py                    [done]
├── tools/               # 5 tools: github_fetcher, severity_scanner,
│                        #          codebase_searcher, developer_lookup (stubs),
│                        #          slack_notifier (done)
├── tests/               # per-agent + integration + llm_judge                      [stubs + conftest/judge done]
├── data/
│   ├── developers.json      # 6-person mock developer DB
│   ├── golden_dataset.json  # 20 labelled bug reports
│   └── mock_codebase/       # NestJS-flavoured .ts files for codebase_searcher
├── logs/                # runtime execution traces (gitignored)
├── main.py              # CLI entry point
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Team — who owns what

Each member owns one agent, one tool, and one test file. **Start in
[`MEMBERS.md`](MEMBERS.md)** — it has the contract, acceptance criteria, and
run commands for each slice.

| Member                       | Agent                   | Tool                         | Test file                   |
| ---------------------------- | ----------------------- | ---------------------------- | --------------------------- |
| **Member 1** (project setup) | `agents/coordinator.py` | `tools/github_fetcher.py`    | `tests/test_coordinator.py` |
| **Member 2**                 | `agents/classifier.py`  | `tools/severity_scanner.py`  | `tests/test_classifier.py`  |
| **Member 3**                 | `agents/reproducer.py`  | `tools/codebase_searcher.py` | `tests/test_reproducer.py`  |
| **Member 4**                 | `agents/delegator.py`   | `tools/developer_lookup.py`  | `tests/test_delegator.py`   |

**Shared (pair work):** `core/state.py`, `core/graph.py`, `core/llm.py`, `core/logger.py`, `tools/slack_notifier.py`, golden dataset, architecture diagram, demo video, technical report.

---

## Model comparison

| Model          | Size   | M1 8GB      | Intel 16GB+ | Tool-call quality | Verdict                    |
| -------------- | ------ | ----------- | ----------- | ----------------- | -------------------------- |
| `qwen2.5:3b`   | 2.0 GB | 15–20 tok/s | 25+ tok/s   | Excellent         | **Chosen**                 |
| `phi3:mini`    | 2.3 GB | Usable      | Good        | Very good         | Fallback                   |
| `llama3.2:3b`  | 2.0 GB | Usable      | Good        | Good              | Alternative                |
| `qwen2.5:1.5b` | 1.0 GB | Fast        | Fast        | Adequate          | Emergency low-RAM fallback |

Swap models by editing `OLLAMA_MODEL` in `.env` and running `ollama pull <model>`.

---

## Documentation index

| Doc                                                          | What it's for                                                                      |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| [`MEMBERS.md`](MEMBERS.md)                                   | **Start here if you are a team member.** Your file, contract, tests, run commands. |
| [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md)             | Full onboarding — setup, run, test, VIVA prep, troubleshooting.                    |
| [`docs/architecture.md`](docs/architecture.md)               | How the system is designed — CWD pattern, state, reducers, lecture mapping.        |
| [`docs/agent_prompts.md`](docs/agent_prompts.md)             | Verbatim system prompts for all 4 agents.                                          |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | The master plan driving implementation.                                            |
| [`docs/diagrams/workflow.md`](docs/diagrams/workflow.md)     | Mermaid + Graphviz sources.                                                        |
| [`docs/phases/`](docs/phases/)                               | Per-phase (A–G) build guides.                                                      |

---

## Troubleshooting (top 3)

1. **`NotImplementedError: Member N: implement ...`** — the file is still a stub. Open `MEMBERS.md`, find your section, implement it.
2. **`ConnectionError: localhost:11434`** — Ollama is not running. On macOS/Linux run `ollama serve`; on Windows open the Ollama tray app.
3. **`model 'qwen2.5:3b' not found`** — you skipped `ollama pull qwen2.5:3b`. Run it.

Full troubleshooting list: [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) §10.

---

## Deliverables

- Source code: this repository.
- Technical report (4–8 pages, PDF): _TBD — add link here once written._
- Demo video (4–5 min, MP4): _TBD — add link here once recorded._

---

**License:** academic coursework — SLIIT SE4010, 2026.
