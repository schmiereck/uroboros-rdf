# GEMINI.md - Uroboros-RDF

## Project Overview
**Uroboros-RDF (Recursive Discovery Framework)** is an autonomous research orchestrator designed to automate the scientific discovery process. It implements a closed-loop system where two AI agents collaborate:

- **Strategic Planner (Gemini 2.5 Pro):** Analyzes the current research state, forms falsifiable hypotheses, and plans experiments. It uses context-cached system prompts for efficiency.
- **Implementation Executor (Claude Code):** Executes the planned experiments by writing code, running simulations, and collecting metrics within a persistent `src/` directory.

The framework is designed for iterative, empirical research, where each iteration results in a git commit and contributes to an evolving `current_state.md` document.

## Architecture
- **Orchestrator (`rdf/core/orchestrator.py`):** The central controller managing the research loop, state transitions, and user interaction.
- **Agents:**
    - **Planner (`rdf/agents/planner.py`):** Wraps the Gemini adapter. It uses tools like `run_agent` to delegate work.
    - **Executor (`rdf/agents/executor.py`):** Wraps the Claude adapter to execute concrete tasks.
- **Adapters (`rdf/adapters/`):** Interface with specific LLM APIs (Gemini, Claude).
- **Tools (`rdf/tools/`):** Function declarations and implementations available to the Planner (e.g., `run_agent`, `read_iteration`).
- **State Management:**
    - `goal.md`: Defines the high-level research objective and success criteria.
    - `current_state.md`: A live document summarizing confirmed facts, refuted hypotheses, and open questions.
    - `experiment_log.md`: An append-only log of all iterations with YAML metadata.
    - `archive/iter_NNN/`: Stores per-iteration artifacts (logs, results, metadata).
    - `src/`: Persistent source code directory for the research project.

## Building and Running

### Prerequisites
- Python 3.11+
- Gemini API Key (`GEMINI_API_KEY` environment variable)
- Claude Code CLI (authenticated via `claude login`)

### Setup
```bash
python -m venv .venv
# Activate venv (Windows: .venv\Scripts\activate, Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

### Key Commands
- **Initialize a Project:**
  ```bash
  python orchestrator.py --project path/to/project init
  ```
- **Run the Research Loop:**
  ```bash
  python orchestrator.py --project path/to/project run
  ```
- **Dry-run (Testing):**
  ```bash
  python orchestrator.py --project path/to/project run --dry-run
  ```

## Development Conventions

### Scientific Methodology
- **Minimal Validating Step:** Prioritize the smallest intervention that produces falsifiable evidence.
- **Falsifiable Hypotheses:** Every iteration must aim to test a specific claim with a measurable outcome.
- **State Hygiene:** `current_state.md` must be updated every iteration to reflect the latest findings.
- **Negative Results:** Refuted hypotheses are as valuable as confirmed ones and must be documented.

### Project Layout
- **Tool Repo:** This repository contains the orchestrator logic.
- **Research Project Repo:** A separate directory managed by the orchestrator containing `goal.md`, `src/`, and `archive/`.

### Coding Standards
- **Python:** Use type hints and follow PEP 8.
- **Rich UI:** Use the `rich` library for terminal output formatting.
- **YAML:** All agent reports and logs use YAML for structured data.
- **Git:** The framework automatically handles commits and tags. Manual changes should be committed with clear messages following the project's style.

### Agent Interactions
- The Planner communicates with the Executor via the `run_agent` tool.
- The Executor (Claude) operates with `cwd = src/` in the research project.
- Results are reported back to the Planner in a specific YAML format.
